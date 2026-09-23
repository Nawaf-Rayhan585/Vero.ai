from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import OWNER, adopt_orphans, get_current_user
from app.auth_schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeRead,
    OrganizationMembershipRead,
    OrganizationRead,
    RefreshRequest,
    RegisterRequest,
    TokenPairRead,
    UserRead,
)
from app.config import get_settings
from app.database import get_db
from app.models import Location, Membership, Organization, RefreshToken, User
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

INCORRECT_CREDENTIALS = "Incorrect email or password"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _org_memberships(db: Session, user: User) -> list[OrganizationMembershipRead]:
    rows = db.execute(
        select(Membership, Organization).join(Organization).where(Membership.user_id == user.id)
    ).all()
    return [
        OrganizationMembershipRead(organization=OrganizationRead.model_validate(org), role=membership.role)
        for membership, org in rows
    ]


def _issue_tokens(db: Session, user: User) -> TokenPairRead:
    settings = get_settings()
    access_token = create_access_token(user.id, settings.access_token_ttl_seconds, settings.auth_secret_key)
    refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    db.commit()
    return TokenPairRead(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
        user=UserRead.model_validate(user),
        organizations=_org_memberships(db, user),
    )


@router.post("/register", response_model=TokenPairRead)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    email = _normalize_email(request.email)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Whether to adopt pre-Phase-10 data is decided *before* this user is inserted, so a
    # second concurrent registration can never also see "no users yet".
    is_first_user = db.scalar(select(func.count()).select_from(User)) == 0

    user = User(email=email, password_hash=hash_password(request.password), name=request.name)
    db.add(user)
    db.flush()

    organization = Organization(name=request.organization_name)
    db.add(organization)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=organization.id, role=OWNER))
    db.add(Location(organization_id=organization.id, name="Main location"))
    db.flush()

    if is_first_user:
        adopt_orphans(db, organization.id)

    return _issue_tokens(db, user)


@router.post("/login", response_model=TokenPairRead)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    email = _normalize_email(request.email)
    user = db.scalar(select(User).where(User.email == email))

    # verify_password always does a real Argon2 verify, even when `user` is None, so a
    # wrong password and an unregistered email take the same time and get the same error.
    if not verify_password(request.password, user.password_hash if user else None) or not (user and user.is_active):
        raise HTTPException(status_code=401, detail=INCORRECT_CREDENTIALS)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(request.password)

    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPairRead)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(request.refresh_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    invalid = HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if stored is None:
        raise invalid
    if stored.replaced_by is not None:
        # This token was already used once to rotate — presenting it again means either a
        # bug or a copy of it leaked. Treat it as theft: end every session for this user,
        # not just this one token.
        db.execute(
            RefreshToken.__table__.update()
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        db.commit()
        raise invalid
    if stored.revoked_at is not None or stored.expires_at < datetime.now(timezone.utc):
        raise invalid

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise invalid

    tokens = _issue_tokens(db, user)  # commits; stored.replaced_by needs the new row's id first
    new_token_hash = hash_refresh_token(tokens.refresh_token)
    new_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == new_token_hash))
    stored.revoked_at = datetime.now(timezone.utc)
    stored.replaced_by = new_row.id
    db.commit()
    return tokens


@router.post("/logout", status_code=204)
def logout(request: RefreshRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(request.refresh_token), RefreshToken.user_id == user.id
        )
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return None


@router.get("/me", response_model=MeRead)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return MeRead(user=UserRead.model_validate(user), organizations=_org_memberships(db, user))


@router.post("/change-password", response_model=TokenPairRead)
def change_password(
    request: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user.password_hash = hash_password(request.new_password)
    # Every other session is signed out; a new pair is issued below so this one keeps
    # working without forcing the caller to log back in immediately.
    db.execute(
        RefreshToken.__table__.update()
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    return _issue_tokens(db, user)

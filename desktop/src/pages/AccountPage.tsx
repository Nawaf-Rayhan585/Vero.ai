import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { useCreateOrganization, useRenameOrganization } from "../hooks/useOrganizations";
import { useCreateLocation, useDeleteLocation, useLocations, useUpdateLocation } from "../hooks/useLocations";
import { useAddMember, useMembers, useRemoveMember, useUpdateMemberRole } from "../hooks/useMembers";
import { Button, Card, EmptyState, ErrorNotice, Spinner, StatusBadge } from "../components/ui";
import type { Location, Member, Role } from "../api/types";
import "./AccountPage.css";

const MIN_PASSWORD_LENGTH = 10;
const ROLE_LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", member: "Member" };
const ROLE_TONE: Record<Role, "success" | "neutral"> = { owner: "success", admin: "neutral", member: "neutral" };

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function ProfileSection() {
  const auth = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await auth.logout();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <Card title="Profile">
      <div className="account-profile">
        <div>
          <p className="account-profile__name">{auth.user?.name}</p>
          <p className="account-muted">{auth.user?.email}</p>
        </div>
        {auth.currentRole && (
          <StatusBadge label={ROLE_LABEL[auth.currentRole]} tone={ROLE_TONE[auth.currentRole]} />
        )}
      </div>
      <div className="row">
        <Button onClick={handleSignOut} disabled={signingOut}>
          {signingOut ? "Signing out..." : "Sign out"}
        </Button>
      </div>
    </Card>
  );
}

function PasswordSection() {
  const auth = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match.");
      return;
    }
    setBusy(true);
    try {
      await auth.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSuccess(true);
    } catch (err) {
      setError(errorMessage(err, "Could not change your password."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Password">
      <form className="account-form" onSubmit={handleSubmit}>
        <div className="settings-row">
          <label htmlFor="account-current-password">Current password</label>
          <input
            id="account-current-password"
            type="password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.currentTarget.value)}
          />
        </div>
        <div className="settings-row">
          <label htmlFor="account-new-password">New password</label>
          <input
            id="account-new-password"
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={newPassword}
            onChange={(e) => setNewPassword(e.currentTarget.value)}
          />
        </div>
        <div className="settings-row">
          <label htmlFor="account-confirm-password">Confirm new password</label>
          <input
            id="account-confirm-password"
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.currentTarget.value)}
          />
        </div>
        {error && <ErrorNotice message={error} />}
        {success && <p className="account-success">Password changed. Your other sessions were signed out.</p>}
        <div className="row">
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Saving..." : "Change password"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function OrganizationsSection() {
  const auth = useAuth();
  const canConfigure = auth.currentRole === "owner" || auth.currentRole === "admin";
  const createOrganization = useCreateOrganization();
  const renameOrganization = useRenameOrganization();
  const [renameDraft, setRenameDraft] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");

  const current = auth.organizations.find((m) => m.organization.id === auth.currentOrganizationId);

  function startRename() {
    setRenameDraft(current?.organization.name ?? "");
    setRenaming(true);
  }

  async function submitRename(e: FormEvent) {
    e.preventDefault();
    if (!auth.currentOrganizationId) return;
    try {
      await renameOrganization.mutateAsync({ id: auth.currentOrganizationId, name: renameDraft });
      await auth.refreshOrganizations();
      setRenaming(false);
    } catch {
      // Surfaced below via renameOrganization.isError; nothing else to do here.
    }
  }

  async function submitCreate(e: FormEvent) {
    e.preventDefault();
    try {
      const created = await createOrganization.mutateAsync(newOrgName);
      await auth.refreshOrganizations();
      auth.switchOrganization(created.organization.id);
      setNewOrgName("");
      setCreating(false);
    } catch {
      // Surfaced below via createOrganization.isError; nothing else to do here.
    }
  }

  return (
    <Card title="Organization">
      <div className="settings-row">
        <label htmlFor="account-org-switch">Current organization</label>
        <select
          id="account-org-switch"
          value={auth.currentOrganizationId ?? ""}
          onChange={(e) => auth.switchOrganization(e.currentTarget.value)}
        >
          {auth.organizations.map((m) => (
            <option key={m.organization.id} value={m.organization.id}>
              {m.organization.name} — {ROLE_LABEL[m.role]}
            </option>
          ))}
        </select>
      </div>

      {canConfigure && !renaming && (
        <div className="row">
          <Button onClick={startRename}>Rename this organization</Button>
        </div>
      )}
      {canConfigure && renaming && (
        <form className="account-form" onSubmit={submitRename}>
          <div className="settings-row">
            <label htmlFor="account-org-rename">Organization name</label>
            <input
              id="account-org-rename"
              type="text"
              required
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.currentTarget.value)}
            />
          </div>
          {renameOrganization.isError && <ErrorNotice message={errorMessage(renameOrganization.error, "Could not rename organization.")} />}
          <div className="row">
            <Button type="submit" variant="primary" disabled={renameOrganization.isPending}>
              {renameOrganization.isPending ? "Saving..." : "Save"}
            </Button>
            <Button type="button" onClick={() => setRenaming(false)} disabled={renameOrganization.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      <hr className="account-divider" />

      {!creating && <Button onClick={() => setCreating(true)}>Create another organization</Button>}
      {creating && (
        <form className="account-form" onSubmit={submitCreate}>
          <div className="settings-row">
            <label htmlFor="account-org-create">New organization name</label>
            <input
              id="account-org-create"
              type="text"
              required
              placeholder="e.g. Acme Retail"
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.currentTarget.value)}
            />
            <span className="auth-hint">You&apos;ll be its owner. Switch to it above once created.</span>
          </div>
          {createOrganization.isError && <ErrorNotice message={errorMessage(createOrganization.error, "Could not create organization.")} />}
          <div className="row">
            <Button type="submit" variant="primary" disabled={createOrganization.isPending}>
              {createOrganization.isPending ? "Creating..." : "Create"}
            </Button>
            <Button type="button" onClick={() => setCreating(false)} disabled={createOrganization.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function LocationRow({ location, canConfigure }: { location: Location; canConfigure: boolean }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(location.name);
  const updateLocation = useUpdateLocation();
  const deleteLocation = useDeleteLocation();

  if (editing) {
    return (
      <li className="account-row">
        <form
          className="account-form account-form--inline"
          onSubmit={(e) => {
            e.preventDefault();
            updateLocation.mutate(
              { id: location.id, body: { name: draft } },
              { onSuccess: () => setEditing(false) },
            );
          }}
        >
          <input type="text" required value={draft} onChange={(e) => setDraft(e.currentTarget.value)} />
          <Button type="submit" variant="primary" disabled={updateLocation.isPending}>
            Save
          </Button>
          <Button type="button" onClick={() => setEditing(false)} disabled={updateLocation.isPending}>
            Cancel
          </Button>
          {updateLocation.isError && <ErrorNotice message={errorMessage(updateLocation.error, "Could not rename location.")} />}
        </form>
      </li>
    );
  }

  return (
    <li className="account-row">
      <div className="account-row__header">
        <div>
          <strong>{location.name}</strong>{" "}
          <span className="account-muted">
            {location.camera_count} camera{location.camera_count === 1 ? "" : "s"}
          </span>
        </div>
        {canConfigure && (
          <div className="row">
            <Button onClick={() => { setDraft(location.name); setEditing(true); }}>Rename</Button>
            <Button
              onClick={() => {
                if (window.confirm(`Delete location "${location.name}"?`)) {
                  deleteLocation.mutate(location.id);
                }
              }}
              disabled={deleteLocation.isPending}
            >
              Delete
            </Button>
          </div>
        )}
      </div>
      {deleteLocation.isError && <ErrorNotice message={errorMessage(deleteLocation.error, "Could not delete location.")} />}
    </li>
  );
}

function LocationsSection() {
  const auth = useAuth();
  const canConfigure = auth.currentRole === "owner" || auth.currentRole === "admin";
  const { data: locations, isLoading, isError, error } = useLocations();
  const createLocation = useCreateLocation();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  return (
    <Card title="Locations">
      {canConfigure && (
        <div className="row">
          {!adding && <Button variant="primary" onClick={() => setAdding(true)}>Add location</Button>}
        </div>
      )}
      {adding && (
        <form
          className="account-form"
          onSubmit={(e) => {
            e.preventDefault();
            createLocation.mutate({ name }, { onSuccess: () => { setName(""); setAdding(false); } });
          }}
        >
          <div className="settings-row">
            <label htmlFor="account-location-name">Location name</label>
            <input
              id="account-location-name"
              type="text"
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
          </div>
          {createLocation.isError && <ErrorNotice message={errorMessage(createLocation.error, "Could not create location.")} />}
          <div className="row">
            <Button type="submit" variant="primary" disabled={createLocation.isPending}>
              {createLocation.isPending ? "Adding..." : "Add"}
            </Button>
            <Button type="button" onClick={() => setAdding(false)} disabled={createLocation.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {isLoading && <Spinner label="Loading locations" />}
      {isError && <ErrorNotice message={error.message} />}
      {locations && locations.length === 0 && !adding && (
        <EmptyState title="No locations yet">Add one to start assigning cameras to it.</EmptyState>
      )}
      {locations && locations.length > 0 && (
        <ul className="account-list">
          {locations.map((location) => (
            <LocationRow key={location.id} location={location} canConfigure={canConfigure} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function MemberRow({ member, ownerCount, canConfigure }: { member: Member; ownerCount: number; canConfigure: boolean }) {
  const auth = useAuth();
  const updateRole = useUpdateMemberRole();
  const removeMember = useRemoveMember();
  const isSelf = member.user_id === auth.user?.id;
  const isLastOwner = member.role === "owner" && ownerCount <= 1;
  const canGrantOwner = auth.currentRole === "owner";

  function handleRemove() {
    const prompt = isSelf ? "Leave this organization?" : `Remove ${member.name || member.email} from this organization?`;
    if (!window.confirm(prompt)) return;
    removeMember.mutate(member.user_id, {
      onSuccess: () => {
        if (isSelf) auth.refreshOrganizations();
      },
    });
  }

  const canRemove = isSelf || canConfigure;

  return (
    <li className="account-row">
      <div className="account-row__header">
        <div>
          <strong>{member.name || member.email}</strong> <span className="account-muted">{member.email}</span>
        </div>
        <div className="row">
          {canConfigure ? (
            <select
              value={member.role}
              disabled={updateRole.isPending || isLastOwner}
              title={isLastOwner ? "An organization must always have at least one owner" : undefined}
              onChange={(e) => updateRole.mutate({ userId: member.user_id, role: e.currentTarget.value as Role })}
            >
              <option value="owner" disabled={!canGrantOwner}>Owner</option>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
            </select>
          ) : (
            <StatusBadge label={ROLE_LABEL[member.role]} tone={ROLE_TONE[member.role]} />
          )}
          {canRemove && (
            <Button
              onClick={handleRemove}
              // The backend refuses to remove the last owner no matter who asks — self-leave
              // or another admin/owner removing them — so this disables for both cases.
              disabled={removeMember.isPending || isLastOwner}
              title={isLastOwner ? "An organization must always have at least one owner" : undefined}
            >
              {isSelf ? "Leave" : "Remove"}
            </Button>
          )}
        </div>
      </div>
      {updateRole.isError && <ErrorNotice message={errorMessage(updateRole.error, "Could not change role.")} />}
      {removeMember.isError && <ErrorNotice message={errorMessage(removeMember.error, "Could not remove member.")} />}
    </li>
  );
}

function MembersSection() {
  const auth = useAuth();
  const canConfigure = auth.currentRole === "owner" || auth.currentRole === "admin";
  const canGrantOwner = auth.currentRole === "owner";
  const { data: members, isLoading, isError, error } = useMembers();
  const addMember = useAddMember();
  const [adding, setAdding] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const ownerCount = members?.filter((m) => m.role === "owner").length ?? 0;

  return (
    <Card title="Members">
      {canConfigure && (
        <div className="row">
          {!adding && <Button variant="primary" onClick={() => setAdding(true)}>Add member</Button>}
        </div>
      )}
      {adding && (
        <form
          className="account-form"
          onSubmit={(e) => {
            e.preventDefault();
            addMember.mutate(
              { email, role },
              { onSuccess: () => { setEmail(""); setRole("member"); setAdding(false); } },
            );
          }}
        >
          <div className="settings-row">
            <label htmlFor="account-member-email">Email</label>
            <input
              id="account-member-email"
              type="email"
              required
              autoFocus
              placeholder="Must already have a Vero.ai account"
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
            />
          </div>
          <div className="settings-row">
            <label htmlFor="account-member-role">Role</label>
            <select id="account-member-role" value={role} onChange={(e) => setRole(e.currentTarget.value as Role)}>
              <option value="owner" disabled={!canGrantOwner}>Owner</option>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
            </select>
          </div>
          {addMember.isError && <ErrorNotice message={errorMessage(addMember.error, "Could not add member.")} />}
          <div className="row">
            <Button type="submit" variant="primary" disabled={addMember.isPending}>
              {addMember.isPending ? "Adding..." : "Add"}
            </Button>
            <Button type="button" onClick={() => setAdding(false)} disabled={addMember.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {isLoading && <Spinner label="Loading members" />}
      {isError && <ErrorNotice message={error.message} />}
      {members && members.length > 0 && (
        <ul className="account-list">
          {members.map((member) => (
            <MemberRow key={member.user_id} member={member} ownerCount={ownerCount} canConfigure={canConfigure} />
          ))}
        </ul>
      )}
    </Card>
  );
}

export function AccountPage() {
  const auth = useAuth();
  if (!auth.currentOrganizationId) return null;

  return (
    <>
      <ProfileSection />
      <PasswordSection />
      <OrganizationsSection />
      <LocationsSection />
      <MembersSection />
    </>
  );
}

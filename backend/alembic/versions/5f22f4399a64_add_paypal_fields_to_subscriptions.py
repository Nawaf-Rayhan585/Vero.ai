"""add paypal fields to subscriptions

Revision ID: 5f22f4399a64
Revises: 4901bb10a1ad
Create Date: 2026-09-25 16:06:34.233349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f22f4399a64'
down_revision: Union[str, Sequence[str], None] = '4901bb10a1ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('subscriptions', sa.Column('paypal_subscription_id', sa.String(length=64), nullable=True))
    op.add_column('subscriptions', sa.Column('paypal_plan_id', sa.String(length=64), nullable=True))
    op.add_column('subscriptions', sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        'uq_subscriptions_paypal_subscription_id', 'subscriptions', ['paypal_subscription_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_subscriptions_paypal_subscription_id', 'subscriptions', type_='unique')
    op.drop_column('subscriptions', 'canceled_at')
    op.drop_column('subscriptions', 'paypal_plan_id')
    op.drop_column('subscriptions', 'paypal_subscription_id')

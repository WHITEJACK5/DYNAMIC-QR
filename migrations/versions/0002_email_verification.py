"""email verification (Phase 4d)

Revision ID: 0002_email_verification
Revises: 0001_initial
Create Date: 2026-09-29

Adds the columns the directive's "email verification on registration"
requires. Reversible: downgrade drops them, and drops the index with them.

Existing rows are backfilled as UNVERIFIED (0) rather than silently marked
verified: an account that predates this migration has not proven it can
receive mail, and the dynamic-QR gate should apply to it. That is a
deliberate, visible consequence of the upgrade and is documented in the
README, because the alternative — grandfathering everyone — would make the
new control do nothing for existing users.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_email_verification'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('email_verified', sa.Integer(),
                                     server_default=sa.text('0'), nullable=True))
    op.add_column('users', sa.Column('verify_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('verify_expires', sa.String(), nullable=True))
    op.create_index('idx_users_verify_token', 'users', ['verify_token'])


def downgrade():
    op.drop_index('idx_users_verify_token', table_name='users')
    op.drop_column('users', 'verify_expires')
    op.drop_column('users', 'verify_token')
    op.drop_column('users', 'email_verified')

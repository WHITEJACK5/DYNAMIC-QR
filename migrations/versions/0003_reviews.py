"""review capture (Phase 10)

Revision ID: 0003_reviews
Revises: 0002_email_verification
Create Date: 2026-10-02

Adds the review-capture table. A review is created when a customer scans a
dynamic QR of type `review`, fills in the form, and submits. The LLM
sentiment fields are populated asynchronously by a background job, so they
are nullable and start NULL.
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_reviews'
down_revision = '0002_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('qr_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review_text', sa.Text(), nullable=True),
        # Phase 10b: populated by the LLM job, not at capture time
        sa.Column('sentiment', sa.String(), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['qr_id'], ['qrcodes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_reviews_qr', 'reviews', ['qr_id'])
    op.create_index('idx_reviews_user', 'reviews', ['user_id'])


def downgrade():
    op.drop_index('idx_reviews_user', table_name='reviews')
    op.drop_index('idx_reviews_qr', table_name='reviews')
    op.drop_table('reviews')

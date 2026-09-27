"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-27 10:58:10.143885
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('created_at', sa.String(), nullable=True),
    sa.Column('is_premium', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('twofa_enabled', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('twofa_secret', sa.String(), nullable=True),
    sa.Column('reset_token', sa.String(), nullable=True),
    sa.Column('reset_expires', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('folders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('created_at', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('templates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('config_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('qrcodes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('folder_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('type', sa.String(), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('data_json', sa.Text(), nullable=True),
    sa.Column('is_dynamic', sa.Integer(), nullable=True),
    sa.Column('short_code', sa.String(), nullable=True),
    sa.Column('fg_color', sa.String(), nullable=True),
    sa.Column('bg_color', sa.String(), nullable=True),
    sa.Column('gradient', sa.String(), nullable=True),
    sa.Column('pattern', sa.String(), nullable=True),
    sa.Column('eye_style', sa.String(), nullable=True),
    sa.Column('frame_text', sa.String(), nullable=True),
    sa.Column('frame_color', sa.String(), nullable=True),
    sa.Column('logo_path', sa.String(), nullable=True),
    sa.Column('has_password', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('password_hash', sa.String(), nullable=True),
    sa.Column('expiry_date', sa.String(), nullable=True),
    sa.Column('scan_limit', sa.Integer(), nullable=True),
    sa.Column('scan_count', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('created_at', sa.String(), nullable=True),
    sa.Column('updated_at', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('short_code')
    )
    op.create_index('idx_qr_short', 'qrcodes', ['short_code'], unique=False)
    op.create_index('idx_qr_user', 'qrcodes', ['user_id'], unique=False)
    op.create_table('scans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('qr_id', sa.Integer(), nullable=True),
    sa.Column('timestamp', sa.String(), nullable=True),
    sa.Column('ip', sa.String(), nullable=True),
    sa.Column('user_agent', sa.String(), nullable=True),
    sa.Column('device', sa.String(), nullable=True),
    sa.Column('browser', sa.String(), nullable=True),
    sa.Column('os', sa.String(), nullable=True),
    sa.Column('country', sa.String(), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['qr_id'], ['qrcodes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_scans_qr', 'scans', ['qr_id'], unique=False)


def downgrade():
    op.drop_index('idx_scans_qr', table_name='scans')
    op.drop_table('scans')
    op.drop_index('idx_qr_user', table_name='qrcodes')
    op.drop_index('idx_qr_short', table_name='qrcodes')
    op.drop_table('qrcodes')
    op.drop_table('templates')
    op.drop_table('folders')
    op.drop_table('users')

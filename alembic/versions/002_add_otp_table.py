"""Add OTP table for email verification

Revision ID: 002_add_otp_table
Revises: 001_add_initial_tables
Create Date: 2026-03-31 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_otp_table'
down_revision = '001_add_initial_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create OTP table
    op.create_table(
        'otps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('otp_code', sa.String(length=6), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_otps_email'), 'otps', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_otps_email'), table_name='otps')
    op.drop_table('otps')

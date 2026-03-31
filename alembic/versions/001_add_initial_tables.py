"""Add initial tables - users, accounts, transactions, chunks

Revision ID: 001_add_initial_tables
Revises: None
Create Date: 2026-03-31 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_add_initial_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Create account_details table
    op.create_table(
        'account_details',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_holder_name', sa.String(), nullable=True),
        sa.Column('account_number', sa.String(), nullable=True),
        sa.Column('bank_name', sa.String(), nullable=True),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('ifsc_code', sa.String(), nullable=True),
        sa.Column('statement_start_date', sa.Date(), nullable=True),
        sa.Column('statement_end_date', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_account_details_id'), 'account_details', ['id'], unique=False)
    op.create_index(op.f('ix_account_details_user_id'), 'account_details', ['user_id'], unique=False)

    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('debit', sa.Float(), nullable=True),
        sa.Column('credit', sa.Float(), nullable=True),
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('transaction_type', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['account_details.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_transactions_account_id'), 'transactions', ['account_id'], unique=False)
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)

    # Create chunks table (for RAG embeddings)
    op.create_table(
        'chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', postgresql.FLOAT8RANGE(asdecimal=False), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['account_details.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chunks_account_id'), 'chunks', ['account_id'], unique=False)
    op.create_index(op.f('ix_chunks_id'), 'chunks', ['id'], unique=False)
    op.create_index(op.f('ix_chunks_user_id'), 'chunks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chunks_user_id'), table_name='chunks')
    op.drop_index(op.f('ix_chunks_id'), table_name='chunks')
    op.drop_index(op.f('ix_chunks_account_id'), table_name='chunks')
    op.drop_table('chunks')

    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_account_id'), table_name='transactions')
    op.drop_table('transactions')

    op.drop_index(op.f('ix_account_details_user_id'), table_name='account_details')
    op.drop_index(op.f('ix_account_details_id'), table_name='account_details')
    op.drop_table('account_details')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_user_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

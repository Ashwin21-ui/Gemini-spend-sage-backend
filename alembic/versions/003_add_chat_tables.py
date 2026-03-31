"""Add Chat and ChatMessage tables

Revision ID: 003_add_chat_tables
Revises: 002_add_otp_table
Create Date: 2026-03-31 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_chat_tables'
down_revision = '002_add_otp_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create Chat table
    op.create_table(
        'chats',
        sa.Column('chat_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['account_details.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('chat_id')
    )
    op.create_index(op.f('ix_chats_account_id'), 'chats', ['account_id'], unique=False)
    op.create_index(op.f('ix_chats_chat_id'), 'chats', ['chat_id'], unique=False)
    op.create_index(op.f('ix_chats_created_at'), 'chats', ['created_at'], unique=False)
    op.create_index(op.f('ix_chats_user_id'), 'chats', ['user_id'], unique=False)

    # Create ChatMessage table
    op.create_table(
        'chat_messages',
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chat_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sources', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.chat_id'], ),
        sa.PrimaryKeyConstraint('message_id')
    )
    op.create_index(op.f('ix_chat_messages_chat_id'), 'chat_messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_created_at'), 'chat_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_chat_messages_message_id'), 'chat_messages', ['message_id'], unique=False)


def downgrade() -> None:
    # Drop ChatMessage table
    op.drop_index(op.f('ix_chat_messages_message_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_created_at'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_chat_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    # Drop Chat table
    op.drop_index(op.f('ix_chats_created_at'), table_name='chats')
    op.drop_index(op.f('ix_chats_user_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_account_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_chat_id'), table_name='chats')
    op.drop_table('chats')

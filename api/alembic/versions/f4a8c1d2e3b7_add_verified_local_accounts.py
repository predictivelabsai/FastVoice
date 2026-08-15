"""add verified local accounts

Revision ID: f4a8c1d2e3b7
Revises: c7a1e4f93b26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a8c1d2e3b7"
down_revision: Union[str, None] = "c7a1e4f93b26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.alter_column("users", "email_verified", server_default=sa.false())
    op.create_table(
        "user_auth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_user_auth_tokens_id"), "user_auth_tokens", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_user_auth_tokens_user_id"),
        "user_auth_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_tokens_token_hash"),
        "user_auth_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_user_auth_tokens_expires_at"),
        "user_auth_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_auth_tokens_user_purpose",
        "user_auth_tokens",
        ["user_id", "purpose"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_auth_tokens_user_purpose", table_name="user_auth_tokens")
    op.drop_index(op.f("ix_user_auth_tokens_expires_at"), table_name="user_auth_tokens")
    op.drop_index(op.f("ix_user_auth_tokens_token_hash"), table_name="user_auth_tokens")
    op.drop_index(op.f("ix_user_auth_tokens_user_id"), table_name="user_auth_tokens")
    op.drop_index(op.f("ix_user_auth_tokens_id"), table_name="user_auth_tokens")
    op.drop_table("user_auth_tokens")
    op.drop_column("users", "email_verified")

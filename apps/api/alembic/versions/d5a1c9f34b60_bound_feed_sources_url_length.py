"""bound feed_sources.url length

Caps feed_sources.url at VARCHAR(512) so its unique btree index stays within
Postgres's ~2704-byte per-entry limit even for multibyte URLs. Autogenerate
does not detect this (SQLite ignores string length), so it is written by hand.

Revision ID: d5a1c9f34b60
Revises: c4e8a1f0b2d3
Create Date: 2026-07-08 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'd5a1c9f34b60'
down_revision: str | None = 'c4e8a1f0b2d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('feed_sources') as batch_op:
        batch_op.alter_column(
            'url',
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            type_=sa.String(length=512),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('feed_sources') as batch_op:
        batch_op.alter_column(
            'url',
            existing_type=sa.String(length=512),
            type_=sqlmodel.sql.sqltypes.AutoString(),
            existing_nullable=False,
        )

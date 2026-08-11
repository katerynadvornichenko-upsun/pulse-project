"""add unique index on feed_sources.url

Revision ID: c4e8a1f0b2d3
Revises: 7b3f9c1d2e4a
Create Date: 2026-08-10 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = 'c4e8a1f0b2d3'
down_revision: str | None = '7b3f9c1d2e4a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f('ix_feed_sources_url'), 'feed_sources', ['url'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_feed_sources_url'), table_name='feed_sources')

"""add last_fetched_at to feed_sources

Per-source last successful poll time. FeedItem.fetched_at is first-seen only
(it doubles as the recency fallback for undated entries), so the last-poll
signal needs its own column here.

Revision ID: f2b7e14c9a83
Revises: d5a1c9f34b60
Create Date: 2026-08-11 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2b7e14c9a83'
down_revision: str | None = 'd5a1c9f34b60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'feed_sources',
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('feed_sources', 'last_fetched_at')

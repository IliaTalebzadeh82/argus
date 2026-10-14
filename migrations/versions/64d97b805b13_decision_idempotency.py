"""phase 1 decision idempotency

Revision ID: 64d97b805b13
Revises: 09fc42332bec
"""

import sqlalchemy as sa
from alembic import op

revision = "64d97b805b13"
down_revision = "09fc42332bec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_idempotency",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
    )


def downgrade() -> None:
    op.drop_table("decision_idempotency")

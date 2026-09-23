"""book status rework, error message, dedup constraint

Revision ID: 16a11bac3fe5
Revises: cea5a9aee94b
Create Date: 2026-09-23 16:32:55.435571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16a11bac3fe5'
down_revision: Union[str, None] = 'cea5a9aee94b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite can't ALTER a table to add a constraint directly; batch mode
    # does it via Alembic's copy-and-move strategy instead.
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_books_owner_source_hash", ["owner_id", "source_hash"]
        )


def downgrade() -> None:
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_constraint("uq_books_owner_source_hash", type_="unique")
        batch_op.drop_column("error_message")

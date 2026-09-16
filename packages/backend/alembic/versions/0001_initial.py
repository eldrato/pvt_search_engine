"""Initial Schema Foundation

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-16 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema tables will be defined in subsequent phase milestones
    pass


def downgrade() -> None:
    pass

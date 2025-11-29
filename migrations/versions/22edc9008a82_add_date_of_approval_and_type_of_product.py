"""add date of approval and type of product

Revision ID: 22edc9008a82
Revises: e85b0d2ba66f
Create Date: 2025-08-16 01:54:04.508600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22edc9008a82'
down_revision: Union[str, Sequence[str], None] = 'e85b0d2ba66f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass

def downgrade() -> None:
    """Downgrade schema."""
    pass

"""add date of approval and type of product in policy_version

Revision ID: 217e956a4a63
Revises: 22edc9008a82
Create Date: 2025-08-16 02:15:28.642807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '217e956a4a63'
down_revision: Union[str, Sequence[str], None] = '22edc9008a82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('policy_version', sa.Column('approval_date', sa.String(), nullable=True))
    op.add_column('policy_version', sa.Column('type_of_product', sa.String(), nullable=True))



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('product', 'type_of_product')

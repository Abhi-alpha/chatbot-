"""rename policychunk_metadata to metadata

Revision ID: e85b0d2ba66f
Revises: c76d69435526
Create Date: 2025-08-15 23:23:25.308631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e85b0d2ba66f'
down_revision: Union[str, Sequence[str], None] = 'c76d69435526'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('policy_chunk', sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.drop_column('policy_chunk', 'policyChunk_metadata')

def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('policy_chunk',
                    'metadata',
                    new_column_name='policychunk_metadata',
                    existing_type=postgresql.JSONB,
                    existing_nullable=True)

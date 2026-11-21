"""Add full and market display names to ETF instruments.

Revision ID: 0002_instrument_names
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_instrument_names"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("etf_instruments")}
    if "full_name" not in columns:
        op.add_column("etf_instruments", sa.Column("full_name", sa.String(length=180), nullable=True))
    if "market_name" not in columns:
        op.add_column("etf_instruments", sa.Column("market_name", sa.String(length=120), nullable=True))


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("etf_instruments")}
    if "market_name" in columns:
        op.drop_column("etf_instruments", "market_name")
    if "full_name" in columns:
        op.drop_column("etf_instruments", "full_name")

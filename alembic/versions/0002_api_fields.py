"""API product fields, saved plan output, and seller settings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_api"
down_revision = "0001_stage1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("forecast_override", sa.Numeric(12, 2), nullable=True))
    op.add_column("products", sa.Column("notes", sa.Text(), nullable=True))
    op.create_check_constraint("ck_products_forecast_override_nonnegative", "products",
                                "forecast_override IS NULL OR forecast_override >= 0")
    op.add_column("plans", sa.Column("results", postgresql.JSONB(astext_type=sa.Text()),
                                    server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_table(
        "seller_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.UniqueConstraint("owner_id", name="uq_seller_settings_owner_id"),
    )


def downgrade() -> None:
    op.drop_table("seller_settings")
    op.drop_column("plans", "results")
    op.drop_column("products", "notes")
    op.drop_constraint("ck_products_forecast_override_nonnegative", "products", type_="check")
    op.drop_column("products", "forecast_override")

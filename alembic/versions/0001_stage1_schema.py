"""Initial StockWise persistence schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_stage1"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False), sa.Column("profit_per_unit", sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2)), sa.Column("min_order_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pack_size", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("cost_price >= 0", name="ck_products_cost_nonnegative"),
        sa.CheckConstraint("min_order_qty >= 0", name="ck_products_min_order_nonnegative"),
        sa.CheckConstraint("pack_size >= 1", name="ck_products_pack_size_positive"),
        sa.UniqueConstraint("owner_id", "sku", name="uq_products_owner_sku"))
    op.create_index("ix_products_owner_id", "products", ["owner_id"])
    op.create_table("upload_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False), sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False))
    op.create_index("ix_upload_batches_owner_id", "upload_batches", ["owner_id"])
    op.create_table("sales_weeks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False), sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.Column("stockout_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("upload_batch_id", sa.Integer(), sa.ForeignKey("upload_batches.id", ondelete="SET NULL")),
        sa.CheckConstraint("units_sold >= 0", name="ck_sales_units_nonnegative"),
        sa.UniqueConstraint("product_id", "week_start", name="uq_sales_product_week"))
    op.create_index("ix_sales_weeks_product_id", "sales_weeks", ["product_id"])
    op.create_table("plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("budget", sa.Numeric(12, 2), nullable=False), sa.Column("risk_mode", sa.String(20), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_spent", sa.Numeric(12, 2), nullable=False), sa.Column("total_profit", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_plans_owner_id", "plans", ["owner_id"])
    op.create_table("plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("spend", sa.Numeric(12, 2), nullable=False), sa.Column("expected_profit", sa.Numeric(12, 2), nullable=False))
    op.create_index("ix_plan_items_plan_id", "plan_items", ["plan_id"])

def downgrade() -> None:
    op.drop_index("ix_plan_items_plan_id", table_name="plan_items")
    op.drop_table("plan_items")
    op.drop_index("ix_plans_owner_id", table_name="plans")
    op.drop_table("plans")
    op.drop_index("ix_sales_weeks_product_id", table_name="sales_weeks")
    op.drop_table("sales_weeks")
    op.drop_index("ix_upload_batches_owner_id", table_name="upload_batches")
    op.drop_table("upload_batches")
    op.drop_index("ix_products_owner_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

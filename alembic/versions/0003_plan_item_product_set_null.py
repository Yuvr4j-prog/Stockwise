"""Allow products in saved plans to be deleted."""
from alembic import op
import sqlalchemy as sa

revision = "0003_plan_product_nullable"
down_revision = "0002_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("plan_items_product_id_fkey", "plan_items", type_="foreignkey")
    op.alter_column("plan_items", "product_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("plan_items_product_id_fkey", "plan_items", "products", ["product_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("plan_items_product_id_fkey", "plan_items", type_="foreignkey")
    op.execute("DELETE FROM plan_items WHERE product_id IS NULL")
    op.alter_column("plan_items", "product_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("plan_items_product_id_fkey", "plan_items", "products", ["product_id"], ["id"], ondelete="RESTRICT")

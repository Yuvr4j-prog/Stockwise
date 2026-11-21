from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

from stockwise.models import Base, Plan, Product, SalesWeek


def test_stage1_schema_has_expected_tables_and_relationships():
    configure_mappers()
    assert set(Base.metadata.tables) == {"users", "products", "sales_weeks", "upload_batches", "plans", "plan_items", "seller_settings"}
    assert any(constraint.name == "uq_products_owner_sku" for constraint in Base.metadata.tables["products"].constraints)
    assert any(constraint.name == "uq_sales_product_week" for constraint in SalesWeek.__table__.constraints)
    assert isinstance(Plan.__table__.c.inputs.type, JSONB)
    assert "sales" in Product.__mapper__.relationships
    assert "items" in Plan.__mapper__.relationships

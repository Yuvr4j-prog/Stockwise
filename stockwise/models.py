"""SQLAlchemy 2.0 persistence model for the Stage 1 domain."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    products: Mapped[list[Product]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    batches: Mapped[list[UploadBatch]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    plans: Mapped[list[Plan]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    settings: Mapped[SellerSettings | None] = relationship(back_populates="owner", cascade="all, delete-orphan", uselist=False)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("owner_id", "sku", name="uq_products_owner_sku"),
                      CheckConstraint("cost_price >= 0", name="ck_products_cost_nonnegative"),
                      CheckConstraint("min_order_qty >= 0", name="ck_products_min_order_nonnegative"),
                      CheckConstraint("pack_size >= 1", name="ck_products_pack_size_positive"),
                      CheckConstraint("forecast_override IS NULL OR forecast_override >= 0",
                                      name="ck_products_forecast_override_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    profit_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    min_order_qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    pack_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    forecast_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    owner: Mapped[User] = relationship(back_populates="products")
    sales: Mapped[list[SalesWeek]] = relationship(back_populates="product", cascade="all, delete-orphan")


class UploadBatch(Base):
    __tablename__ = "upload_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    owner: Mapped[User] = relationship(back_populates="batches")


class SalesWeek(Base):
    __tablename__ = "sales_weeks"
    __table_args__ = (UniqueConstraint("product_id", "week_start", name="uq_sales_product_week"),
                      CheckConstraint("units_sold >= 0", name="ck_sales_units_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    stockout_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id", ondelete="SET NULL"))
    product: Mapped[Product] = relationship(back_populates="sales")


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    risk_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    results: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    owner: Mapped[User] = relationship(back_populates="plans")
    items: Mapped[list[PlanItem]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanItem(Base):
    __tablename__ = "plan_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expected_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    plan: Mapped[Plan] = relationship(back_populates="items")


class SellerSettings(Base):
    __tablename__ = "seller_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    owner: Mapped[User] = relationship(back_populates="settings")

"""Create or refresh the opt-in local kirana demonstration seller."""
from __future__ import annotations

import os
from datetime import date, timedelta

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from stockwise.config import load_settings
from stockwise.models import Product, SalesWeek, SellerSettings, UploadBatch, User

DEMO_EMAIL = "demo@stockwise.example.com"
DEMO_PASSWORD = "StockWise-demo-2026"

# SKU, name, unit cost, unit profit, MOQ, pack size, last eight weeks, stockout week indices.
CATALOG = [
    ("RICE-5", "Basmati Rice 5 kg", 310, 65, 6, 2, [12, 14, 13, 18, 16, 19, 17, 21], []),
    ("ATTA-5", "Whole Wheat Atta 5 kg", 205, 38, 4, 1, [17, 18, 19, 17, 21, 20, 23, 22], []),
    ("OIL-1", "Sunflower Oil 1 L", 118, 22, 6, 6, [22, 25, 24, 28, 26, 29, 27, 31], []),
    ("SUGAR-1", "Sugar 1 kg", 41, 8, 5, 1, [20, 21, 18, 22, 24, 22, 25, 24], []),
    ("DAL-1", "Toor Dal 1 kg", 142, 28, 4, 2, [11, 13, 12, 14, 13, 16, 15, 17], []),
    ("TEA-250", "CTC Tea 250 g", 94, 21, 3, 1, [14, 15, 13, 17, 16, 18, 17, 20], []),
    ("SOAP-125", "Bath Soap 125 g", 31, 12, 12, 4, [31, 34, 32, 36, 34, 39, 37, 41], []),
    ("WASH-1", "Laundry Powder 1 kg", 76, 18, 4, 2, [10, 11, 12, 10, 13, 12, 14, 13], []),
    ("BIS-100", "Glucose Biscuits 100 g", 8, 3, 24, 12, [57, 62, 59, 68, 65, 72, 69, 76], []),
    ("NOOD-70", "Instant Noodles 70 g", 12, 4, 24, 12, [42, 45, 41, 49, 47, 53, 50, 56], []),
    ("SALT-1", "Iodised Salt 1 kg", 17, 4, 6, 1, [15, 14, 16, 15, 17, 16, 18, 17], []),
    ("MILK-500", "Milk Powder 500 g", 174, 32, 3, 1, [7, 8, 7, 9, 8, 10, 9, 11], []),
    ("SHMP-10", "Shampoo Sachet 10 ml", 1.8, 0.7, 50, 25, [82, 86, 78, 91, 88, 96, 93, 102], []),
    ("PASTE-150", "Toothpaste 150 g", 62, 15, 3, 1, [8, 9, 8, 10, 9, 11, 10, 12], []),
    ("AGARB-10", "Incense Sticks 10 pack", 19, 6, 5, 1, [12, 14, 13, 15, 16, 14, 18, 19], []),
    ("BAT-AA", "AA Batteries 2 pack", 38, 11, 2, 1, [4, 5, 4, 6, 5, 7, 6, 8], []),
    ("CHIPS-25", "Salted Chips 25 g", 9, 3, 24, 12, [47, 50, 48, 55, 53, 58, 56, 63], [6]),
    ("KETCH-500", "Tomato Ketchup 500 g", 58, 14, 2, 1, [5, 6, 5, 7, 6, 8, 7, 9], [7]),
]


def seed_demo() -> None:
    if os.getenv("SEED_DEMO") != "1":
        raise RuntimeError("Set SEED_DEMO=1 to opt in to local demo data")

    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    password_hasher = PasswordHasher()
    weeks = [date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=offset)
             for offset in reversed(range(8))]
    try:
        with Session(engine) as db, db.begin():
            user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
            if user is None:
                user = User(email=DEMO_EMAIL, password_hash=password_hasher.hash(DEMO_PASSWORD))
                db.add(user)
                db.flush()
            if db.scalar(select(SellerSettings).where(SellerSettings.owner_id == user.id)) is None:
                db.add(SellerSettings(owner_id=user.id, currency="INR"))

            batch = db.scalar(select(UploadBatch).where(
                UploadBatch.owner_id == user.id, UploadBatch.filename == "stockwise-demo-seed.csv"
            ))
            if batch is None:
                batch = UploadBatch(owner_id=user.id, filename="stockwise-demo-seed.csv",
                                    row_count=len(CATALOG) + len(CATALOG) * len(weeks))
                db.add(batch)
                db.flush()

            for old_sale in db.scalars(select(SalesWeek).where(
                SalesWeek.upload_batch_id == batch.id, SalesWeek.week_start.not_in(weeks)
            )):
                db.delete(old_sale)

            products = {product.sku: product for product in db.scalars(
                select(Product).where(Product.owner_id == user.id)
            )}
            for sku, name, cost, profit, minimum, pack, units, stockouts in CATALOG:
                product = products.get(sku)
                if product is None:
                    product = Product(owner_id=user.id, sku=sku, name=name, cost_price=cost,
                                      profit_per_unit=profit, min_order_qty=minimum, pack_size=pack)
                    db.add(product)
                    db.flush()
                    products[sku] = product
                else:
                    product.name = name
                    product.cost_price = cost
                    product.profit_per_unit = profit
                    product.min_order_qty = minimum
                    product.pack_size = pack

                sales = {row.week_start: row for row in db.scalars(
                    select(SalesWeek).where(SalesWeek.product_id == product.id)
                )}
                for index, week in enumerate(weeks):
                    row = sales.get(week)
                    if row is None:
                        row = SalesWeek(product_id=product.id, week_start=week,
                                        units_sold=units[index], stockout_flag=index in stockouts,
                                        upload_batch_id=batch.id)
                        db.add(row)
                    else:
                        row.units_sold = units[index]
                        row.stockout_flag = index in stockouts
                        row.upload_batch_id = batch.id
        print(f"Seeded {DEMO_EMAIL} with {len(CATALOG)} products and {len(weeks)} weeks of sales.")
        print(f"Demo password: {DEMO_PASSWORD}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed_demo()

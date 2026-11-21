"""REST integration tests. Set DATABASE_URL to run against real PostgreSQL."""
from __future__ import annotations

import os
import uuid
from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from alembic import command
from alembic.config import Config
from stockwise.api import SessionLocal, app
from stockwise.models import Product, SalesWeek
from stockwise.imports import MAX_FILE_BYTES

BASE = "/api/v1"
DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.fixture(scope="session")
def migrated_database():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not set; API integration tests require a real PostgreSQL database")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield


@pytest.fixture()
def anonymous_client(migrated_database):
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def other_seller(migrated_database):
    with TestClient(app) as client:
        csrf = client.get(f"{BASE}/auth/csrf").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        email = f"other-{uuid.uuid4().hex}@example.com"
        response = client.post(f"{BASE}/auth/signup", json={"email": email, "password": "correct-horse-51"}, headers=headers)
        assert response.status_code == 201, response.text
        yield client, headers, email


@pytest.fixture()
def seller(anonymous_client):
    client = anonymous_client
    token = client.get(f"{BASE}/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": token}
    email = f"seller-{uuid.uuid4().hex}@example.com"
    response = client.post(f"{BASE}/auth/signup", json={"email": email, "password": "correct-horse-51"}, headers=headers)
    assert response.status_code == 201, response.text
    return client, headers, email, "correct-horse-51", response.json()["id"]


def _product(client, headers, *, sku="R1", name="Rice", cost=10, profit=4, **extra):
    return client.post(f"{BASE}/products", headers=headers, json={
        "sku": sku, "name": name, "cost_price": cost, "profit_per_unit": profit, **extra,
    })


def _wide_upload(client, headers, filename="sales.csv", rows=None):
    contents = rows or ("sku,name,cost_price,profit_per_unit,2026-W44,2026-W45,2026-W46,2026-W47\n"
                        "R1,Rice,10,4,4,5,6,7\n")
    return client.post(f"{BASE}/uploads/commit", headers=headers,
                       files={"file": (filename, contents.encode(), "text/csv")})


def _product_with_history(client, headers, **fields):
    response = _product(client, headers, **fields)
    assert response.status_code == 201, response.text
    result = _wide_upload(client, headers, rows=(
        "sku,name,cost_price,profit_per_unit,2026-W44,2026-W45,2026-W46,2026-W47\n"
        f"{response.json()['sku']},{response.json()['name']},{response.json()['cost_price']},"
        f"{response.json()['profit_per_unit']},4,5,6,7\n"))
    assert result.status_code == 201, result.text
    return response.json()


def test_alembic_migration_matches_current_models(migrated_database):
    command.check(Config("alembic.ini"))


def test_openapi_documents_versioned_routes(anonymous_client):
    response = anonymous_client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "StockWise API"
    assert "/api/v1/plans/optimize" in response.json()["paths"]


def test_signup_sets_http_only_session_and_me_returns_own_account(seller):
    client, _, email, _, user_id = seller
    assert client.cookies.get("stockwise_session")
    cookie = next(c for c in client.cookies.jar if c.name == "stockwise_session")
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert client.get(f"{BASE}/auth/me").json() == {"id": user_id, "email": email}


@pytest.mark.parametrize("csrf_kind", ["missing", "wrong", "no_cookie"])
def test_state_change_requires_matching_csrf(csrf_kind, anonymous_client):
    client = anonymous_client
    headers = {}
    if csrf_kind != "no_cookie":
        token = client.get(f"{BASE}/auth/csrf").json()["csrf_token"]
        if csrf_kind == "wrong":
            headers["X-CSRF-Token"] = "wrong-token"
    else:
        headers["X-CSRF-Token"] = "without-cookie"
    response = client.post(f"{BASE}/auth/signup", headers=headers,
                           json={"email": f"csrf-{uuid.uuid4().hex}@example.com", "password": "correct-horse-51"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_duplicate_signup_email_is_conflict(seller):
    client, headers, email, password, _ = seller
    response = client.post(f"{BASE}/auth/signup", headers=headers, json={"email": email, "password": password})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_in_use"


@pytest.mark.parametrize("payload", [
    {"email": "not-an-email", "password": "correct-horse-51"},
    {"email": "a@example.com", "password": "short"},
    {"email": "a@example.com", "password": "correct-horse-51", "unexpected": True},
])
def test_signup_rejects_invalid_payload(payload, anonymous_client):
    client = anonymous_client
    csrf = client.get(f"{BASE}/auth/csrf").json()["csrf_token"]
    response = client.post(f"{BASE}/auth/signup", headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("password", ["wrong-password", "", "another-invalid-password"])
def test_login_rejects_bad_password(password, seller):
    client, headers, email, _, _ = seller
    client.post(f"{BASE}/auth/logout", headers=headers)
    response = client.post(f"{BASE}/auth/login", headers=headers, json={"email": email, "password": password})
    assert response.status_code in (401, 422)
    if response.status_code == 401:
        assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_and_logout_flow(seller):
    client, headers, email, password, _ = seller
    assert client.post(f"{BASE}/auth/logout", headers=headers).status_code == 200
    assert client.get(f"{BASE}/auth/me").status_code == 401
    assert client.post(f"{BASE}/auth/login", headers=headers, json={"email": email, "password": password}).status_code == 200
    assert client.get(f"{BASE}/auth/me").status_code == 200


def test_unauthenticated_get_requires_session(anonymous_client):
    response = anonymous_client.get(f"{BASE}/products")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_product_crud_and_optional_fields(seller):
    client, headers, *_ = seller
    created = _product(client, headers, notes="front shelf", min_order_qty=6, pack_size=3,
                       forecast_override=8.5)
    assert created.status_code == 201
    product = created.json()
    assert (product["min_order_qty"], product["pack_size"], product["notes"], product["forecast_override"]) == (6, 3, "front shelf", "8.50")
    updated = client.patch(f"{BASE}/products/{product['id']}", headers=headers,
                           json={"name": "Basmati", "forecast_override": None})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Basmati"
    assert updated.json()["forecast_override"] is None
    assert client.get(f"{BASE}/products/{product['id']}").status_code == 200
    assert client.delete(f"{BASE}/products/{product['id']}", headers=headers).status_code == 204
    assert client.get(f"{BASE}/products/{product['id']}").status_code == 404


@pytest.mark.parametrize("payload", [
    {"sku": "", "name": "x", "cost_price": 1, "profit_per_unit": 1},
    {"sku": "x", "name": "x", "cost_price": -1, "profit_per_unit": 1},
    {"sku": "x", "name": "x", "cost_price": 1, "profit_per_unit": 1, "pack_size": 0},
    {"sku": "x", "name": "x", "cost_price": 1, "profit_per_unit": 1, "min_order_qty": -1},
    {"sku": "x", "name": "x", "cost_price": 1, "profit_per_unit": 1, "forecast_override": -1},
    {"sku": "x", "name": "x", "cost_price": 1, "profit_per_unit": 1, "unknown": 2},
])
def test_product_create_validates_fields(payload, seller):
    client, headers, *_ = seller
    assert client.post(f"{BASE}/products", headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize("field", ["sku", "name", "cost_price", "profit_per_unit", "min_order_qty", "pack_size"])
def test_product_patch_does_not_allow_null_required_fields(field, seller):
    client, headers, *_ = seller
    product = _product(client, headers).json()
    response = client.patch(f"{BASE}/products/{product['id']}", headers=headers, json={field: None})
    assert response.status_code == 422


def test_sku_unique_per_seller(seller):
    client, headers, *_ = seller
    assert _product(client, headers).status_code == 201
    response = _product(client, headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sku_in_use"


def test_product_list_contains_only_seller_rows(seller):
    client, headers, *_ = seller
    _product(client, headers, sku="A")
    _product(client, headers, sku="B")
    assert [row["sku"] for row in client.get(f"{BASE}/products").json()] == ["A", "B"]


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_other_sellers_product_id_is_always_404(method, seller, other_seller):
    client_a, headers_a, *_ = seller
    other_client, other_headers, _ = other_seller
    product = _product(client_a, headers_a).json()
    url = f"{BASE}/products/{product['id']}"
    if method == "get":
        response = other_client.get(url)
    elif method == "patch":
        response = other_client.patch(url, headers=other_headers, json={"name": "stolen"})
    else:
        response = other_client.delete(url, headers=other_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_upload_preview_validates_and_writes_nothing(seller):
    client, headers, *_ = seller
    csv_data = "sku,name,cost_price,profit_per_unit,2026-W44\nR1,Rice,10,4,2\n"
    response = client.post(f"{BASE}/uploads/preview", headers=headers,
                           files={"file": ("sales.csv", csv_data.encode(), "text/csv")})
    assert response.status_code == 200
    assert response.json()["summary"]["products_to_create"] == 1
    assert "no records were written" in response.json()["message"]
    assert client.get(f"{BASE}/products").json() == []


def test_upload_preview_returns_every_error_with_location(seller):
    client, headers, *_ = seller
    invalid = b"sku,name,cost_price,profit_per_unit,2026-W54\nR1,Rice,-1,NaN,-3\n"
    response = client.post(f"{BASE}/uploads/preview", headers=headers,
                           files={"file": ("bad.csv", invalid, "text/csv")})
    assert response.status_code == 422
    details = response.json()["error"]["details"]["errors"]
    assert {(item["row"], item["column"]) for item in details} >= {
        (1, "2026-W54"), (2, "cost_price"), (2, "profit_per_unit")}


def test_upload_preview_returns_nonfatal_warnings_alongside_errors(seller):
    client, headers, *_ = seller
    invalid = b"sku,name,cost_price,profit_per_unit,2026-W44,2026-W45\nR1,Rice,-1,2,4,\n"
    response = client.post(f"{BASE}/uploads/preview", headers=headers,
                           files={"file": ("bad.csv", invalid, "text/csv")})
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["errors"][0]["column"] == "cost_price"
    assert details["warnings"][0]["column"] == "2026-W45"


def test_upload_commit_creates_batch_products_and_sales(seller):
    client, headers, *_ = seller
    result = _wide_upload(client, headers)
    assert result.status_code == 201
    assert result.json()["summary"] == {"product_rows": 1, "products_to_create": 1, "products_to_update": 0, "sales_rows": 4}
    products = client.get(f"{BASE}/products").json()
    assert len(products) == 1 and products[0]["sku"] == "R1"
    sales = client.get(f"{BASE}/products/{products[0]['id']}/sales").json()
    assert len(sales) == 4 and sales[-1]["units_sold"] == 7


def test_new_upload_overwrites_existing_product_week_and_tracks_new_batch(seller):
    client, headers, *_ = seller
    first = _wide_upload(client, headers)
    second = _wide_upload(client, headers, rows="sku,name,cost_price,profit_per_unit,2026-W47\nR1,Rice,12,5,9\n")
    assert first.json()["batch_id"] != second.json()["batch_id"]
    product = client.get(f"{BASE}/products").json()[0]
    assert product["cost_price"] == "12.00"
    assert client.get(f"{BASE}/products/{product['id']}/sales").json()[-1]["units_sold"] == 9
    with SessionLocal() as db:
        sale = db.scalar(select(SalesWeek).join(Product).where(
            Product.owner_id == seller[4], Product.sku == "R1", SalesWeek.week_start == date(2026, 11, 16)))
        assert sale.upload_batch_id == second.json()["batch_id"]


def test_long_format_upload_updates_existing_sku(seller):
    client, headers, *_ = seller
    created = _product(client, headers).json()
    long_csv = b"sku,week,units_sold\nR1,2026-W44,8\n"
    response = client.post(f"{BASE}/uploads/commit", headers=headers,
                           files={"file": ("long.csv", long_csv, "text/csv")})
    assert response.status_code == 201
    history = client.get(f"{BASE}/products/{created['id']}/sales").json()
    assert history[0]["units_sold"] == 8


def test_upload_cannot_resolve_or_modify_another_sellers_sku(seller, other_seller):
    client_a, headers_a, *_ = seller
    client_b, headers_b, *_ = other_seller
    _product(client_a, headers_a, sku="PRIVATE")
    long_csv = b"sku,week,units_sold\nPRIVATE,2026-W44,50\n"
    preview = client_b.post(f"{BASE}/uploads/preview", headers=headers_b,
                            files={"file": ("long.csv", long_csv, "text/csv")})
    commit = client_b.post(f"{BASE}/uploads/commit", headers=headers_b,
                           files={"file": ("long.csv", long_csv, "text/csv")})
    assert preview.status_code == commit.status_code == 422
    assert preview.json()["error"]["details"]["errors"][0]["column"] == "sku"
    assert client_a.get(f"{BASE}/products").json()[0]["sku"] == "PRIVATE"
    assert client_b.get(f"{BASE}/products").json() == []


@pytest.mark.parametrize("template_format", ["wide", "long"])
def test_csv_template_downloads(template_format, anonymous_client):
    response = anonymous_client.get(f"{BASE}/uploads/templates/{template_format}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "sku" in response.text.splitlines()[0]


def test_upload_size_limit_is_enforced_by_api(seller):
    client, headers, *_ = seller
    response = client.post(f"{BASE}/uploads/preview", headers=headers,
                           files={"file": ("big.csv", BytesIO(b"x" * (MAX_FILE_BYTES + 1)), "text/csv")})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_sales_stockout_patch_preserves_sales_and_rejects_non_monday(seller):
    client, headers, *_ = seller
    product = _product_with_history(client, headers)
    response = client.patch(f"{BASE}/products/{product['id']}/sales/2026-11-09",
                            headers=headers, json={"stockout_flag": True})
    assert response.status_code == 200
    assert response.json()["units_sold"] == 6
    assert response.json()["stockout_flag"] is True
    bad = client.patch(f"{BASE}/products/{product['id']}/sales/2026-11-10",
                       headers=headers, json={"stockout_flag": True})
    assert bad.status_code == 422


@pytest.mark.parametrize("method", ["auto", "moving_average", "exponential_smoothing"])
def test_forecast_endpoint_returns_history_method_and_override(method, seller):
    client, headers, *_ = seller
    product = _product_with_history(client, headers, forecast_override=8)
    response = client.get(f"{BASE}/forecasts", params={"method": method, "window": 2, "alpha": 0.4})
    assert response.status_code == 200
    result = next(item for item in response.json() if item["product_id"] == product["id"])
    assert result["forecast"] == 8
    assert result["override_applied"] is True
    assert len(result["history"]) == 4
    assert result["method_used"] in {"moving_average", "exponential_smoothing"}


@pytest.mark.parametrize("params", [{"window": 0}, {"alpha": 0}, {"method": "holt"}])
def test_forecast_endpoint_rejects_invalid_settings(params, seller):
    client, *_ = seller
    response = client.get(f"{BASE}/forecasts", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_optimize_saves_plan_with_totals_and_greedy_comparison(seller):
    client, headers, *_ = seller
    _product_with_history(client, headers)
    response = client.post(f"{BASE}/plans/optimize", headers=headers,
                           json={"budget": 25, "risk_mode": "balanced", "forecast_method": "moving_average"})
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["items"][0]["quantity"] > 0
    assert plan["total_profit"] >= 0
    assert "greedy_profit" in plan and "unspent_budget" in plan
    reopened = client.get(f"{BASE}/plans/{plan['id']}").json()
    assert reopened["inputs"]["risk_mode"] == "balanced"
    assert reopened["inputs"]["products"][0]["cost_price"] == "10.00"
    assert len(client.get(f"{BASE}/plans").json()) == 1


@pytest.mark.parametrize(("risk_mode", "forecast_cap"), [("safe", 5), ("balanced", 7), ("aggressive", 8)])
def test_optimize_applies_named_risk_mode(risk_mode, forecast_cap, seller):
    client, headers, *_ = seller
    _product_with_history(client, headers, cost=1, profit=1)
    result = client.post(f"{BASE}/plans/optimize", headers=headers,
                         json={"budget": 100, "risk_mode": risk_mode, "forecast_method": "moving_average", "window": 1})
    assert result.status_code == 201, result.text
    assert result.json()["items"][0]["forecast"] == 7
    assert result.json()["items"][0]["quantity"] == forecast_cap


def test_optimize_enforces_optional_moq_without_forcing_purchase(seller):
    client, headers, *_ = seller
    _product_with_history(client, headers, min_order_qty=6, pack_size=3, cost=10, profit=2)
    no_budget = client.post(f"{BASE}/plans/optimize", headers=headers,
                            json={"budget": 20, "risk_mode": "balanced", "forecast_method": "moving_average"})
    assert no_budget.status_code == 201
    assert no_budget.json()["items"][0]["quantity"] == 0


def test_optimize_reports_infeasible_forced_include(seller):
    client, headers, *_ = seller
    product = _product_with_history(client, headers, cost=20, profit=3)
    response = client.post(f"{BASE}/plans/optimize", headers=headers, json={
        "budget": 10, "constraints": [{"product_id": product["id"], "force_include": True}],
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "infeasible_plan"
    assert "infeasible" in response.json()["error"]["message"].lower() or "cannot fit" in response.json()["error"]["message"].lower()


@pytest.mark.parametrize("constraints", [
    [{"product_id": 999999, "force_include": True}],
    [{"product_id": 999999, "force_include": True}, {"product_id": 999999, "force_exclude": True}],
])
def test_optimize_rejects_foreign_or_duplicate_constraints(constraints, seller):
    client, headers, *_ = seller
    response = client.post(f"{BASE}/plans/optimize", headers=headers, json={"budget": 5, "constraints": constraints})
    assert response.status_code == 404 if len(constraints) == 1 else 422


def test_saved_plan_export_csv_contains_rows_and_summary(seller):
    client, headers, *_ = seller
    _product_with_history(client, headers)
    plan = client.post(f"{BASE}/plans/optimize", headers=headers, json={"budget": 30}).json()
    response = client.get(f"{BASE}/plans/{plan['id']}/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "total_profit" in response.text


def test_other_seller_cannot_read_plan_or_export(seller, other_seller):
    client, headers, *_ = seller
    _product_with_history(client, headers)
    plan_id = client.post(f"{BASE}/plans/optimize", headers=headers, json={"budget": 30}).json()["id"]
    other_client, _, _ = other_seller
    assert other_client.get(f"{BASE}/plans/{plan_id}").status_code == 404
    assert other_client.get(f"{BASE}/plans/{plan_id}/export.csv").status_code == 404


def test_other_seller_cannot_patch_sales(seller, other_seller):
    client, headers, *_ = seller
    product = _product_with_history(client, headers)
    other_client, token_headers, _ = other_seller
    response = other_client.patch(f"{BASE}/products/{product['id']}/sales/2026-11-09",
                                  headers=token_headers, json={"stockout_flag": True})
    assert response.status_code == 404


def test_settings_default_and_currency_update(seller):
    client, headers, *_ = seller
    assert client.get(f"{BASE}/settings").json() == {"currency": "INR"}
    assert client.patch(f"{BASE}/settings", headers=headers, json={"currency": "usd"}).json() == {"currency": "USD"}


@pytest.mark.parametrize("currency", ["US", "US1", "USDD", "₹₹₹"])
def test_settings_reject_invalid_currency(currency, seller):
    client, headers, *_ = seller
    response = client.patch(f"{BASE}/settings", headers=headers, json={"currency": currency})
    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/products", "/forecasts", "/plans", "/settings", "/auth/me"])
def test_private_routes_require_authentication(path, anonymous_client):
    response = anonymous_client.get(f"{BASE}{path}")
    assert response.status_code == 401

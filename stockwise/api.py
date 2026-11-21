"""StockWise REST API. Forecasting and allocation stay in pure domain modules."""
from __future__ import annotations

import csv
import io
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from stockwise.config import format_upload_limit, load_settings
from stockwise.forecasting import forecast
from stockwise.imports import MAX_FILE_BYTES, ParsedUpload, UploadValidationError, parse_upload
from stockwise.models import Plan, PlanItem, Product, SalesWeek, SellerSettings, UploadBatch, User
from stockwise.optimizer import InfeasiblePlan, ProductOption, solve_plan

settings = load_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=300,
                       connect_args={"connect_timeout": 8})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"
JWT_COOKIE = "stockwise_session"
CSRF_COOKIE = "stockwise_csrf"
JWT_TTL_SECONDS = 60 * 60 * 12
logger = logging.getLogger("stockwise.api")
AUTH_RATE_LIMIT = 10
AUTH_RATE_WINDOW_SECONDS = 60
_auth_attempts: dict[str, deque[float]] = defaultdict(deque)
_auth_attempts_lock = threading.Lock()

app = FastAPI(title="StockWise API", version="1.0.0", docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


def _error(status: int, code: str, message: str, details: Any = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "details": details})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> Response:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        payload = {"error": detail}
    else:
        payload = {"error": {"code": "http_error", "message": str(detail), "details": None}}
    from fastapi.responses import JSONResponse
    return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> Response:
    from fastapi.responses import JSONResponse
    details = [{"location": [str(part) for part in error["loc"]], "message": error["msg"], "type": error["type"]}
               for error in exc.errors()]
    return JSONResponse({"error": {"code": "validation_error", "message": "Request validation failed", "details": details}}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> Response:
    logger.error(
        "Unhandled exception for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    from fastapi.responses import JSONResponse
    return JSONResponse({"error": {"code": "internal_error", "message": "An unexpected server error occurred", "details": None}}, status_code=500)


@app.get("/api/v1/health")
def health() -> dict[str, int | str]:
    return {"status": "ok", "max_upload_bytes": MAX_FILE_BYTES}


@app.get("/api/v1/health/db")
def health_db() -> Response:
    from fastapi.responses import JSONResponse
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def csrf_guard(request: Request, x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    if not cookie or not x_csrf_token or not secrets.compare_digest(cookie, x_csrf_token):
        raise _error(403, "csrf_failed", "A matching CSRF cookie and X-CSRF-Token header are required")


def client_ip(request: Request) -> str:
    if settings.environment.lower() in {"production", "prod"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",", 1)[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def auth_attempt_limit(request: Request) -> None:
    now = time.monotonic()
    address = client_ip(request)
    with _auth_attempts_lock:
        attempts = _auth_attempts[address]
        while attempts and now - attempts[0] >= AUTH_RATE_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= AUTH_RATE_LIMIT:
            retry_after = max(1, ceil(AUTH_RATE_WINDOW_SECONDS - (now - attempts[0])))
            raise HTTPException(status_code=429, detail={
                "code": "rate_limited",
                "message": "Too many sign-in attempts. Try again shortly",
                "details": None,
            }, headers={"Retry-After": str(retry_after)})
        attempts.append(now)
        if len(_auth_attempts) > 4096:
            expired = [key for key, queue in _auth_attempts.items()
                       if not queue or now - queue[-1] >= AUTH_RATE_WINDOW_SECONDS]
            for key in expired:
                _auth_attempts.pop(key, None)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(JWT_COOKIE)
    if not token:
        raise _error(401, "not_authenticated", "Sign in to continue")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise _error(401, "invalid_session", "Your session is invalid or has expired")
    user = db.get(User, user_id)
    if user is None:
        raise _error(401, "invalid_session", "Your session is invalid or has expired")
    return user


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=128)


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    cost_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    profit_per_unit: Decimal = Field(max_digits=12, decimal_places=2)
    min_order_qty: int = Field(default=0, ge=0)
    pack_size: int = Field(default=1, ge=1)
    forecast_override: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None

    @field_validator("sku", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("must not be blank")
        return result


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(default=None, min_length=1, max_length=100)
    name: str = Field(default=None, min_length=1, max_length=200)
    cost_price: Decimal = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    profit_per_unit: Decimal = Field(default=None, max_digits=12, decimal_places=2)
    min_order_qty: int = Field(default=None, ge=0)
    pack_size: int = Field(default=None, ge=1)
    forecast_override: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None

    @field_validator("sku", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("must not be blank")
        return result


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    name: str
    cost_price: Decimal
    profit_per_unit: Decimal
    min_order_qty: int
    pack_size: int
    forecast_override: Decimal | None
    notes: str | None


class StockoutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stockout_flag: StrictBool


class ProductConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int
    force_include: bool = False
    force_exclude: bool = False


class OptimizeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    risk_mode: Literal["safe", "balanced", "aggressive"] = "balanced"
    storage_limit: int | None = Field(default=None, ge=0)
    constraints: list[ProductConstraint] = Field(default_factory=list)
    forecast_method: Literal["auto", "moving_average", "exponential_smoothing"] = "auto"
    window: int = Field(default=3, ge=1, le=52)
    alpha: float = Field(default=0.4, gt=0, le=1)


class CurrencyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        result = value.upper()
        if not result.isascii() or not result.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return result


def _token_for(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(seconds=JWT_TTL_SECONDS)},
                      settings.jwt_secret, algorithm=JWT_ALGORITHM)


def _set_auth_cookie(response: Response, user: User) -> None:
    response.set_cookie(JWT_COOKIE, _token_for(user), max_age=JWT_TTL_SECONDS, httponly=True,
                        secure=settings.secure_cookies, samesite="lax", path="/")


def _seller_product(db: Session, user_id: int, product_id: int) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.owner_id == user_id))
    if product is None:
        raise _error(404, "not_found", "Product not found")
    return product


@app.get("/api/v1/auth/csrf")
def csrf_token(response: Response) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=settings.secure_cookies, samesite="lax", path="/")
    return {"csrf_token": token}


@app.post("/api/v1/auth/signup", status_code=201, dependencies=[Depends(csrf_guard), Depends(auth_attempt_limit)])
def signup(data: AuthInput, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = User(email=str(data.email).lower(), password_hash=password_hasher.hash(data.password))
    user.settings = SellerSettings(currency="INR")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(409, "email_in_use", "An account with this email already exists")
    db.refresh(user)
    _set_auth_cookie(response, user)
    return {"id": user.id, "email": user.email}


@app.post("/api/v1/auth/login", dependencies=[Depends(csrf_guard), Depends(auth_attempt_limit)])
def login(data: AuthInput, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    try:
        valid = user is not None and password_hasher.verify(user.password_hash, data.password)
    except (VerificationError, InvalidHashError, VerifyMismatchError):
        valid = False
    if not valid or user is None:
        raise _error(401, "invalid_credentials", "Email or password is incorrect")
    _set_auth_cookie(response, user)
    return {"id": user.id, "email": user.email}


@app.post("/api/v1/auth/logout", dependencies=[Depends(csrf_guard)])
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(JWT_COOKIE, httponly=True, secure=settings.secure_cookies, samesite="lax", path="/")
    return {"message": "Signed out"}


@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return {"id": user.id, "email": user.email}


@app.get("/api/v1/products", response_model=list[ProductOut])
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.owner_id == user.id).order_by(Product.sku)).all())


@app.post("/api/v1/products", response_model=ProductOut, status_code=201, dependencies=[Depends(csrf_guard)])
def create_product(data: ProductCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Product:
    product = Product(owner_id=user.id, **data.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(409, "sku_in_use", "That SKU is already used in this account")
    db.refresh(product)
    return product


@app.get("/api/v1/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Product:
    return _seller_product(db, user.id, product_id)


@app.patch("/api/v1/products/{product_id}", response_model=ProductOut, dependencies=[Depends(csrf_guard)])
def update_product(product_id: int, data: ProductUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Product:
    product = _seller_product(db, user.id, product_id)
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(product, name, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(409, "sku_in_use", "That SKU is already used in this account")
    db.refresh(product)
    return product


@app.delete("/api/v1/products/{product_id}", status_code=204, dependencies=[Depends(csrf_guard)])
def delete_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    product = _seller_product(db, user.id, product_id)
    db.delete(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(409, "product_in_saved_plan", "This product appears in a saved plan and cannot be deleted")
    return Response(status_code=204)


def _seller_products(db: Session, user_id: int) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.owner_id == user_id).order_by(Product.sku)).all())


def _read_upload(upload: UploadFile) -> tuple[str, bytes]:
    data = upload.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise _error(413, "file_too_large", f"Upload exceeds the {format_upload_limit(MAX_FILE_BYTES)} limit")
    return upload.filename or "upload", data


def _parse_for_seller(db: Session, user_id: int, filename: str, data: bytes) -> ParsedUpload:
    existing = {p.sku: p.name for p in _seller_products(db, user_id)}
    return parse_upload(data, filename, existing)


def _upload_summary(db: Session, user_id: int, parsed: ParsedUpload) -> dict[str, int]:
    current = {p.sku for p in _seller_products(db, user_id)}
    return {"product_rows": len(parsed.products),
            "products_to_create": sum(p.sku not in current for p in parsed.products),
            "products_to_update": sum(p.sku in current for p in parsed.products),
            "sales_rows": len(parsed.sales)}


@app.post("/api/v1/uploads/preview", dependencies=[Depends(csrf_guard)])
def upload_preview(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    filename, data = _read_upload(file)
    try:
        parsed = _parse_for_seller(db, user.id, filename, data)
    except UploadValidationError as exc:
        raise _error(422, "upload_invalid", "Upload contains validation errors",
                     {"errors": exc.errors, "warnings": exc.warnings})
    return {"format": parsed.format, "summary": _upload_summary(db, user.id, parsed), "warnings": parsed.warnings,
            "message": "Preview only; no records were written"}


@app.post("/api/v1/uploads/commit", status_code=201, dependencies=[Depends(csrf_guard)])
def upload_commit(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    filename, data = _read_upload(file)
    try:
        parsed = _parse_for_seller(db, user.id, filename, data)
    except UploadValidationError as exc:
        raise _error(422, "upload_invalid", "Upload contains validation errors",
                     {"errors": exc.errors, "warnings": exc.warnings})
    summary = _upload_summary(db, user.id, parsed)
    current = {p.sku: p for p in _seller_products(db, user.id)}
    batch = UploadBatch(owner_id=user.id, filename=filename, row_count=len(parsed.products) + len(parsed.sales))
    db.add(batch)
    try:
        db.flush()
        for row in parsed.products:
            product = current.get(row.sku)
            if product is None:
                product = Product(owner_id=user.id, sku=row.sku, name=row.name, cost_price=row.cost_price,
                                  profit_per_unit=row.profit_per_unit)
                db.add(product)
                current[row.sku] = product
            else:
                product.name = row.name
                product.cost_price = row.cost_price
                product.profit_per_unit = row.profit_per_unit
        db.flush()
        for row in parsed.sales:
            product = current.get(row.sku)
            if product is None:
                raise _error(422, "unknown_sku", f"SKU {row.sku} is not present in this account")
            old = db.scalar(select(SalesWeek).where(SalesWeek.product_id == product.id, SalesWeek.week_start == row.week_start))
            if old is None:
                db.add(SalesWeek(product_id=product.id, week_start=row.week_start, units_sold=row.units_sold,
                                 upload_batch_id=batch.id))
            else:
                old.units_sold = row.units_sold
                old.upload_batch_id = batch.id
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise _error(409, "upload_conflict", "Upload could not be committed because records changed concurrently")
    return {"batch_id": batch.id, "format": parsed.format, "summary": summary,
            "warnings": parsed.warnings}


@app.get("/api/v1/uploads/templates/{template_format}")
def upload_template(template_format: Literal["wide", "long"]) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if template_format == "long":
        writer.writerow(["sku", "week", "units_sold"])
    else:
        monday = date.today() - timedelta(days=date.today().weekday())
        labels = []
        for offset in reversed(range(4)):
            week_day = monday - timedelta(weeks=offset)
            iso = week_day.isocalendar()
            labels.append(f"{iso.year}-W{iso.week:02d}")
        writer.writerow(["sku", "name", "cost_price", "profit_per_unit", *labels])
    from fastapi.responses import Response as FastAPIResponse
    return FastAPIResponse(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=stockwise-{template_format}-template.csv"})


@app.get("/api/v1/products/{product_id}/sales")
def sales_history(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    product = _seller_product(db, user.id, product_id)
    rows = db.scalars(select(SalesWeek).where(SalesWeek.product_id == product.id).order_by(SalesWeek.week_start)).all()
    return [{"week_start": row.week_start, "units_sold": row.units_sold, "stockout_flag": row.stockout_flag} for row in rows]


@app.patch("/api/v1/products/{product_id}/sales/{week_start}", dependencies=[Depends(csrf_guard)])
def patch_stockout(product_id: int, week_start: date, data: StockoutUpdate,
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    product = _seller_product(db, user.id, product_id)
    if week_start.weekday() != 0:
        raise _error(422, "invalid_week_start", "week_start must be a Monday ISO week date")
    row = db.scalar(select(SalesWeek).where(SalesWeek.product_id == product.id, SalesWeek.week_start == week_start))
    if row is None:
        raise _error(404, "not_found", "Sales week not found")
    row.stockout_flag = data.stockout_flag
    db.commit()
    return {"week_start": row.week_start, "units_sold": row.units_sold, "stockout_flag": row.stockout_flag}


def _history(db: Session, product: Product) -> list[SalesWeek]:
    return list(db.scalars(select(SalesWeek).where(SalesWeek.product_id == product.id).order_by(SalesWeek.week_start)).all())


def _product_forecast(product: Product, history: list[SalesWeek], method: str, window: int, alpha: float) -> dict[str, Any]:
    result = forecast([row.units_sold for row in history], method, window=window, alpha=alpha,
                      stockout_flags=[row.stockout_flag for row in history]) if history else None
    statistical = result.demand if result else 0.0
    override = float(product.forecast_override) if product.forecast_override is not None else None
    return {
        "product_id": product.id, "sku": product.sku, "name": product.name,
        "forecast": override if override is not None else statistical,
        "base_forecast": statistical, "method_used": result.method if result else "no_history",
        "confidence": result.confidence if result else "low", "mae": result.mae if result else None,
        "override_applied": override is not None,
        "history": [{"week_start": row.week_start.isoformat(), "units_sold": row.units_sold,
                     "stockout_flag": row.stockout_flag} for row in history],
    }


@app.get("/api/v1/forecasts")
def forecasts(method: Literal["auto", "moving_average", "exponential_smoothing"] = "auto",
              window: int = Query(default=3, ge=1, le=52), alpha: float = Query(default=0.4, gt=0, le=1),
              user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [_product_forecast(product, _history(db, product), method, window, alpha)
            for product in _seller_products(db, user.id)]


@app.get("/api/v1/plans")
def list_plans(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    plans = db.scalars(select(Plan).where(Plan.owner_id == user.id).order_by(Plan.created_at.desc(), Plan.id.desc())).all()
    return [{"id": plan.id, "created_at": plan.created_at, "budget": plan.budget,
             "risk_mode": plan.risk_mode, "total_spent": plan.total_spent,
             "total_profit": plan.total_profit, "roi": plan.results.get("roi", 0)} for plan in plans]


def _owned_plan(db: Session, user_id: int, plan_id: int) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.owner_id == user_id))
    if plan is None:
        raise _error(404, "not_found", "Plan not found")
    return plan


@app.post("/api/v1/plans/optimize", status_code=201, dependencies=[Depends(csrf_guard)])
def optimize(data: OptimizeInput, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    products = _seller_products(db, user.id)
    requested: dict[int, ProductConstraint] = {}
    for entry in data.constraints:
        if entry.product_id in requested:
            raise _error(422, "duplicate_constraint", "Each product may have one constraint entry")
        if entry.force_include and entry.force_exclude:
            raise _error(422, "conflicting_constraint", "A product cannot be forced both included and excluded")
        requested[entry.product_id] = entry
    by_id = {p.id: p for p in products}
    unknown_ids = sorted(set(requested) - set(by_id))
    if unknown_ids:
        raise _error(404, "not_found", "One or more constrained products were not found")
    forecasts_by_sku: dict[str, dict[str, Any]] = {}
    options = []
    for product in products:
        history = _history(db, product)
        fc = _product_forecast(product, history, data.forecast_method, data.window, data.alpha)
        forecasts_by_sku[product.sku] = fc
        flags = requested.get(product.id, ProductConstraint(product_id=product.id))
        options.append(ProductOption(
            sku=product.sku, cost=float(product.cost_price), profit=float(product.profit_per_unit),
            demand=float(fc["forecast"]), min_qty=product.min_order_qty, pack_size=product.pack_size,
            force_include=flags.force_include, force_exclude=flags.force_exclude,
        ))
    try:
        result = solve_plan(options, float(data.budget), storage_limit=data.storage_limit, risk_mode=data.risk_mode)
    except InfeasiblePlan as exc:
        raise _error(422, "infeasible_plan", str(exc))
    rows = [{"sku": item.sku, "quantity": item.quantity, "spend": item.spend,
             "expected_profit": item.expected_profit, "reason": item.reason,
             "forecast": forecasts_by_sku[item.sku]["forecast"]} for item in result.items]
    inputs = {"budget": str(data.budget), "risk_mode": data.risk_mode, "storage_limit": data.storage_limit,
              "constraints": [item.model_dump() for item in data.constraints],
              "forecast_method": data.forecast_method, "window": data.window, "alpha": data.alpha,
              "products": [{"product_id": p.id, "sku": p.sku, "name": p.name,
                            "cost_price": str(p.cost_price), "profit_per_unit": str(p.profit_per_unit),
                            "min_order_qty": p.min_order_qty, "pack_size": p.pack_size,
                            "forecast_override": str(p.forecast_override) if p.forecast_override is not None else None}
                           for p in products]}
    result_json = {"items": rows, "total_spent": result.total_spent, "unspent_budget": result.unspent_budget,
                   "total_profit": result.total_profit, "roi": result.roi, "greedy_profit": result.greedy_profit,
                   "greedy_quantities": dict(result.greedy_quantities),
                   "forecasts": list(forecasts_by_sku.values()), "status": result.status}
    plan = Plan(owner_id=user.id, budget=data.budget, risk_mode=data.risk_mode, inputs=inputs,
                results=result_json, total_spent=Decimal(str(result.total_spent)),
                total_profit=Decimal(str(result.total_profit)))
    db.add(plan)
    db.flush()
    product_ids = {p.sku: p.id for p in products}
    db.add_all([PlanItem(plan_id=plan.id, product_id=product_ids[item.sku], sku=item.sku,
                         quantity=item.quantity, spend=Decimal(str(item.spend)),
                         expected_profit=Decimal(str(item.expected_profit))) for item in result.items])
    db.commit()
    return {"id": plan.id, "created_at": plan.created_at, "budget": str(plan.budget),
            "risk_mode": plan.risk_mode, **result_json}


@app.get("/api/v1/plans/{plan_id}")
def get_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = _owned_plan(db, user.id, plan_id)
    return {"id": plan.id, "created_at": plan.created_at, "budget": str(plan.budget),
            "risk_mode": plan.risk_mode, "inputs": plan.inputs, **plan.results}


@app.get("/api/v1/plans/{plan_id}/export.csv")
def export_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    plan = _owned_plan(db, user.id, plan_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["sku", "quantity", "spend", "expected_profit", "reason"])
    for item in plan.results.get("items", []):
        writer.writerow([item["sku"], item["quantity"], item["spend"], item["expected_profit"], item["reason"]])
    writer.writerow([])
    writer.writerow(["total_spent", plan.results.get("total_spent", 0)])
    writer.writerow(["unspent_budget", plan.results.get("unspent_budget", 0)])
    writer.writerow(["total_profit", plan.results.get("total_profit", 0)])
    writer.writerow(["roi", plan.results.get("roi", 0)])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=stockwise-plan-{plan.id}.csv"})


@app.get("/api/v1/settings")
def get_settings(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.scalar(select(SellerSettings).where(SellerSettings.owner_id == user.id))
    return {"currency": row.currency if row is not None else "INR"}


@app.patch("/api/v1/settings", dependencies=[Depends(csrf_guard)])
def update_settings(data: CurrencyUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.scalar(select(SellerSettings).where(SellerSettings.owner_id == user.id))
    if row is None:
        row = SellerSettings(owner_id=user.id, currency=data.currency)
        db.add(row)
    else:
        row.currency = data.currency
    db.commit()
    return {"currency": row.currency}

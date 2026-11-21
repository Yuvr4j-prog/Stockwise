"""Strict pure parsing and validation for wide/long CSV and XLSX sales uploads."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

from openpyxl import load_workbook

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
BASE = {"sku", "name", "cost_price", "profit_per_unit"}


@dataclass(frozen=True)
class ProductRow:
    sku: str
    name: str
    cost_price: float
    profit_per_unit: float


@dataclass(frozen=True)
class SalesRow:
    sku: str
    week_start: date
    units_sold: int


@dataclass
class ParsedUpload:
    format: str
    products: list[ProductRow] = field(default_factory=list)
    sales: list[SalesRow] = field(default_factory=list)


class UploadValidationError(ValueError):
    def __init__(self, errors: list[dict[str, object]]):
        self.errors = errors
        super().__init__("; ".join(f"row {e['row']}: {e['message']}" for e in errors))


def _week(label: str) -> date:
    match = WEEK_RE.fullmatch(label.strip())
    if not match:
        raise ValueError("week must use ISO format YYYY-Www")
    year, week = map(int, match.groups())
    return date.fromisocalendar(year, week, 1)


def _rows(data: bytes, filename: str) -> tuple[list[str], list[list[object]]]:
    if len(data) > MAX_FILE_BYTES:
        raise UploadValidationError([{"row": 0, "field": "file", "message": "file exceeds 10 MiB"}])
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if suffix == "csv":
            decoded = data.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(decoded))
            first = next(reader, None)
            if first is None:
                return [], []
            headers = [str(x).strip() for x in first]
            body = []
            for row in reader:
                body.append(row)
                if len(body) > MAX_ROWS:
                    raise UploadValidationError([{"row": 0, "field": "file", "message": f"file exceeds {MAX_ROWS:,} data rows"}])
        elif suffix == "xlsx":
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            try:
                sheet = workbook.active
                iterator = sheet.iter_rows(values_only=True)
                first = next(iterator, None)
                headers = [str(x).strip() if x is not None else "" for x in (first or ())]
                body = []
                for row in iterator:
                    body.append(list(row))
                    if len(body) > MAX_ROWS:
                        raise UploadValidationError([{"row": 0, "field": "file", "message": f"file exceeds {MAX_ROWS:,} data rows"}])
            finally:
                workbook.close()
        else:
            raise UploadValidationError([{"row": 0, "field": "file", "message": "only .csv and .xlsx files are accepted"}])
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError([{"row": 0, "field": "file", "message": f"could not read file: {exc}"}]) from exc
    return headers, body


def parse_upload(data: bytes, filename: str, existing_products: Mapping[str, str] | None = None) -> ParsedUpload:
    headers, rows = _rows(data, filename)
    errors: list[dict[str, object]] = []
    if not headers or len(set(headers)) != len(headers):
        raise UploadValidationError([{"row": 1, "field": "header", "message": "headers are empty or duplicated"}])
    long_format = set(headers) == {"sku", "week", "units_sold"}
    if long_format:
        parsed = ParsedUpload("long")
        seen: set[tuple[str, date]] = set()
        known = existing_products or {}
        for line, row in enumerate(rows, 2):
            item = dict(zip(headers, row))
            sku = str(item.get("sku", "")).strip()
            try:
                if not sku:
                    raise ValueError("SKU is required")
                if sku not in known:
                    raise ValueError("SKU is not present in existing products")
                week = _week(str(item.get("week", "")))
                units = _units(item.get("units_sold"))
                key = (sku, week)
                if key in seen:
                    raise ValueError("duplicate SKU and week")
                seen.add(key)
                parsed.sales.append(SalesRow(sku, week, units))
            except (ValueError, TypeError) as exc:
                errors.append({"row": line, "field": "row", "message": str(exc)})
        if errors:
            raise UploadValidationError(errors)
        return parsed
    if not BASE.issubset(headers):
        raise UploadValidationError([{"row": 1, "field": "header", "message": f"wide format requires {', '.join(sorted(BASE))} and one or more ISO week columns"}])
    week_cols: dict[int, date] = {}
    for idx, header in enumerate(headers):
        if header in BASE:
            continue
        try:
            week_cols[idx] = _week(header)
        except ValueError as exc:
            errors.append({"row": 1, "field": header, "message": str(exc)})
    if not week_cols:
        errors.append({"row": 1, "field": "week", "message": "at least one ISO week column is required"})
    parsed = ParsedUpload("wide")
    seen_skus: set[str] = set()
    for line, row in enumerate(rows, 2):
        if len(row) != len(headers):
            errors.append({"row": line, "field": "row", "message": "column count does not match header"})
            continue
        item = dict(zip(headers, row))
        sku = str(item.get("sku") or "").strip()
        try:
            if not sku:
                raise ValueError("SKU is required")
            if sku in seen_skus:
                raise ValueError("duplicate SKU")
            seen_skus.add(sku)
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            cost = _money(item.get("cost_price"), "cost_price")
            profit = _money(item.get("profit_per_unit"), "profit_per_unit")
            parsed.products.append(ProductRow(sku, name, cost, profit))
            for idx, week in week_cols.items():
                value = row[idx]
                if value is None or str(value).strip() == "":
                    continue
                parsed.sales.append(SalesRow(sku, week, _units(value)))
        except (ValueError, TypeError) as exc:
            errors.append({"row": line, "field": "row", "message": str(exc)})
    if errors:
        raise UploadValidationError(errors)
    return parsed


def _money(value: object, field: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if number < 0 or number != number or number == float("inf"):
        raise ValueError(f"{field} must be finite and non-negative")
    return number


def _units(value: object) -> int:
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("units_sold must be numeric") from exc
    if number < 0 or not number.is_integer() or number in (float("inf"), float("-inf")):
        raise ValueError("units_sold must be a non-negative whole number")
    return int(number)

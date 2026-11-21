"""Strict pure parsing and validation for wide/long CSV and XLSX uploads."""
from __future__ import annotations

import csv
import io
import re
from math import isfinite
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping

from openpyxl import load_workbook

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
BASE = {"sku", "name", "cost_price", "profit_per_unit"}
NUMBER_RE = re.compile(r"^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")


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
    warnings: list[dict[str, object]] = field(default_factory=list)


def _issue(row: int, column: str, value: object, message: str) -> dict[str, object]:
    return {"row": row, "column": column, "value": value, "message": message}


class UploadValidationError(ValueError):
    def __init__(self, errors: list[dict[str, object]], warnings: list[dict[str, object]] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__("; ".join(f"row {e['row']} column {e['column']}: {e['message']}" for e in errors))


def _week(label: str) -> date:
    match = WEEK_RE.fullmatch(label.strip())
    if not match:
        raise ValueError("week must use ISO format YYYY-Www")
    year, week = map(int, match.groups())
    return date.fromisocalendar(year, week, 1)


def _rows(data: bytes, filename: str) -> tuple[list[str], list[list[object]]]:
    if len(data) > MAX_FILE_BYTES:
        raise UploadValidationError([_issue(0, "file", len(data), "file exceeds 10 MiB")])
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if suffix == "csv":
            reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
            first = next(reader, None)
            if first is None:
                return [], []
            headers = [str(x).strip() for x in first]
            body = []
            for row in reader:
                body.append(row)
                if len(body) > MAX_ROWS:
                    raise UploadValidationError([_issue(0, "file", len(body), f"file exceeds {MAX_ROWS:,} data rows")])
        elif suffix == "xlsx":
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            try:
                iterator = workbook.active.iter_rows(values_only=True)
                first = next(iterator, None)
                headers = [str(x).strip() if x is not None else "" for x in (first or ())]
                body = []
                for row in iterator:
                    body.append(list(row))
                    if len(body) > MAX_ROWS:
                        raise UploadValidationError([_issue(0, "file", len(body), f"file exceeds {MAX_ROWS:,} data rows")])
            finally:
                workbook.close()
        else:
            raise UploadValidationError([_issue(0, "file", filename, "only .csv and .xlsx files are accepted")])
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError([_issue(0, "file", filename, f"could not read file: {exc}")]) from exc
    return headers, body


def _numeric(value: object, column: str, *, money: bool) -> Decimal:
    if value is None:
        raise ValueError(f"{column} must be numeric")
    text = str(value).strip()
    if money and text.startswith("₹"):
        text = text[1:].strip()
    if not NUMBER_RE.fullmatch(text):
        raise ValueError(f"{column} must be numeric with valid thousands grouping")
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"{column} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{column} must be finite")
    return number


def _money(value: object, column: str, *, non_negative: bool = True) -> float:
    number = _numeric(value, column, money=True)
    if non_negative and number < 0:
        raise ValueError(f"{column} must be non-negative")
    converted = float(number)
    if not isfinite(converted):
        raise ValueError(f"{column} must be finite")
    return converted


def _units(value: object) -> int:
    number = _numeric(value, "units_sold", money=False)
    if number < 0:
        raise ValueError("units_sold must be non-negative")
    if number != number.to_integral_value():
        raise ValueError("units_sold must be a whole number")
    return int(number)


def parse_upload(data: bytes, filename: str, existing_products: Mapping[str, str] | None = None) -> ParsedUpload:
    headers, rows = _rows(data, filename)
    errors: list[dict[str, object]] = []
    if not headers:
        raise UploadValidationError([_issue(1, "header", "", "header row is empty")])
    for header in headers:
        if not header:
            errors.append(_issue(1, "header", header, "column name cannot be blank"))
    first_index: dict[str, int] = {}
    for index, header in enumerate(headers):
        if header in first_index:
            errors.append(_issue(1, header, header, "duplicate column name"))
        else:
            first_index[header] = index

    is_long = "week" in headers or "units_sold" in headers
    if is_long:
        expected = {"sku", "week", "units_sold"}
        for missing in sorted(expected - set(headers)):
            errors.append(_issue(1, missing, None, "required long-format column is missing"))
        for unexpected in sorted(set(headers) - expected):
            errors.append(_issue(1, unexpected, unexpected, "unexpected column in long format"))
        parsed = ParsedUpload("long")
        known = existing_products or {}
        seen: set[tuple[str, date]] = set()
        for line, row in enumerate(rows, 2):
            if len(row) != len(headers):
                errors.append(_issue(line, "row", row, f"expected {len(headers)} columns but found {len(row)}"))
                continue
            vals = dict(zip(headers, row))
            sku = str(vals.get("sku") or "").strip()
            week: date | None = None
            units: int | None = None
            if not sku:
                errors.append(_issue(line, "sku", vals.get("sku"), "SKU is required"))
            elif sku not in known:
                errors.append(_issue(line, "sku", vals.get("sku"), "SKU is not present in this seller's products"))
            try:
                week = _week(str(vals.get("week") or ""))
            except (ValueError, TypeError) as exc:
                errors.append(_issue(line, "week", vals.get("week"), str(exc)))
            try:
                units = _units(vals.get("units_sold"))
            except (ValueError, TypeError) as exc:
                errors.append(_issue(line, "units_sold", vals.get("units_sold"), str(exc)))
            if sku and week is not None:
                key = (sku, week)
                if key in seen:
                    errors.append(_issue(line, "week", vals.get("week"), "duplicate SKU and week pair"))
                else:
                    seen.add(key)
                    if units is not None:
                        parsed.sales.append(SalesRow(sku, week, units))
        if errors:
            raise UploadValidationError(errors, parsed.warnings)
        return parsed

    for column in sorted(BASE - set(headers)):
        errors.append(_issue(1, column, None, "required wide-format column is missing"))
    week_cols: dict[int, date] = {}
    for idx, header in enumerate(headers):
        if header in BASE:
            continue
        try:
            week_cols[idx] = _week(header)
        except ValueError as exc:
            errors.append(_issue(1, header or f"column_{idx + 1}", header, str(exc)))
    if not week_cols:
        errors.append(_issue(1, "week", None, "at least one ISO week column is required"))

    parsed = ParsedUpload("wide")
    seen_skus: set[str] = set()
    for line, row in enumerate(rows, 2):
        if len(row) != len(headers):
            errors.append(_issue(line, "row", row, f"expected {len(headers)} columns but found {len(row)}"))
            continue
        vals = dict(zip(headers, row))
        sku = str(vals.get("sku") or "").strip()
        name = str(vals.get("name") or "").strip()
        row_valid = True
        if not sku:
            errors.append(_issue(line, "sku", vals.get("sku"), "SKU is required"))
            row_valid = False
        elif sku in seen_skus:
            errors.append(_issue(line, "sku", vals.get("sku"), "duplicate SKU"))
            row_valid = False
        else:
            seen_skus.add(sku)
        if not name:
            errors.append(_issue(line, "name", vals.get("name"), "name is required"))
            row_valid = False
        cost: float | None = None
        profit: float | None = None
        try:
            cost = _money(vals.get("cost_price"), "cost_price")
        except (ValueError, TypeError) as exc:
            errors.append(_issue(line, "cost_price", vals.get("cost_price"), str(exc)))
            row_valid = False
        try:
            profit = _money(vals.get("profit_per_unit"), "profit_per_unit", non_negative=False)
        except (ValueError, TypeError) as exc:
            errors.append(_issue(line, "profit_per_unit", vals.get("profit_per_unit"), str(exc)))
            row_valid = False

        nonblank_weeks = 0
        blank_weeks: list[tuple[str, object]] = []
        for idx, week in week_cols.items():
            value = row[idx]
            if value is None or str(value).strip() == "":
                blank_weeks.append((headers[idx], value))
                continue
            nonblank_weeks += 1
            try:
                sales_units = _units(value)
            except (ValueError, TypeError) as exc:
                errors.append(_issue(line, headers[idx], value, str(exc)))
                row_valid = False
                continue
            if sku:
                parsed.sales.append(SalesRow(sku, week, sales_units))
        if nonblank_weeks and blank_weeks and len(week_cols) > 1:
            for column, value in blank_weeks:
                parsed.warnings.append(_issue(line, column, value, "blank week skipped while this product has sales in other weeks"))
        if row_valid and cost is not None and profit is not None:
            parsed.products.append(ProductRow(sku, name, cost, profit))
    if errors:
        raise UploadValidationError(errors, parsed.warnings)
    return parsed

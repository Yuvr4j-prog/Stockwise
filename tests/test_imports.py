from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook

from stockwise.imports import UploadValidationError, parse_upload


def test_wide_csv_keeps_zero_skips_blank_and_parses_iso_mondays():
    data = ("sku,name,cost_price,profit_per_unit,2026-W44,2026-W45\n"
            "R1,Rice,50,12,0,\n").encode()
    result = parse_upload(data, "sales.csv")
    assert result.format == "wide"
    assert result.products[0].sku == "R1"
    assert [(s.week_start, s.units_sold) for s in result.sales] == [(date(2026, 10, 26), 0)]


def test_long_csv_requires_known_skus_and_rejects_duplicate_weeks():
    data = b"sku,week,units_sold\nR1,2026-W44,3\nR1,2026-W44,0\n"
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(data, "history.csv", {"R1": "Rice"})
    assert "duplicate SKU and week" in str(exc.value)
    result = parse_upload(b"sku,week,units_sold\nR1,2026-W44,3\n", "history.csv", {"R1": "Rice"})
    assert result.sales[0].week_start == date(2026, 10, 26)


def test_wide_collects_row_errors_without_dropping_bad_rows():
    data = b"sku,name,cost_price,profit_per_unit,2026-W44\nR1,Rice,-2,4,not-a-number\nR1,Rice,3,4,1\n"
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(data, "bad.csv")
    assert [error["row"] for error in exc.value.errors] == [2, 3]


def test_bad_iso_week_and_fractional_sales_rejected():
    for data in (b"sku,name,cost_price,profit_per_unit,2026-W54\nR1,Rice,1,2,1\n",
                 b"sku,week,units_sold\nR1,2026-W44,1.5\n"):
        with pytest.raises(UploadValidationError):
            parse_upload(data, "bad.csv", {"R1": "Rice"})


def test_xlsx_wide_upload_and_limits():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["sku", "name", "cost_price", "profit_per_unit", "2026-W44"])
    sheet.append(["M1", "Milk", 25, 5, 7])
    output = BytesIO()
    workbook.save(output)
    result = parse_upload(output.getvalue(), "sales.xlsx")
    assert result.sales[0].units_sold == 7
    with pytest.raises(UploadValidationError, match="10 MiB"):
        parse_upload(b"x" * (10 * 1024 * 1024 + 1), "big.csv")


def test_row_limit_and_long_unknown_sku_are_errors():
    with pytest.raises(UploadValidationError, match="not present"):
        parse_upload(b"sku,week,units_sold\nR1,2026-W44,1\n", "h.csv", {})


def test_data_row_limit_is_enforced_before_import():
    rows = "".join(f"R{i},Product {i},1,1,0\n" for i in range(10_001))
    data = ("sku,name,cost_price,profit_per_unit,2026-W44\n" + rows).encode()
    with pytest.raises(UploadValidationError, match="10,000 data rows"):
        parse_upload(data, "too-many.csv")

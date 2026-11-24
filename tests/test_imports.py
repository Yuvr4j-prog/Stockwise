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
    assert result.warnings[0]["column"] == "2026-W45"


def test_sku_free_wide_csv_with_price_aliases_and_stockout_columns():
    data = ("name,cost_per_unit,price_per_unit,2026-W44,2026-W44_stockout,2026-W45,2026-W45_stockout\n"
            "Rice 1kg,92,118,4,false,2,true\n").encode()
    result = parse_upload(data, "stockwise-sample-upload.csv")
    assert result.products[0].name == "Rice 1kg"
    assert result.products[0].cost_price == 92
    assert result.products[0].profit_per_unit == 26
    assert [(row.units_sold, row.stockout_flag) for row in result.sales] == [(4, False), (2, True)]


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
    assert [(error["row"], error["column"], error["value"]) for error in exc.value.errors] == [
        (2, "cost_price", "-2"), (2, "2026-W44", "not-a-number"), (3, "sku", "R1")]
    assert all(error["message"] for error in exc.value.errors)


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


def test_currency_and_thousands_separators_parse_without_silent_reformatting():
    # Unquoted comma fields are separate CSV columns; quote formatted values explicitly.
    data = 'sku,name,cost_price,profit_per_unit,2026-W44\nR1,Rice,"₹1,200",-30,"1,200"\n'.encode()
    result = parse_upload(data, "formatted.csv")
    assert result.products[0].cost_price == 1200
    assert result.products[0].profit_per_unit == -30
    assert result.sales[0].units_sold == 1200
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(b'sku,name,cost_price,profit_per_unit,2026-W44\nR1,Rice,"1,20",2,1\n', "bad.csv")
    assert exc.value.errors[0]["value"] == "1,20"


def test_row_limit_and_long_unknown_sku_are_errors():
    with pytest.raises(UploadValidationError, match="not present"):
        parse_upload(b"sku,week,units_sold\nR1,2026-W44,1\n", "h.csv", {})


def test_upload_warnings_include_row_column_value_and_message():
    result = parse_upload(b"sku,name,cost_price,profit_per_unit,2026-W44,2026-W45\nR1,Rice,1,2,3,\n", "w.csv")
    assert result.warnings == [{"row": 2, "column": "2026-W45", "value": "", "message": "blank week skipped while this product has sales in other weeks"}]


def test_parser_collects_all_cell_errors_with_row_column_value_message():
    data = b"name,cost_per_unit,price_per_unit,2026-W44,2026-W45\n,-5,NaN,1.5,-1\n"
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(data, "bad.csv")
    assert [(e["row"], e["column"], e["value"]) for e in exc.value.errors] == [
        (2, "name", ""), (2, "cost_price", "-5"), (2, "selling_price", "NaN"),
        (2, "2026-W44", "1.5"), (2, "2026-W45", "-1")]
    assert all(isinstance(e["message"], str) and e["message"] for e in exc.value.errors)


def test_duplicate_sku_bad_week_headers_and_wrong_column_count_are_reported():
    data = b"sku,name,cost_price,profit_per_unit,2026-W54,not-a-week\nR1,Rice,1,2,2,3\nR1,Rice,1,2\n"
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(data, "bad.csv")
    assert {(e["row"], e["column"]) for e in exc.value.errors} >= {
        (1, "2026-W54"), (1, "not-a-week"), (3, "row")}


def test_long_format_collects_bad_sku_week_units_and_duplicate_pair_errors():
    data = b"sku,week,units_sold\nmissing,2026-W54,-1\nR1,2026-W44,1\nR1,2026-W44,2\n"
    with pytest.raises(UploadValidationError) as exc:
        parse_upload(data, "long.csv", {"R1": "Rice"})
    assert [(e["row"], e["column"]) for e in exc.value.errors] == [
        (2, "sku"), (2, "week"), (2, "units_sold"), (4, "week")]


def test_data_row_limit_is_enforced_before_import():
    rows = "".join(f"R{i},Product {i},1,1,0\n" for i in range(10_001))
    data = ("sku,name,cost_price,profit_per_unit,2026-W44\n" + rows).encode()
    with pytest.raises(UploadValidationError, match="10,000 data rows"):
        parse_upload(data, "too-many.csv")

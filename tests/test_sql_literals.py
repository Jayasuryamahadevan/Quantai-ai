import pytest
from app.security.sql_literals import (
    quote_identifier, sql_literal, validated_direction, validated_limit,
)


def test_identifiers_are_allowlisted():
    assert quote_identifier("sales_2026") == "`sales_2026`"
    assert quote_identifier("`orders`") == "`orders`"
    assert quote_identifier("DATE_FORMAT(`sold_at`, '%Y-%m')") == "DATE_FORMAT(`sold_at`, '%Y-%m')"
    for value in ["x; DROP TABLE y", "SUM(amount)", "x.y", "`x`; --"]:
        with pytest.raises(ValueError):
            quote_identifier(value)


def test_escaping_and_nulls():
    assert sql_literal("O'Reilly") == "'O''Reilly'"
    assert sql_literal(None) == "NULL"
    assert sql_literal(12) == "12"
    assert sql_literal(True) == "1"
    with pytest.raises(ValueError):
        sql_literal(float("nan"))


def test_sort_and_limit_validation():
    assert validated_limit(100_000) == 1000
    assert validated_direction("asc") == "ASC"
    for value in ["1; DROP TABLE x", -1, True, 0]:
        with pytest.raises(ValueError):
            validated_limit(value)
    with pytest.raises(ValueError):
        validated_direction("DESC; DROP TABLE x")

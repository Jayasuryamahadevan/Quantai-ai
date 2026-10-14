import pytest
from app.accuracy.plan_to_sql import compile_plan


def test_literal_is_escaped():
    sql = compile_plan(
        {"metrics": [{"column": "amount", "agg": "sum"}],
         "filters": [{"column": "customer", "op": "=", "value": "O'Reilly"}]},
        table_name="sales", schema_name="quantai_data",
    )
    assert "`customer` = 'O''Reilly'" in sql
    assert "FROM `quantai_data`.`sales`" in sql


def test_rejects_injection_in_identifier_sort_or_limit():
    with pytest.raises(ValueError):
        compile_plan({"group_by": ["x) UNION SELECT secret FROM users --"]}, "sales")
    with pytest.raises(ValueError):
        compile_plan({"order_by": [{"column": "amount", "direction": "DESC; DROP TABLE sales"}]}, "sales")
    with pytest.raises(ValueError):
        compile_plan({"limit": "100; DELETE FROM sales"}, "sales")


def test_bounds_plan_limit():
    assert "LIMIT 1000" in compile_plan({"limit": 100000}, "sales")


def test_rejects_unknown_operator():
    with pytest.raises(ValueError):
        compile_plan({"filters": [{"column": "amount", "op": "= 1 OR 1=1", "value": 10}]}, "sales")

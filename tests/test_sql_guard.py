from app.security.sql_guard import validate_sql


def test_keyword_inside_literal():
    result = validate_sql("SELECT 'DROP' AS action FROM sales", {"sales": ["amount"]})
    assert result.valid, result.error
    assert "LIMIT 1000" in result.sql.upper()


def test_existing_limit_is_capped():
    result = validate_sql("SELECT amount FROM sales LIMIT 999999", {"sales": ["amount"]}, default_limit=50)
    assert result.valid, result.error
    assert "LIMIT 50" in result.sql.upper()


def test_rejects_multi_statement_and_unknown_tables():
    assert not validate_sql("SELECT 1; DROP TABLE sales").valid
    assert not validate_sql("SELECT amount FROM secrets", {"sales": ["amount"]}).valid


def test_handles_table_aliases():
    assert validate_sql("SELECT s.amount FROM sales AS s", {"sales": ["amount"]}).valid
    assert not validate_sql("SELECT s.secret FROM sales AS s", {"sales": ["amount"]}).valid


def test_rejects_unsafe_function():
    assert not validate_sql("SELECT SLEEP(10) FROM sales").valid

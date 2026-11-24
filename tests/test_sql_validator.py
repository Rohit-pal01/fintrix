"""Unit tests for SQL validator and safety layer."""
import pytest
from app.tools.validator import validate_sql, extract_tables

def test_valid_select_query():
    sql = "SELECT amount, txn_date FROM transactions WHERE user_id = 1;"
    is_valid, err = validate_sql(sql, expected_user_id=1)
    assert is_valid is True
    assert err is None

def test_block_dml_keywords():
    queries = [
        "INSERT INTO transactions (amount) VALUES (100);",
        "UPDATE transactions SET amount = 0 WHERE user_id = 1;",
        "DELETE FROM transactions WHERE user_id = 1;",
        "DROP TABLE users;",
        "ALTER TABLE accounts ADD COLUMN secret TEXT;",
        "TRUNCATE TABLE transactions;"
    ]
    for q in queries:
        is_valid, err = validate_sql(q, expected_user_id=1)
        assert is_valid is False, f"Query should have been blocked: {q}"
        assert err is not None

def test_block_comments_injection():
    queries = [
        "SELECT * FROM transactions WHERE user_id = 1 -- comment",
        "SELECT * FROM transactions /* inline comment */ WHERE user_id = 1",
        "SELECT * FROM transactions WHERE user_id = 1; -- bypass"
    ]
    for q in queries:
        is_valid, err = validate_sql(q, expected_user_id=1)
        assert is_valid is False
        assert "comments" in err.lower()

def test_block_multi_statement():
    sql = "SELECT 1 FROM transactions WHERE user_id = 1; DROP TABLE users;"
    is_valid, err = validate_sql(sql, expected_user_id=1)
    assert is_valid is False
    assert "multiple" in err.lower()

def test_block_unauthorized_tables():
    queries = [
        "SELECT * FROM pg_catalog.pg_user;",
        "SELECT * FROM information_schema.tables;",
        "SELECT * FROM passwords WHERE user_id = 1;",
        "SELECT * FROM admin_credentials;"
    ]
    for q in queries:
        is_valid, err = validate_sql(q, expected_user_id=1)
        assert is_valid is False
        assert "unauthorized" in err.lower() or "forbidden" in err.lower()

def test_enforce_user_scoping():
    # Query missing user_id filter when expected_user_id is set
    sql = "SELECT SUM(amount) FROM transactions WHERE direction = 'debit';"
    is_valid, err = validate_sql(sql, expected_user_id=1)
    assert is_valid is False
    assert "user_id" in err.lower()

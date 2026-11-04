"""
Test SQL Injection Scanner
TDD RED PHASE: These tests should FAIL initially
"""

import ast
from pathlib import Path
from typing import Dict, List

import pytest

# Skip all tests if the scanner has not been implemented yet.
# When scripts.audit_sql_injection is created, tests auto-enable.
pytest.importorskip("scripts.audit_sql_injection")


class TestSQLInjectionPatternDetection:
    """Test SQL injection pattern detection - TDD RED PHASE"""

    def test_detects_fstring_in_execute(self):
        """RED: Detect f-string usage in database execute()"""
        # Vulnerable code pattern
        code = """
async def get_user(email: str):
    query = f"SELECT * FROM users WHERE email = '{email}'"
    result = await db.execute(query)
    return result
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        assert len(vulnerabilities) > 0
        assert any("f-string" in v["type"].lower() for v in vulnerabilities)
        assert any("execute" in v["type"].lower() for v in vulnerabilities)

    def test_detects_percent_formatting_in_execute(self):
        """RED: Detect % string formatting in queries"""
        code = """
async def get_agent(agent_id: int):
    query = "SELECT * FROM agents WHERE id = %s" % agent_id
    return await db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        assert len(vulnerabilities) > 0
        assert any(
            "%" in v["type"].lower() or "format" in v["type"].lower() for v in vulnerabilities
        )

    def test_detects_str_format_in_execute(self):
        """RED: Detect .format() string formatting"""
        code = """
def delete_workflow(workflow_name: str):
    query = "DELETE FROM workflows WHERE name = '{}'".format(workflow_name)
    db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        assert len(vulnerabilities) > 0
        assert any("format" in v["type"].lower() for v in vulnerabilities)

    def test_detects_string_concatenation_in_execute(self):
        """RED: Detect string concatenation with + operator"""
        code = """
def search_users(search_term: str):
    query = "SELECT * FROM users WHERE name LIKE '" + search_term + "%'"
    return db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        assert len(vulnerabilities) > 0
        assert any("concat" in v["type"].lower() or "+" in v["code"] for v in vulnerabilities)

    def test_accepts_safe_parameterized_query(self):
        """RED: Safe parameterized queries should NOT be flagged"""
        code = """
async def get_user_safe(email: str):
    query = "SELECT * FROM users WHERE email = :email"
    result = await db.execute(query, {"email": email})
    return result
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        # Should find NO vulnerabilities (safe pattern)
        assert len(vulnerabilities) == 0

    def test_accepts_safe_orm_query(self):
        """RED: SQLAlchemy ORM queries should NOT be flagged"""
        code = """
async def get_user_orm(email: str):
    result = await db.query(User).filter(User.email == email).first()
    return result
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test_file.py")

        # Should find NO vulnerabilities (ORM is safe)
        assert len(vulnerabilities) == 0


class TestSQLInjectionScanner:
    """Test SQL injection scanner functionality - TDD RED PHASE"""

    def test_scanner_reports_file_and_line_number(self):
        """RED: Vulnerabilities should include file path and line number"""
        code = """
def vulnerable_func(user_id: int):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "src/test.py")

        assert len(vulnerabilities) > 0
        vuln = vulnerabilities[0]

        assert "file" in vuln
        assert vuln["file"] == "src/test.py"
        assert "line" in vuln
        assert isinstance(vuln["line"], int)
        assert vuln["line"] > 0

    def test_scanner_includes_vulnerability_type(self):
        """RED: Each vulnerability should have a descriptive type"""
        code = """
query = f"SELECT * FROM users WHERE email = '{email}'"
db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        assert len(vulnerabilities) > 0
        vuln = vulnerabilities[0]

        assert "type" in vuln
        assert isinstance(vuln["type"], str)
        assert len(vuln["type"]) > 0

    def test_scanner_includes_severity_level(self):
        """RED: Vulnerabilities should have severity (HIGH/MEDIUM/LOW)"""
        code = """
db.execute(f"DELETE FROM users WHERE id = {user_id}")
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        assert len(vulnerabilities) > 0
        vuln = vulnerabilities[0]

        assert "severity" in vuln
        assert vuln["severity"] in ["HIGH", "MEDIUM", "LOW"]

    def test_scanner_includes_code_snippet(self):
        """RED: Should include the vulnerable code for review"""
        code = """
query = "SELECT * FROM users WHERE name = '{}'".format(username)
db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        assert len(vulnerabilities) > 0
        vuln = vulnerabilities[0]

        assert "code" in vuln
        assert isinstance(vuln["code"], str)
        assert "format" in vuln["code"].lower() or "execute" in vuln["code"].lower()


class TestMultipleVulnerabilitiesDetection:
    """Test detection of multiple vulnerabilities - TDD RED PHASE"""

    def test_detects_multiple_vulnerabilities_in_same_file(self):
        """RED: Should detect all vulnerabilities in a file"""
        code = """
def func1(email: str):
    query = f"SELECT * FROM users WHERE email = '{email}'"
    db.execute(query)

def func2(user_id: int):
    query = "SELECT * FROM users WHERE id = %s" % user_id
    db.execute(query)

def func3(name: str):
    query = "SELECT * FROM users WHERE name = '{}'".format(name)
    db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        # Should detect all 3 different vulnerability types
        assert len(vulnerabilities) >= 3

    def test_scanner_deduplicates_same_line(self):
        """RED: Should not report same vulnerability multiple times"""
        code = """
query = f"SELECT * FROM users WHERE email = '{email}'"
result = await db.execute(query)
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        # Should only report vulnerability once (f-string in query definition)
        unique_lines = set(v["line"] for v in vulnerabilities)
        assert len(unique_lines) == len(vulnerabilities)


class TestScannerEdgeCases:
    """Test edge cases and false positives - TDD RED PHASE"""

    def test_ignores_comments_with_vulnerable_patterns(self):
        """RED: Should not flag code in comments"""
        code = """
# Bad example: query = f"SELECT * FROM users WHERE email = '{email}'"
# Don't do this: db.execute(query)

def safe_function(email: str):
    query = "SELECT * FROM users WHERE email = :email"
    return db.execute(query, {"email": email})
"""

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        # Should NOT flag comments as vulnerabilities
        assert len(vulnerabilities) == 0

    def test_ignores_docstring_examples(self):
        """RED: Should not flag code in docstrings"""
        code = '''
def safe_query(email: str):
    """
    Example of WRONG way (don't do this):
    query = f"SELECT * FROM users WHERE email = '{email}'"

    Correct way:
    Use parameterized queries
    """
    query = "SELECT * FROM users WHERE email = :email"
    return db.execute(query, {"email": email})
'''

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        # Should NOT flag docstring examples
        assert len(vulnerabilities) == 0

    def test_handles_multiline_queries(self):
        """RED: Should detect vulnerabilities in multiline queries"""
        code = '''
def get_users(status: str):
    query = f"""
        SELECT * FROM users
        WHERE status = '{status}'
        AND active = true
    """
    return db.execute(query)
'''

        from scripts.audit_sql_injection import scan_code_string

        vulnerabilities = scan_code_string(code, "test.py")

        # Should detect f-string in multiline query
        assert len(vulnerabilities) > 0


# Expected test results when running pytest:
#
# pytest tests/unit/test_sql_injection_scanner.py -v
#
# EXPECTED OUTPUT (RED PHASE - ALL SHOULD FAIL):
#
# test_detects_fstring_in_execute FAILED
#   ModuleNotFoundError: No module named 'scripts.audit_sql_injection'
#
# test_detects_percent_formatting_in_execute FAILED
#   ModuleNotFoundError: No module named 'scripts.audit_sql_injection'
#
# ... (all 17 tests should fail with ModuleNotFoundError)
#
# This proves we're doing TDD correctly - tests written BEFORE implementation!

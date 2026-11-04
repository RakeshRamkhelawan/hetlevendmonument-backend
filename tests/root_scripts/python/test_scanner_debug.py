from scripts.audit_sql_injection import scan_code_string

# Test 1: f-string in query assignment
code1 = """
query = f"SELECT * FROM users WHERE email = '{email}'"
result = await db.execute(query)
"""
result1 = scan_code_string(code1, "test1.py")
print("\n=== Test 1: f-string in query assignment ===")
print(f"Found {len(result1)} vulnerabilities")
for v in result1:
    print(f"  Type: {v['type']}")
    print(f"  Line: {v['line']}")
    print(f"  Code: {v['code'][:50]}")

# Test 2: String concatenation in execute()
code2 = """
query = "SELECT * FROM users WHERE name LIKE '" + search_term + "%'"
return db.execute(query)
"""
result2 = scan_code_string(code2, "test2.py")
print("\n=== Test 2: String concatenation ===")
print(f"Found {len(result2)} vulnerabilities")
for v in result2:
    print(f"  Type: {v['type']}")
    print(f"  Line: {v['line']}")
    print(f"  Code: {v['code'][:50]}")

# Test 3: f-string directly in execute()
code3 = """
result = await db.execute(f"SELECT * FROM users WHERE email = '{email}'")
"""
result3 = scan_code_string(code3, "test3.py")
print("\n=== Test 3: f-string directly in execute() ===")
print(f"Found {len(result3)} vulnerabilities")
for v in result3:
    print(f"  Type: {v['type']}")
    print(f"  Line: {v['line']}")
    print(f"  Code: {v['code'][:50]}")

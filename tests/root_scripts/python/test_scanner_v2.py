from scripts.audit_sql_injection import scan_code_string

# Test 4: LLM prompt (should be IGNORED now)
code4 = '''
prompt = f"""
Select the best agent for this task. Return JSON with agent_id, confidence.
Task Type: {context.task_type}
Description: {context.task_description}
"""
'''
result4 = scan_code_string(code4, "test_llm_prompt.py")
print("=== Test 4: LLM Prompt (should be 0) ===")
print(f"Found {len(result4)} vulnerabilities")
if result4:
    for v in result4:
        print(f"  UNEXPECTED: {v['type']}")

# Test 5: Code template (should be IGNORED)
code5 = '''
code_template = f"""
import pandas as pd
SELECT * FROM table
"""
'''
result5 = scan_code_string(code5, "test_template.py")
print("\n=== Test 5: Code Template (should be 0) ===")
print(f"Found {len(result5)} vulnerabilities")

# Test 6: Cache key (should be IGNORED)
code6 = """
cache_key = f"router_selection_{hashlib.md5(str(request).encode()).hexdigest()}"
"""
result6 = scan_code_string(code6, "test_cache.py")
print("\n=== Test 6: Cache Key (should be 0) ===")
print(f"Found {len(result6)} vulnerabilities")

# Test 7: Arithmetic (should be IGNORED)
code7 = """
count = stats.get(agent_id, 0) + 1
"""
result7 = scan_code_string(code7, "test_math.py")
print("\n=== Test 7: Arithmetic (should be 0) ===")
print(f"Found {len(result7)} vulnerabilities")

# Test 8: Real SQL vulnerability (should STILL detect)
code8 = """
query = f"SELECT * FROM users WHERE id = {user_id}"
result = await db.execute(query)
"""
result8 = scan_code_string(code8, "test_real_vuln.py")
print("\n=== Test 8: Real SQL Vuln (should be 1) ===")
print(f"Found {len(result8)} vulnerabilities {'✅' if result8 else '❌ BROKEN!'}")

total_fps = len(result4) + len(result5) + len(result6) + len(result7)
print(f"\n{'='*60}")
print(f"False Positives: {total_fps} (should be 0)")
print(f"Real Vulnerabilities Detected: {len(result8)} (should be 1)")
if total_fps == 0 and len(result8) == 1:
    print("✅ SCANNER IMPROVEMENT SUCCESS!")
else:
    print("❌ Scanner needs more work")

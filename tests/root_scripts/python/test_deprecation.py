"""Test deprecation warnings for security.py"""

import warnings

print("Testing deprecation warnings...")

# Test 1: Module import warning
print("\n1. Testing module import warning:")
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    from src.core.security import create_access_token

    if w:
        print(f"  ✅ Got {len(w)} warning(s)")
        for warning in w:
            print(f"     - {warning.category.__name__}: {warning.message}")
    else:
        print("  ❌ No warnings!")

# Test 2: create_access_token warning
print("\n2. Testing create_access_token() warning:")
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    token = create_access_token({"sub": "test@example.com"})

    if w:
        print(f"  ✅ Got {len(w)} warning(s)")
        for warning in w:
            print(f"     - {warning.category.__name__}: {warning.message}")
    else:
        print("  ❌ No warnings!")

# Test 3: TokenData warning
print("\n3. Testing TokenData class warning:")
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    from src.core.security import TokenData

    td = TokenData(username="test", scopes=["read"])

    if w:
        print(f"  ✅ Got {len(w)} warning(s)")
        for warning in w:
            print(f"     - {warning.category.__name__}: {warning.message}")
    else:
        print("  ❌ No warnings!")

print("\n✅ Deprecation test complete!")

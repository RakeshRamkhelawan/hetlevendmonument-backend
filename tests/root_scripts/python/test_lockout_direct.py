"""Direct test of lockout functionality to debug 500 error."""

import asyncio
from datetime import datetime, timezone

# Test imports
try:
    from src.core.api.auth.router import router

    print("✅ Router imported successfully")
except Exception as e:
    print(f"❌ Router import failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

try:
    from src.core.auth.models.account_lockout import AccountLockout

    print("✅ AccountLockout model imported successfully")
except Exception as e:
    print(f"❌ AccountLockout import failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

# Test datetime
try:
    now = datetime.now(timezone.utc)
    print(f"✅ Timezone-aware datetime works: {now}")
except Exception as e:
    print(f"❌ Datetime failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

# Test creating AccountLockout instance
try:
    lockout = AccountLockout(
        user_id=1, failed_attempts=0, ip_address="127.0.0.1", user_agent="test"
    )
    print(f"✅ AccountLockout instance created: {lockout}")
except Exception as e:
    print(f"❌ AccountLockout instantiation failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

print("\n✅ All imports and basic functionality work!")
print("The issue must be in the test environment or database interaction.")

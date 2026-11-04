import os

from src.core.middleware.tenant_context import require_tenant_id


def test_env_and_tenant_context():
    print(f"DEBUG: TESTING={os.getenv('TESTING')}")
    try:
        tid = require_tenant_id()
        print(f"DEBUG: require_tenant_id() returned {tid}")
    except Exception as e:
        print(f"DEBUG: require_tenant_id() failed with {type(e).__name__}: {e}")

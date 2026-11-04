import os
import sys

import pytest


def test_debug_imports():
    print("\nDEBUG IMPORTS")
    print("sys.path:", sys.path)

    try:
        import src.core as core

        print("core:", core)
        print("core file:", core.__file__)
    except ImportError as e:
        print("ImportError core:", e)

    try:
        import src.core.auth as core_auth

        print("src.core.auth:", core_auth)
        print("src.core.auth file:", getattr(core_auth, "__file__", "unknown"))
        print("src.core.auth path:", getattr(core_auth, "__path__", "unknown"))
        print("src.core.auth type:", type(core_auth))
    except ImportError as e:
        print("ImportError src.core.auth:", e)

    try:
        import src.core.auth.auth_bearer as auth_bearer

        print("src.core.auth.auth_bearer:", auth_bearer)
    except ImportError as e:
        print("ImportError src.core.auth.auth_bearer:", e)

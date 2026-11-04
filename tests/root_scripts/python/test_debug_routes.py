"""
Debug script to inspect registered routes in CVA router
"""

import sys

sys.path.insert(0, "src")

print("\n=== BEGIN ROUTER INSPECTION ===\n")

# Set minimal env vars to allow imports
import os

os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///memory"
os.environ["JWT_SECRET"] = "test-secret"

# Import the router
from src.core.api.cva_endpoints import router as cva_router

print("CVA ROUTER DETAILS:")
print(f"  Prefix: {cva_router.prefix}")
print(f"  Tags: {cva_router.tags}")
print(f"  Number of routes: {len(cva_router.routes)}")
print("\nROUTES IN CVA ROUTER:")

for route in cva_router.routes:
    if hasattr(route, "path"):
        methods = list(getattr(route, "methods", []))
        name = getattr(route, "name", "unknown")
        full_path = cva_router.prefix + route.path
        print(f"  {methods[0] if methods else 'GET':6} {full_path:35} -> {name}")

print("\n=== END ROUTER INSPECTION ===\n")

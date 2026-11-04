import os
import sys

from starlette.routing import Route

# Ensure we can import from src
sys.path.append(os.getcwd())


def safe_print(msg: object) -> None:
    try:
        print(msg, flush=True)
    except Exception as e:
        # Silently fail on print (may be in non-interactive environment)
        sys.stderr.write(f"Failed to print: {str(e)}\n")


safe_print("--- START DEBUG ---")
try:
    safe_print("Importing src.main...")
    from src.main import app

    safe_print("src.main imported.")

    safe_print(f"App Routes Count: {len(app.routes)}")
    for r in app.routes:
        try:
            path = getattr(r, "path", "N/A")
            name = getattr(r, "name", "N/A")
            methods = ", ".join(r.methods) if isinstance(r, Route) and r.methods else "None"
            safe_print(f"Route: {path} [{methods}] ({name})")
        except Exception as e:
            safe_print(f"Error printing route: {e}")

    safe_print("\n--- OAUTH2 ROUTER CHECK ---")
    try:
        from src.core.api.auth.router import router as auth_router

        safe_print(f"OAuth2 Router Routes Count: {len(auth_router.routes)}")
        for r in auth_router.routes:
            try:
                path = getattr(r, "path", "N/A")
                safe_print(f"Auth Route: {path}")
            except Exception as e:
                safe_print(f"Failed to parse auth router route: {str(e)}")
    except Exception as e:
        safe_print(f"Error importing auth_router: {e}")

except Exception as e:
    safe_print(f"CRITICAL ERROR: {e}")
    import traceback

    traceback.print_exc()

safe_print("--- END DEBUG ---")

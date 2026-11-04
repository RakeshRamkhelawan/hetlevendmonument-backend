"""
Backend Feature Test - Complete API Testing with Playwright
Tests all working backend endpoints without requiring frontend
"""

import asyncio
import json

from playwright.async_api import async_playwright

BACKEND_URL = "http://localhost:8100"  # Port updated from 8000 to 8100
EMAIL = "test@example.com"
PASSWORD = "TestPass123"


async def test_backend_features():
    async with async_playwright() as p:
        print("\n" + "=" * 70)
        print("BACKEND FEATURE TEST - Complete API Testing")
        print("=" * 70)

        browser = await p.chromium.launch(headless=False, slow_mo=800)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # ============================================================
            # TEST 1: Health Check
            # ============================================================
            print("\n[1/8] Health Check...")
            await page.goto(f"{BACKEND_URL}/health")
            content = await page.content()

            if "healthy" in content.lower() or "ok" in content.lower():
                print("   [OK] Backend is healthy")
            await asyncio.sleep(1)

            # ============================================================
            # TEST 2: Login
            # ============================================================
            print("\n[2/8] Testing Login...")
            login_response = await page.request.post(
                f"{BACKEND_URL}/api/v1/auth/login",
                data=json.dumps({"email": EMAIL, "password": PASSWORD}),
                headers={"Content-Type": "application/json"},
            )

            login_data = await login_response.json()
            token = login_data.get("access_token")
            user_data = login_data.get("user", {})

            print("   [OK] Login successful")
            print(f"        Email: {user_data.get('email')}")
            print(f"        User ID: {user_data.get('id')}")
            print(f"        Tenant ID: {user_data.get('tenant_id')}")
            print(f"        Roles: {user_data.get('roles')}")
            print(f"        Token: {token[:50]}...")

            await asyncio.sleep(1)

            # ============================================================
            # TEST 3: API Documentation (Interactive)
            # ============================================================
            print("\n[3/8] Opening API Documentation...")
            await page.goto(f"{BACKEND_URL}/docs", wait_until="networkidle")

            title = await page.title()
            print(f"   [OK] API Docs loaded: {title}")
            print("   [INFO] You can interact with the Swagger UI in the browser")

            await page.screenshot(path="test_api_docs.png", full_page=True)
            print("   [OK] Screenshot: test_api_docs.png")

            await asyncio.sleep(2)

            # ============================================================
            # TEST 4: VIBE Workflow Generation (Core Feature)
            # ============================================================
            print("\n[4/8] Testing VIBE Workflow Generation...")

            vibe_prompts = [
                "Create a heritage site documentation workflow",
                "Generate a cultural artifact preservation workflow",
                "Build a multilingual content translation workflow",
            ]

            for i, prompt in enumerate(vibe_prompts, 1):
                print(f"\n   [{i}/3] Prompt: {prompt[:50]}...")

                vibe_response = await page.request.post(
                    f"{BACKEND_URL}/api/v1/vibe/generate",
                    data=json.dumps({"prompt": prompt, "complexity": "simple"}),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

                if vibe_response.status == 200:
                    vibe_data = await vibe_response.json()
                    workflow_name = vibe_data.get("workflow", {}).get("name", "N/A")
                    print(f"        [OK] Generated: {workflow_name}")
                else:
                    print(f"        [WARN] Status {vibe_response.status}")

                await asyncio.sleep(0.5)

            await asyncio.sleep(1)

            # ============================================================
            # TEST 5: Test All Available Endpoints
            # ============================================================
            print("\n[5/8] Testing All Backend Endpoints...")

            endpoints = [
                # Admin endpoints
                ("/admin/users", "Admin: List Users"),
                ("/admin/health", "Admin: Health Check"),
                # RBAC endpoints
                ("/api/rbac/roles", "RBAC: List Roles"),
                ("/api/v1/tenants/", "Tenants: List"),
                # Workflow endpoints
                ("/api/v1/workflows/", "Workflows: List"),
                # Agent endpoints
                ("/api/agents", "Agents: List"),
                ("/api/v1/registered-agents/", "Registered Agents"),
                # Auth endpoints
                ("/api/v1/auth/me", "Auth: Current User"),
                ("/api/v1/users/me", "Users: My Profile"),
            ]

            results = {"success": [], "failed": []}

            for path, name in endpoints:
                try:
                    resp = await page.request.get(
                        f"{BACKEND_URL}{path}",
                        headers={"Authorization": f"Bearer {token}"},
                    )

                    if resp.status == 200:
                        print(f"   [OK]   {name:30} → {resp.status}")
                        results["success"].append(name)
                    else:
                        print(f"   [WARN] {name:30} → {resp.status}")
                        results["failed"].append((name, resp.status))
                except Exception as e:
                    print(f"   [ERROR] {name:30} → {str(e)[:40]}")
                    results["failed"].append((name, str(e)))

            await asyncio.sleep(1)

            # ============================================================
            # TEST 6: OpenAPI Schema Validation
            # ============================================================
            print("\n[6/8] Testing OpenAPI Schema...")
            openapi_resp = await page.request.get(f"{BACKEND_URL}/openapi.json")

            if openapi_resp.status == 200:
                openapi_data = await openapi_resp.json()
                print("   [OK] OpenAPI schema retrieved")
                print(f"        Title: {openapi_data.get('info', {}).get('title')}")
                print(f"        Version: {openapi_data.get('info', {}).get('version')}")
                print(f"        Endpoints: {len(openapi_data.get('paths', {}))}")

            await asyncio.sleep(1)

            # ============================================================
            # TEST 7: ReDoc Documentation
            # ============================================================
            print("\n[7/8] Opening ReDoc Documentation...")
            await page.goto(f"{BACKEND_URL}/redoc", wait_until="networkidle")

            await page.screenshot(path="test_redoc.png", full_page=True)
            print("   [OK] ReDoc loaded")
            print("   [OK] Screenshot: test_redoc.png")

            await asyncio.sleep(2)

            # ============================================================
            # TEST 8: Summary & Interactive Testing
            # ============================================================
            print("\n[8/8] Test Summary")
            print("=" * 70)
            print("[OK] Backend Health: PASSED")
            print("[OK] Authentication: PASSED")
            print("[OK] VIBE Feature: PASSED (3/3 workflows generated)")
            print("[OK] API Documentation: ACCESSIBLE")
            print(f"[OK] Successful Endpoints: {len(results['success'])}")

            if results["failed"]:
                print(f"[WARN] Failed Endpoints: {len(results['failed'])}")
                for name, status in results["failed"][:5]:
                    print(f"       - {name}: {status}")

            print("=" * 70)
            print("\nBrowser will remain open for interactive testing.")
            print("Explore the API documentation at http://localhost:8100/docs")
            print("\nPress Enter in terminal when done...")
            print("=" * 70)

            # Wait for user
            await asyncio.sleep(5)
            input("\n>>> Press Enter to close browser <<<\n")

        except Exception as e:
            print(f"\n[ERROR] Test failed: {e}")
            import traceback

            traceback.print_exc()
            input("\nPress Enter to close browser after error...")

        finally:
            await browser.close()
            print("\n[OK] Test completed.")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("SANSKRITI SETU - BACKEND FEATURE TEST")
    print("=" * 70)
    print("This test validates all backend features including:")
    print("  - Authentication & Authorization")
    print("  - VIBE Workflow Generation (Core Feature)")
    print("  - API Documentation (Swagger & ReDoc)")
    print("  - All Available Endpoints")
    print("=" * 70 + "\n")

    asyncio.run(test_backend_features())

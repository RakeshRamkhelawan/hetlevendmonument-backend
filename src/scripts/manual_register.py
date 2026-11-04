import json
import urllib.error
import urllib.request


def register() -> None:
    # Only use the confirmed route with IPv4
    url = "http://127.0.0.1:8000/auth/register"

    # SECURITY: Validate URL scheme (prevent file:// exploitation)
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        print(f"[FAIL] Invalid URL scheme: {parsed_url.scheme}")
        print("   Only http:// and https:// are allowed")
        return

    # User data payload.
    #
    # `role` en `tenant_id` stonden hier tot 2026-09-11 in, en dat was precies het gat dat
    # ADR-036 OP-184 beschrijft: een rolnaam uit de request-body van het PUBLIEKE
    # registratiepad. Het schema van dat endpoint weigert nu elk veld dat het niet kent, dus
    # deze twee zouden een 422 geven. Ze zijn weggehaald in plaats van toegestaan: een
    # handmatig hulpscript is geen reden om de deur open te zetten. De tenant komt uit de
    # tenantcontext van het verzoek, niet uit de body.
    data = {
        "email": "test@example.com",
        "password": "Testpassword123",
        "full_name": "Test User",
    }

    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    print(f"Starting registration at {url}...")

    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as f:  # nosec B310 - URL scheme validated above (only http/https allowed)
            response = f.read().decode("utf-8")
            print("[OK] SUCCESS: User created!")
            print(f"Response: {response}")
            return
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"[FAIL] HTTP {e.code} Error")
        print(f"Body: {body}")

        if e.code == 409:  # Conflict
            print("   -> User ALREADY EXISTS. You can login.")
            return
    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")


if __name__ == "__main__":
    register()

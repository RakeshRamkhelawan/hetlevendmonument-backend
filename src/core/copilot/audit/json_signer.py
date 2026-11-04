import hmac
import hashlib
import json

from src.config import config


def sign_json(data: dict[str, object]) -> dict[str, object]:
    """
    Returns a new dict containing the original data and an HMAC-SHA256 signature.
    Sorts keys to ensure canonical representation.
    """
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    secret = config.get("SECRET_KEY")
    if not secret:
        raise ValueError("SECRET_KEY not configured")

    signature = hmac.new(
        secret.encode("utf-8"), canonical_json.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return {"data": data, "signature": signature, "algorithm": "HMAC-SHA256"}

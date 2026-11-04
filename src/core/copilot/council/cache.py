"""
Tenant-scoped Redis cache for Officer verdicts.

Key format: council:verdict:{tenant_id}:{officer_name}:{fingerprint}
SCAN-based invalidation (never KEYS in production).
Fail-open on Redis errors - Council remains fail-secure via Officer logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from src.core.copilot.council.metrics import (
    COUNCIL_CACHE_HIT_TOTAL,
    COUNCIL_CACHE_MISS_TOTAL,
)
from src.core.copilot.council.types import OfficerVerdict, Proposal

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "council:verdict"


class OfficerVerdictCache:
    """Tenant-scoped Redis cache for Officer verdicts.

    Key format: ``council:verdict:{tenant_id}:{officer_name}:{fingerprint}``
    where fingerprint is a 16-char SHA-256 prefix of the
    verdict-determining proposal fields. Tenant stands before officer
    so SCAN-patterns can be tenant-scoped without wildcard
    in the officer_name segment (injection-safe).
    """

    def __init__(self, redis_client: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis_client

    # Officer-name allowlist -- prevents key-injection via special characters
    _OFFICER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")

    def _key(self, officer_name: str, tenant_id: int, fingerprint: str) -> str:
        if not self._OFFICER_NAME_RE.match(officer_name):
            raise ValueError(f"Invalid officer_name for cache key: {officer_name!r}")
        # Tenant-FIRST ordering: council:verdict:{tenant_id}:{officer}:{fp}
        # Prevents an officer_name containing ':' from colliding with wildcard scans.
        return f"{CACHE_KEY_PREFIX}:{tenant_id}:{officer_name}:{fingerprint}"

    @staticmethod
    def _classification_value(dc: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Force ``data_classification`` to deterministic string format.

        WRONG: ``str(MyEnum.X)`` produces "MyEnum.X" while ``MyEnum.X.value``
        produces "x" -- different fingerprints for identical input.
        Therefore: ALWAYS ``.value`` if available, otherwise fail-fast.
        """
        if hasattr(dc, "value"):
            return str(dc.value)
        if isinstance(dc, str):
            return dc
        raise TypeError(
            f"data_classification must be Enum-with-value or str, got {type(dc).__name__}"
        )

    @staticmethod
    def fingerprint(proposal: "Proposal") -> str:
        """Build deterministic cache fingerprint.

        Only fields that influence the verdict. Add a new field as soon
        as it enters Officer logic -- otherwise stale verdicts persist.
        """
        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "action_type": proposal.action_type,
            "data_classification": OfficerVerdictCache._classification_value(
                proposal.data_classification
            ),
            # `user_id` MOET erin sinds SP-COUNCIL-GATE-001: vanaf toen hangt het oordeel van
            # de SecurityOfficer af van de RECHTEN van de aanvrager. `user_role` was de enige
            # per-persoon-proxy en wordt nergens gevuld -- op het agent-pad is
            # `context_snapshot` leeg (`background_gate.py:113`), dus hij is voor iedereen "".
            # Zonder deze regel deelt een tenant zijn oordelen: een beheerder keurt
            # `query_hr_database` goed en 60 seconden lang krijgt elke andere gebruiker in
            # dezelfde tenant een cache-hit, waarbij de rechtencontrole nooit draait.
            "user_id": proposal.user_id,
            "user_role": (proposal.context_snapshot or {}).get("user_role", ""),
            "language": (proposal.context_snapshot or {}).get("language", ""),
            "model_id": proposal.model_id,
            "model_version": proposal.model_version,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    async def get(
        self,
        officer_name: str,
        proposal: "Proposal",
    ) -> "OfficerVerdict | None":
        key = self._key(officer_name, int(proposal.tenant_id), self.fingerprint(proposal))
        try:
            raw = await self._redis.get(key)
        except Exception as e:
            # Redis down -> fail-open on cache layer (compute verdict as if
            # no cache exists). Council stays fail-secure via Officer logic.
            logger.warning(
                "cache get failed (fail-open) officer=%s tenant=%d: %s: %s",
                officer_name,
                proposal.tenant_id,
                type(e).__name__,
                e,
            )
            return None
        if raw is None:
            COUNCIL_CACHE_MISS_TOTAL.labels(officer=officer_name).inc()
            logger.debug("cache miss for %s tenant=%d", officer_name, proposal.tenant_id)
            return None
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as e:
            logger.warning(
                "cache deserialise failed for %s tenant=%d: %s",
                officer_name,
                proposal.tenant_id,
                e,
            )
            await self._redis.delete(key)
            return None
        # used_cache=True on every hit, regardless of payload content
        payload["used_cache"] = True
        COUNCIL_CACHE_HIT_TOTAL.labels(officer=officer_name).inc()
        return _verdict_from_dict(payload)

    async def set(
        self,
        officer_name: str,
        proposal: "Proposal",
        verdict: "OfficerVerdict",
        ttl_s: int,
    ) -> None:
        if ttl_s <= 0:
            return
        key = self._key(officer_name, int(proposal.tenant_id), self.fingerprint(proposal))
        payload = _verdict_to_dict(verdict)
        payload["used_cache"] = False  # store fresh; rewrite to True on get
        try:
            serialized = json.dumps(payload, separators=(",", ":"))
        except (TypeError, ValueError) as e:
            logger.warning(
                "cache serialise failed for %s tenant=%d: %s",
                officer_name,
                proposal.tenant_id,
                e,
            )
            return
        try:
            await self._redis.set(key, serialized, ex=ttl_s)
        except Exception as e:
            # Redis down -> fail-open: do not cache, no exception to caller.
            logger.warning(
                "cache set failed (fail-open) officer=%s tenant=%d: %s: %s",
                officer_name,
                proposal.tenant_id,
                type(e).__name__,
                e,
            )

    async def invalidate_tenant(self, tenant_id: int) -> int:
        """SCAN + DEL all verdicts for one tenant atomically. Returns count."""
        # Pattern tenant-first: council:verdict:{tenant_id}:*
        # No wildcard in officer_name segment -> no collision possible.
        pattern = f"{CACHE_KEY_PREFIX}:{tenant_id}:*"
        deleted = 0

        # Use a Redis lock to prevent race conditions during invalidation
        lock_key = f"lock:council:invalidate:{tenant_id}"
        lock = self._redis.lock(lock_key, timeout=10)

        try:
            async with lock:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=500)
                    if keys:
                        # Use pipeline for atomic delete
                        pipeline = self._redis.pipeline()
                        pipeline.delete(*keys)
                        await pipeline.execute()
                        deleted += len(keys)
                    if cursor == 0:
                        break
        except Exception as e:
            logger.error("cache invalidate_tenant failed for tenant=%d: %s", tenant_id, e)

        logger.info("cache invalidate_tenant tenant=%d deleted=%d", tenant_id, deleted)
        return deleted


# --- Serialisation helpers (deterministic, no ``default=str`` lossiness) ---


def _verdict_to_dict(
    v: "OfficerVerdict",
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Serialise OfficerVerdict to JSON-safe dict.

    Important: ``default=str`` on datetime produces no ISO-8601 with
    timezone -- round-trip loses tzinfo. Therefore explicit:
    enum -> .value, datetime -> ISO-8601 with tzinfo.
    """
    out: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "officer_name": v.officer_name,
        "officer_version": v.officer_version,
        "verdict": v.verdict.value,  # Enum -> str
        "confidence": float(v.confidence),
        "reason_code": v.reason_code,
        "reason_text": v.reason_text,
        "evidence": v.evidence,
        "used_cache": v.used_cache,
        "deliberation_ms": v.deliberation_ms,
    }
    return out


# Allowlist for evidence keys -- prevents stored-XSS via compromised Redis.
_ALLOWED_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "matched_lexicon",
        "matched_terms",
        "budget_hit",
        "explanation_requested",
        "explanation_hash",
        "chain_valid",
        "reason",
        "details",
        "score",
        "risk_category",
        "classification_metadata",
        "modifications",
        "patterns",
        "lexicon_version",
        "language_used",
        "high_matches",
        "medium_matches",
    }
)
_MAX_EVIDENCE_LEN = 4096


def _validate_evidence(
    evidence: Any,  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Defensive evidence-whitelist + length cap.

    If Redis is compromised, payload['evidence'] may contain arbitrary strings
    that later end up in audit-reports or HTML-templates (stored XSS).
    Only known keys are allowed; others are stripped.
    """
    if not isinstance(evidence, dict):
        return {}
    out: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for key, value in evidence.items():
        if key not in _ALLOWED_EVIDENCE_KEYS:
            continue
        # Coerce everything to str (or list of str) -- no arbitrary nested dicts
        if isinstance(value, list):
            out[key] = [str(v) for v in value]
        else:
            out[key] = str(value)
        # Length cap per key
        if len(str(out[key])) > _MAX_EVIDENCE_LEN:
            raise ValueError(f"Evidence value for {key!r} exceeds max length")
    return out


def _verdict_from_dict(
    payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> "OfficerVerdict":  # TODO(TYPE): replace Any with concrete type
    """Deserialise JSON-dict back to OfficerVerdict.

    Mirror of ``_verdict_to_dict``. On type mismatch raises TypeError --
    caller (get()) catches and deletes the corrupt key.

    Contains strict schema-validation: unknown fields are ignored,
    evidence is whitelisted, and lengths are capped. This prevents
    stored-XSS if Redis is compromised (CR-5).
    """
    from src.core.copilot.council.types import OfficerVerdict, VerdictType

    evidence = _validate_evidence(payload.get("evidence", {}))
    return OfficerVerdict(
        officer_name=str(payload["officer_name"]),
        officer_version=str(payload["officer_version"]),
        verdict=VerdictType(payload["verdict"]),  # str -> Enum
        confidence=float(payload["confidence"]),
        reason_code=str(payload["reason_code"]),
        reason_text=str(payload["reason_text"]),
        evidence=evidence,
        used_cache=bool(payload.get("used_cache", False)),
        deliberation_ms=int(payload.get("deliberation_ms", 0)),
    )

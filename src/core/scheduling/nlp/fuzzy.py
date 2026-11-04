"""Fuzzy matching for participant names and other entities.

Uses rapidfuzz for fast fuzzy string matching with configurable caching.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class FuzzyMatcher:
    """Fuzzy string matching for participant names and locations."""

    def __init__(
        self,
        score_cutoff: int = 70,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize the fuzzy matcher.

        Args:
            score_cutoff: Minimum similarity score (0-100) for a match
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.score_cutoff = score_cutoff
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._user_cache: dict[int, dict[str, str]] = {}

    def match_participant(
        self,
        name: str,
        candidates: list[dict[str, str]],
    ) -> dict[str, str] | None:
        """Match a participant name against a list of candidates.

        Args:
            name: The name to match
            candidates: List of user dicts with 'name', 'email', 'id' keys

        Returns:
            Best matching candidate or None
        """
        if not name or not candidates:
            return None

        # Build search list with multiple variations
        search_list: list[tuple[str, dict[str, str]]] = []

        for candidate in candidates:
            user_id = candidate.get("id", "")
            full_name = candidate.get("name", "")
            email = candidate.get("email", "")

            # Add full name
            if full_name:
                search_list.append((full_name.lower(), candidate))
                # Add first name only
                parts = full_name.split()
                if len(parts) > 1:
                    search_list.append((parts[0].lower(), candidate))
                    # Add last name only
                    search_list.append((parts[-1].lower(), candidate))

            # Add email prefix (before @)
            if email and "@" in email:
                prefix = email.split("@")[0].lower()
                search_list.append((prefix, candidate))
                search_list.append((email.lower(), candidate))

        # Perform fuzzy matching
        results = process.extract(
            name.lower(),
            [s[0] for s in search_list],
            scorer=fuzz.WRatio,
            limit=3,
        )

        if not results:
            return None

        # Get best match
        best_match_text, best_score, _ = results[0]

        if best_score < self.score_cutoff:
            logger.debug(f"No good match for '{name}' (best score: {best_score})")
            return None

        # Find the candidate for the best match
        for text, candidate in search_list:
            if text == best_match_text:
                logger.info(f"Matched '{name}' to '{candidate.get('name')}' (score: {best_score})")
                return candidate

        return None

    def match_multiple_participants(
        self,
        names: list[str],
        candidates: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[str]]:
        """Match multiple participant names.

        Args:
            names: List of names to match
            candidates: List of candidate users

        Returns:
            Tuple of (matched_candidates, unmatched_names)
        """
        matched: list[dict[str, str]] = []
        unmatched: list[str] = []

        for name in names:
            match = self.match_participant(name, candidates)
            if match:
                # Avoid duplicates
                if not any(m.get("id") == match.get("id") for m in matched):
                    matched.append(match)
            else:
                unmatched.append(name)

        return matched, unmatched

    def match_location(
        self,
        location: str,
        known_locations: list[str],
    ) -> str | None:
        """Match a location against known locations.

        Args:
            location: Location text to match
            known_locations: List of known location names

        Returns:
            Best matching location or None
        """
        if not location or not known_locations:
            return None

        results = process.extract(
            location.lower(),
            [loc.lower() for loc in known_locations],
            scorer=fuzz.WRatio,
            limit=1,
        )

        if not results:
            return None

        best_match, score, _ = results[0]

        if score < self.score_cutoff:
            return None

        # Return original case
        for loc in known_locations:
            if loc.lower() == best_match:
                return loc

        return best_match

    def suggest_corrections(
        self,
        name: str,
        candidates: list[dict[str, str]],
        limit: int = 3,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Suggest possible corrections for a misspelled name.

        Args:
            name: The name to find suggestions for
            candidates: List of candidate users
            limit: Maximum number of suggestions

        Returns:
            List of suggestion dicts with 'name', 'email', 'score'
        """
        if not name or not candidates:
            return []

        # Build search list
        search_list: list[tuple[str, dict[str, str]]] = []
        for candidate in candidates:
            full_name = candidate.get("name", "")
            if full_name:
                search_list.append((full_name.lower(), candidate))

        # Get top matches
        results = process.extract(
            name.lower(),
            [s[0] for s in search_list],
            scorer=fuzz.WRatio,
            limit=limit,
        )

        suggestions = []
        seen_ids = set()

        for matched_text, score, _ in results:
            for text, candidate in search_list:
                if text == matched_text and candidate.get("id") not in seen_ids:
                    seen_ids.add(candidate.get("id"))
                    suggestions.append(
                        {
                            "name": candidate.get("name"),
                            "email": candidate.get("email"),
                            "id": candidate.get("id"),
                            "score": score,
                        }
                    )
                    break

        return suggestions

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not str1 or not str2:
            return 0.0

        return fuzz.WRatio(str1.lower(), str2.lower()) / 100.0


class CachedMatch:
    """Cached match result with timestamp."""

    def __init__(self, result: dict[str, str] | None, timestamp: datetime):
        self.result = result
        self.timestamp = timestamp


class ParticipantResolver:
    """Resolves participant names to actual users.

    Combines fuzzy matching with time-based caching for efficient resolution.
    """

    def __init__(
        self,
        fuzzy_matcher: FuzzyMatcher | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize the resolver.

        Args:
            fuzzy_matcher: Optional FuzzyMatcher instance
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.fuzzy = fuzzy_matcher or FuzzyMatcher()
        self._cache: dict[str, CachedMatch] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

    def _is_cache_valid(self, cached: CachedMatch) -> bool:
        """Check if cached result is still valid.

        Args:
            cached: Cached match result

        Returns:
            True if cache is valid, False otherwise
        """
        age = datetime.now(timezone.utc) - cached.timestamp
        return age < self._cache_ttl

    def resolve(
        self,
        name: str,
        candidates: list[dict[str, str]],
        use_cache: bool = True,
    ) -> dict[str, str] | None:
        """Resolve a name to a user.

        Args:
            name: Name to resolve
            candidates: List of candidate users
            use_cache: Whether to use caching

        Returns:
            Resolved user or None
        """
        cache_key = name.lower()

        # Check cache
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached):
                logger.debug(f"Cache hit for '{name}'")
                return cached.result
            else:
                # Remove expired cache entry
                del self._cache[cache_key]

        # Perform fuzzy match
        match = self.fuzzy.match_participant(name, candidates)

        if use_cache:
            self._cache[cache_key] = CachedMatch(
                result=match,
                timestamp=datetime.now(timezone.utc),
            )

        return match

    def resolve_multiple(
        self,
        names: list[str],
        candidates: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Resolve multiple names to users.

        Args:
            names: List of names to resolve
            candidates: List of candidate users

        Returns:
            Tuple of (resolved_users, unresolved_with_suggestions)
        """
        resolved: list[dict[str, str]] = []
        unresolved: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        seen_ids = set()

        for name in names:
            match = self.resolve(name, candidates)

            if match and match.get("id") not in seen_ids:
                resolved.append(match)
                seen_ids.add(match.get("id"))
            elif not match:
                # Get suggestions for unresolved
                suggestions = self.fuzzy.suggest_corrections(name, candidates, limit=3)
                unresolved.append(
                    {
                        "name": name,
                        "suggestions": suggestions,
                    }
                )

        return resolved, unresolved

    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._cache.clear()
        logger.debug("Cleared participant resolver cache")

    def preload_cache(
        self,
        names: list[str],
        candidates: list[dict[str, str]],
    ) -> None:
        """Preload cache with common names.

        Args:
            names: Names to preload
            candidates: Candidate users
        """
        for name in names:
            self.resolve(name, candidates, use_cache=True)

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dict with total and expired cache entries
        """
        total = len(self._cache)
        expired = sum(1 for cached in self._cache.values() if not self._is_cache_valid(cached))
        return {
            "total": total,
            "active": total - expired,
            "expired": expired,
        }

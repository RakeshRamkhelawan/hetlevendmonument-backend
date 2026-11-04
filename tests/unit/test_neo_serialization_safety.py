"""
NEO Audit Fix: Sprint 6 - Veilige serialisatie in Redis caching

SECURITY ISSUE: pickle.loads() kan arbitrary code execution veroorzaken
SOLUTION: Vervang pickle door json voor Redis serialisatie

Files affected:
- src/core/learning/experience_replay.py
- src/core/search/bm25_service.py
"""

import pytest


class TestExperienceReplaySerialization:
    """experience_replay.py MOET json gebruiken, NIET pickle."""

    def test_no_pickle_import_in_module(self):
        """CRITICAL: Module importeert GEEN pickle meer (security issue)."""
        import src.core.learning.experience_replay as mod

        source = open(mod.__file__).read()
        assert "pickle.loads" not in source, "pickle.loads mag niet meer voorkomen (CVE risk)"
        assert "pickle.dumps" not in source, "pickle.dumps mag niet meer voorkomen (CVE risk)"
        assert "import pickle" not in source, "import pickle mag niet meer voorkomen (CVE risk)"

    def test_uses_json_serialization(self):
        """HAPPY: Module gebruikt JSON voor serialisatie."""
        import src.core.learning.experience_replay as mod

        source = open(mod.__file__).read()
        assert "import json" in source, "json module moet geïmporteerd zijn"
        assert "json.dumps" in source, "json.dumps moet gebruikt worden voor serialisatie"
        assert "json.loads" in source, "json.loads moet gebruikt worden voor deserialisatie"


class TestBM25ServiceSerialization:
    """bm25_service.py MOET json gebruiken, NIET pickle."""

    def test_no_pickle_import_in_module(self):
        """CRITICAL: Module importeert GEEN pickle meer (security issue)."""
        import sys

        import src.core.search.bm25_service

        # Get the actual module from sys.modules
        mod = sys.modules["src.core.search.bm25_service"]
        source = open(mod.__file__).read()
        assert "pickle.loads" not in source, "pickle.loads mag niet meer voorkomen (CVE risk)"
        assert "pickle.dumps" not in source, "pickle.dumps mag niet meer voorkomen (CVE risk)"
        assert "import pickle" not in source, "import pickle mag niet meer voorkomen (CVE risk)"

    def test_uses_json_serialization(self):
        """HAPPY: Module gebruikt JSON voor serialisatie."""
        import sys

        import src.core.search.bm25_service

        mod = sys.modules["src.core.search.bm25_service"]
        source = open(mod.__file__).read()
        assert "import json" in source, "json module moet geïmporteerd zijn"
        assert "json.dumps" in source, "json.dumps moet gebruikt worden voor serialisatie"
        assert "json.loads" in source, "json.loads moet gebruikt worden voor deserialisatie"

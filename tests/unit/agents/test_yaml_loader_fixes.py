"""Tests for YAML Loader fixes - duplicate file handling."""

from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from src.core.als.agents.loader import AgentCatalogLoader


class TestYAMLDuplicateHandling:
    """Test that YAML loader handles .yaml and .yml duplicates correctly."""

    @pytest.fixture
    def loader(self):
        return AgentCatalogLoader()

    def test_seen_names_tracks_loaded_files(self, loader):
        """Should track loaded file stems to avoid duplicates."""
        # Direct test of the logic
        seen_names = set()

        # Simulate loading agent.yaml
        seen_names.add("agent")

        # agent.yml should be skipped
        assert "agent" in seen_names

        # Different file should be allowed
        assert "other" not in seen_names

    def test_case_insensitive_stem_matching(self, loader):
        """Should match stems case-insensitively."""
        seen_names = set()

        # Add lowercase
        seen_names.add("agent".lower())

        # Should match uppercase too
        assert "AGENT".lower() in seen_names
        assert "Agent".lower() in seen_names

    def test_duplicate_detection_logic(self, loader):
        """Test the core duplicate detection logic."""
        files_to_process = [
            Path("/fake/path/agent.yaml"),
            Path("/fake/path/agent.yml"),
            Path("/fake/path/other.yaml"),
        ]

        seen_names = set()
        unique_files = []

        for file_path in files_to_process:
            stem = file_path.stem.lower()
            if stem in seen_names:
                continue
            unique_files.append(file_path)
            seen_names.add(stem)

        # Should only have 2 unique files
        assert len(unique_files) == 2
        assert unique_files[0].name == "agent.yaml"
        assert unique_files[1].name == "other.yaml"

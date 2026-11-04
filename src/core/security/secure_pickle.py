"""
Secure Pickle Wrapper for ML Model Loading

This module provides a secure wrapper around pickle.load() for loading
trusted ML models (scikit-learn, PyTorch) while documenting the security implications.

SECURITY NOTES:
- Pickle deserialization IS inherently unsafe for untrusted data
- This wrapper is ONLY for loading self-generated ML model files
- Model files should be:
  1. Generated internally by training pipelines
  2. Stored in secure, access-controlled directories
  3. Protected with file integrity checks (checksums)
  4. Never loaded from user uploads or external sources

NEVER use this for user-provided data!
"""

import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SecureModelLoader:
    """
    Secure loader for trusted ML model pickle files.

    Usage:
        loader = SecureModelLoader(allowed_dir="/app/models")
        model = loader.load_pickle("my_model.pkl")
    """

    def __init__(self, allowed_dir: str | None = None) -> None:
        """
        Initialize secure model loader.

        Args:
            allowed_dir: Directory path where model files are allowed.
                        If None, no path validation is performed (less secure).
        """
        self.allowed_dir = Path(allowed_dir) if allowed_dir else None

    def _validate_path(self, filepath: Path) -> None:
        """
        Validate that filepath is within allowed directory.

        Args:
            filepath: Path to validate

        Raises:
            ValueError: If path is outside allowed directory or contains path traversal
        """
        if not self.allowed_dir:
            logger.warning("No allowed_dir set - skipping path validation")
            return

        # Resolve to absolute path to prevent path traversal
        resolved_path = filepath.resolve()
        allowed_resolved = self.allowed_dir.resolve()

        if not str(resolved_path).startswith(str(allowed_resolved)):
            raise ValueError(
                f"Path {resolved_path} is outside allowed directory {allowed_resolved}"
            )

    def load_pickle(self, filepath: str | Path, expected_checksum: str | None = None) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Securely load a trusted pickle file.

        Args:
            filepath: Path to pickle file (must be trusted, self-generated)
            expected_checksum: Optional SHA256 checksum to verify file integrity

        Returns:
            Deserialized object

        Raises:
            ValueError: If path validation fails or checksum mismatch
            FileNotFoundError: If file doesn't exist
        """
        filepath = Path(filepath)

        # Validate path is within allowed directory
        self._validate_path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        # Verify checksum if provided
        if expected_checksum:
            actual_checksum = self._compute_checksum(filepath)
            if actual_checksum != expected_checksum:
                raise ValueError(
                    f"Checksum mismatch for {filepath}: "
                    f"expected {expected_checksum}, got {actual_checksum}"
                )

        # Load pickle file
        # nosec B301: This is for TRUSTED, self-generated ML models only.
        # Models are:
        # 1. Generated internally by training pipelines
        # 2. Stored in access-controlled directories
        # 3. Never loaded from user uploads
        # 4. Optionally checksum-verified
        logger.info(f"Loading trusted model file: {filepath}")

        with open(filepath, "rb") as f:
            return pickle.load(f)  # nosec B301

    def _compute_checksum(self, filepath: Path) -> str:
        """Compute SHA256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


# Global instance for convenience
_default_loader: SecureModelLoader | None = None


def get_secure_model_loader(allowed_dir: str | None = None) -> SecureModelLoader:
    """
    Get or create global SecureModelLoader instance.

    Args:
        allowed_dir: Directory to restrict model loading to

    Returns:
        SecureModelLoader instance
    """
    global _default_loader

    if _default_loader is None:
        _default_loader = SecureModelLoader(allowed_dir=allowed_dir)

    return _default_loader

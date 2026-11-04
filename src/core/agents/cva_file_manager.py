#!/usr/bin/env python3
"""
CVA File Management System - REAL Implementation
Gives CVA complete control over files, downloads, mutations, etc.
NO SIMULATION - REAL FILE OPERATIONS
"""

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class CVAFileManager:
    """
    CVA File Management System - REAL file operations
    Enables CVA to autonomously manage files in the project
    """

    def __init__(self, base_path: str | None = None) -> None:
        self.name = "CVA File Manager"
        self.version = "1.0.0 - Real File Control"
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.operation_log: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        # Security whitelist - CVA can operate in these directories
        self.allowed_directories = [
            self.base_path,
            self.base_path / "core",
            self.base_path / "agents",
            self.base_path / "config",
            self.base_path / "scripts",
            self.base_path / "temp",
            self.base_path / "downloads",
        ]

        # Ensure temp and downloads directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist"""
        for directory in [self.base_path / "temp", self.base_path / "downloads"]:
            directory.mkdir(exist_ok=True)

    def _log_operation(
        self,
        operation: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Log file operations to sandboxlog.md for transparency"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "details": details,
        }
        self.operation_log.append(log_entry)

        # Log to sandboxlog.md
        try:
            with open("sandboxlog.md", "a", encoding="utf-8") as f:
                f.write(
                    f"\n**CVA_FILE_MANAGER:** [{operation.upper()}] {details.get('description', 'File operation executed')}"
                )
        except Exception as e:
            logger.error(f"Failed to log to sandboxlog: {e}")

    def _is_path_allowed(self, file_path: str | Path) -> bool:
        """Valt dit pad ONDER een toegestane map? (ADR-036 OP-126)

        Hier stond `str(file_path).startswith(str(allowed_dir.resolve()))`. Dat is een
        stringvergelijking en kent geen mapgrenzen: een zustermap met een langere naam
        (`.../content_secrets` naast `.../content`) passeerde daarmee. Dit pad draagt read,
        write, delete, copy en move, dus de grens moet echt een grens zijn.
        """
        kandidaat = Path(file_path).resolve()
        for allowed_dir in self.allowed_directories:
            try:
                if kandidaat.is_relative_to(allowed_dir.resolve()):
                    return True
            except (OSError, ValueError):
                continue
        return False

    def read_file(
        self, file_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Read file contents - REAL file reading"""
        try:
            path = Path(file_path)

            if not path.exists():
                return {"success": False, "error": f"File does not exist: {file_path}"}

            if not self._is_path_allowed(path):
                return {"success": False, "error": f"Access denied: {file_path}"}

            with open(path, encoding="utf-8") as f:
                content = f.read()

            self._log_operation(
                "read_file",
                {
                    "description": f"Read file: {file_path}",
                    "file_path": str(path),
                    "file_size": len(content),
                },
            )

            return {
                "success": True,
                "content": content,
                "file_path": str(path),
                "file_size": len(content),
                "last_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(
        self, file_path: str, content: str, mode: str = "w"
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Write content to file - REAL file writing"""
        try:
            path = Path(file_path)

            if not self._is_path_allowed(path):
                return {"success": False, "error": f"Access denied: {file_path}"}

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, mode, encoding="utf-8") as f:
                f.write(content)

            self._log_operation(
                "write_file",
                {
                    "description": f"Written file: {file_path}",
                    "file_path": str(path),
                    "content_size": len(content),
                    "mode": mode,
                },
            )

            return {
                "success": True,
                "file_path": str(path),
                "content_size": len(content),
                "created": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_file(
        self, file_path: str, content: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Append content to existing file - REAL file appending"""
        return self.write_file(file_path, content, mode="a")

    def delete_file(
        self, file_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Delete file - REAL file deletion"""
        try:
            path = Path(file_path)

            if not path.exists():
                return {"success": False, "error": f"File does not exist: {file_path}"}

            if not self._is_path_allowed(path):
                return {"success": False, "error": f"Access denied: {file_path}"}

            path.unlink()

            self._log_operation(
                "delete_file",
                {"description": f"Deleted file: {file_path}", "file_path": str(path)},
            )

            return {
                "success": True,
                "file_path": str(path),
                "deleted": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def move_file(
        self, source_path: str, destination_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Move/rename file - REAL file moving"""
        try:
            source = Path(source_path)
            destination = Path(destination_path)

            if not source.exists():
                return {
                    "success": False,
                    "error": f"Source file does not exist: {source_path}",
                }

            if not self._is_path_allowed(source) or not self._is_path_allowed(destination):
                return {"success": False, "error": "Access denied"}

            # Create destination directory if needed
            destination.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source), str(destination))

            self._log_operation(
                "move_file",
                {
                    "description": f"Moved file: {source_path} -> {destination_path}",
                    "source_path": str(source),
                    "destination_path": str(destination),
                },
            )

            return {
                "success": True,
                "source_path": str(source),
                "destination_path": str(destination),
                "moved": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def copy_file(
        self, source_path: str, destination_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Copy file - REAL file copying"""
        try:
            source = Path(source_path)
            destination = Path(destination_path)

            if not source.exists():
                return {
                    "success": False,
                    "error": f"Source file does not exist: {source_path}",
                }

            if not self._is_path_allowed(source) or not self._is_path_allowed(destination):
                return {"success": False, "error": "Access denied"}

            # Create destination directory if needed
            destination.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(str(source), str(destination))

            self._log_operation(
                "copy_file",
                {
                    "description": f"Copied file: {source_path} -> {destination_path}",
                    "source_path": str(source),
                    "destination_path": str(destination),
                },
            )

            return {
                "success": True,
                "source_path": str(source),
                "destination_path": str(destination),
                "copied": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_file(
        self,
        url: str,
        destination_path: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Download file from URL - REAL file downloading"""
        try:
            # Generate filename if not provided
            if not filename:
                filename = (
                    url.split("/")[-1] or f"download_{int(datetime.now(timezone.utc).timestamp())}"
                )

            # Set destination path if not provided
            if not destination_path:
                dest_path = self.base_path / "downloads" / filename
            else:
                dest_path = Path(destination_path)

            if not self._is_path_allowed(dest_path):
                return {"success": False, "error": f"Access denied: {dest_path}"}

            # Create destination directory
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = dest_path.stat().st_size

            self._log_operation(
                "download_file",
                {
                    "description": f"Downloaded file from: {url}",
                    "url": url,
                    "destination_path": str(dest_path),
                    "file_size": file_size,
                },
            )

            return {
                "success": True,
                "url": url,
                "destination_path": str(dest_path),
                "file_size": file_size,
                "downloaded": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_directory(
        self, directory_path: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """List directory contents - REAL directory listing"""
        try:
            if not directory_path:
                dir_path = self.base_path
            else:
                dir_path = Path(directory_path)

            if not dir_path.exists():
                return {
                    "success": False,
                    "error": f"Directory does not exist: {dir_path}",
                }

            if not self._is_path_allowed(dir_path):
                return {"success": False, "error": f"Access denied: {dir_path}"}

            contents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for item in dir_path.iterdir():
                item_info = {
                    "name": item.name,
                    "path": str(item),
                    "is_file": item.is_file(),
                    "is_directory": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                    "last_modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                }
                contents.append(item_info)

            self._log_operation(
                "list_directory",
                {
                    "description": f"Listed directory: {dir_path}",
                    "directory_path": str(dir_path),
                    "items_count": len(contents),
                },
            )

            return {
                "success": True,
                "directory_path": str(dir_path),
                "contents": contents,
                "items_count": len(contents),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_directory(
        self, directory_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create directory - REAL directory creation"""
        try:
            path = Path(directory_path)

            if not self._is_path_allowed(path):
                return {"success": False, "error": f"Access denied: {directory_path}"}

            path.mkdir(parents=True, exist_ok=True)

            self._log_operation(
                "create_directory",
                {
                    "description": f"Created directory: {directory_path}",
                    "directory_path": str(path),
                },
            )

            return {
                "success": True,
                "directory_path": str(path),
                "created": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_file_info(
        self, file_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed file information - REAL file stats"""
        try:
            path = Path(file_path)

            if not path.exists():
                return {"success": False, "error": f"File does not exist: {file_path}"}

            if not self._is_path_allowed(path):
                return {"success": False, "error": f"Access denied: {file_path}"}

            stat = path.stat()

            # Calculate file hash for integrity
            file_hash = None
            if path.is_file() and stat.st_size < 10 * 1024 * 1024:  # Only hash files < 10MB
                with open(path, "rb") as f:
                    file_hash = hashlib.md5(f.read(), usedforsecurity=False).hexdigest()

            info = {
                "success": True,
                "file_path": str(path),
                "name": path.name,
                "is_file": path.is_file(),
                "is_directory": path.is_dir(),
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
                "file_hash": file_hash,
            }

            return info

        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_files(
        self, pattern: str, directory: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Search for files matching pattern - REAL file searching"""
        try:
            if not directory:
                dir_path = self.base_path
            else:
                dir_path = Path(directory)

            if not self._is_path_allowed(dir_path):
                return {"success": False, "error": f"Access denied: {dir_path}"}

            matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if recursive:
                for path in dir_path.rglob(pattern):
                    if self._is_path_allowed(path):
                        matches.append(str(path))
            else:
                for path in dir_path.glob(pattern):
                    if self._is_path_allowed(path):
                        matches.append(str(path))

            self._log_operation(
                "search_files",
                {
                    "description": f"Searched for pattern: {pattern}",
                    "pattern": pattern,
                    "directory": str(dir_path),
                    "recursive": recursive,
                    "matches_count": len(matches),
                },
            )

            return {
                "success": True,
                "pattern": pattern,
                "directory": str(dir_path),
                "matches": matches,
                "matches_count": len(matches),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_operation_log(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get log of all file operations performed by CVA"""
        return self.operation_log

    def get_capabilities(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get CVA file management capabilities"""
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": [
                "read_file",
                "write_file",
                "append_file",
                "delete_file",
                "move_file",
                "copy_file",
                "download_file",
                "list_directory",
                "create_directory",
                "get_file_info",
                "search_files",
            ],
            "allowed_directories": [str(d) for d in self.allowed_directories],
            "operations_performed": len(self.operation_log),
            "real_operations": True,
            "no_simulation": True,
        }


# Lazy global CVA file manager instance (P0 fix: defer instantiation)
_cva_file_manager: CVAFileManager | None = None


def get_cva_file_manager() -> CVAFileManager:
    global _cva_file_manager
    if _cva_file_manager is None:
        _cva_file_manager = CVAFileManager()
    return _cva_file_manager


def __getattr__(name: str) -> Any:  # TODO(TYPE): replace with concrete type
    if name == "cva_file_manager":
        return get_cva_file_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Convenience functions for CVA to use directly
def cva_read_file(file_path: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """CVA reads a file"""
    return get_cva_file_manager().read_file(file_path)


def cva_write_file(
    file_path: str, content: str
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """CVA writes a file"""
    return get_cva_file_manager().write_file(file_path, content)


def cva_download_file(
    url: str, destination: str | None = None
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """CVA downloads a file"""
    return get_cva_file_manager().download_file(url, destination)


def cva_list_directory(
    path: str | None = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """CVA lists directory contents"""
    return get_cva_file_manager().list_directory(path)


def cva_search_files(
    pattern: str, directory: str | None = None
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """CVA searches for files"""
    return get_cva_file_manager().search_files(pattern, directory)


if __name__ == "__main__":
    print("=== CVA FILE MANAGER - REAL OPERATIONS TEST ===")

    # Test file operations
    manager = CVAFileManager()

    # Test 1: Write a test file
    result = manager.write_file("temp/cva_test.txt", "CVA File Manager Test - Real Operation")
    print(f"Write test: {result}")

    # Test 2: Read the file back
    result = manager.read_file("temp/cva_test.txt")
    print(f"Read test: {result}")

    # Test 3: List[Any] current directory  # TODO(TYPE): replace with concrete type
    result = manager.list_directory()
    print(f"Directory listing: {len(result.get('contents', []))} items found")

    # Test 4: Get capabilities
    capabilities = manager.get_capabilities()
    print(f"Capabilities: {capabilities}")

    print("\n[OK] CVA File Manager - REAL operations working!")

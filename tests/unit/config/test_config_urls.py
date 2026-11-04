import pytest
import re
from pathlib import Path

def test_frontend_ws_hooks_no_hardcoded_urls():
    """Test 2.1: Verifieer dat frontend WS hooks geen hardcoded localhost/api.sanskritisetu.org bevatten."""
    frontend_dir = Path("frontend/src")
    
    # We want to check specifically useWebSocket.ts, useHITLWebSocket.ts, ChatInterface.tsx
    files_to_check = [
        frontend_dir / "hooks" / "useWebSocket.ts",
        frontend_dir / "hooks" / "useHITLWebSocket.ts",
        frontend_dir / "components" / "ChatInterface.tsx",
    ]
    
    hardcoded_patterns = [
        re.compile(r"ws://localhost:\d+"),
        re.compile(r"wss://api\.sanskritisetu\.org"),
        re.compile(r"http://localhost:\d+"),
        re.compile(r"https://api\.sanskritisetu\.org"),
    ]
    
    found_issues = []
    
    for file_path in files_to_check:
        if not file_path.exists():
            continue
            
        content = file_path.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in hardcoded_patterns:
                if pattern.search(line):
                    found_issues.append(f"{file_path.name}:{i} bevat hardcoded URL: {line.strip()}")
    
    assert len(found_issues) == 0, "Hardcoded URLs gevonden in frontend:\n" + "\n".join(found_issues)

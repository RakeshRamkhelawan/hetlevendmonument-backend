"""
Architecture test to ensure subclasses of EnhancedBaseAgent do not override process_task.
Overriding process_task bypasses the governance and transparency pipeline.
Subclasses should override _execute_task instead.
"""

import ast
from pathlib import Path

def test_no_agent_overrides_process_task() -> None:
    src_dir = Path(__file__).parent.parent.parent / "src"

    violators = []
    unreadable: list[str] = []
    scanned = 0

    for filepath in src_dir.rglob("*.py"):
        try:
            content = filepath.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{filepath.name}: {exc}")
            continue

        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError as exc:
            unreadable.append(f"{filepath.name}: {exc}")
            continue

        scanned += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it inherits from EnhancedBaseAgent (simple name check)
                inherits_from_enhanced = any(
                    isinstance(base, ast.Name) and base.id == "EnhancedBaseAgent" 
                    for base in node.bases
                )
                
                # If it inherits from EnhancedBaseAgent, it MUST NOT override process_task directly
                if inherits_from_enhanced:
                    # Ignore the base class itself
                    if node.name == "EnhancedBaseAgent" or node.name == "BaseAgent":
                        continue
                        
                    for body_item in node.body:
                        if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if body_item.name == "process_task":
                                violators.append(f"{node.name} in {filepath.name}")
                                
    assert scanned >= 1500, (
        f"Slechts {scanned} bestanden gescand onder {src_dir} -- dat lijkt een (bijna) lege "
        "boom. Verkeerd pad? Deze guard controleert dan vrijwel niets."
    )
    assert not unreadable, (
        "Deze bestanden konden niet gelezen of geparsed worden en zijn NIET gecontroleerd "
        "op een process_task-override:\n" + "\n".join(f"  - {f}" for f in unreadable)
    )
    assert not violators, f"Found classes overriding process_task directly: {violators}. Use _execute_task instead to preserve governance gates."

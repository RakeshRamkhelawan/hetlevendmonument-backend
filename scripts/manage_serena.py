import os
import re
import sys
from pathlib import Path

# Constants
ENV_FILE = Path(".env")
EXAMPLE_ENV_FILE = Path(".env.example")
KEY_ENABLE = "ENABLE_SERENA_MCP"
KEY_PATH = "SERENA_SERVICE_PATH"
DEFAULT_PATH = "services/serena"


def read_env_file(file_path):
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def write_env_file(file_path, lines):
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def set_env_variable(lines, key, value):
    new_lines = []
    found = False
    regex = re.compile(f"^{key}=.*")

    for line in lines:
        if regex.match(line):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        # Check if we need to add a newline before appending
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")

    return new_lines


def get_env_variable(lines, key):
    regex = re.compile(f"^{key}=(.*)")
    for line in lines:
        match = regex.match(line)
        if match:
            return match.group(1).strip()
    return None


def status():
    if not ENV_FILE.exists():
        print("[FAIL] .env file not found!")
        return

    lines = read_env_file(ENV_FILE)
    enabled = get_env_variable(lines, KEY_ENABLE)
    path = get_env_variable(lines, KEY_PATH)

    print("\n[CHART] Serena MCP Status:")
    print("-" * 30)

    if enabled and enabled.lower() == "true":
        print("Status:  [OK] ENABLED")
    else:
        print("Status:  [U+26AA] DISABLED")

    print(f"Path:    {path if path else '(not set, using default)'}")
    print("-" * 30)


def enable():
    if not ENV_FILE.exists():
        print("[WARN] .env file not found. Creating from .env.example...")
        if EXAMPLE_ENV_FILE.exists():
            lines = read_env_file(EXAMPLE_ENV_FILE)
        else:
            lines = []
    else:
        lines = read_env_file(ENV_FILE)

    lines = set_env_variable(lines, KEY_ENABLE, "true")
    # Ensure path is set
    current_path = get_env_variable(lines, KEY_PATH)
    if not current_path:
        lines = set_env_variable(lines, KEY_PATH, DEFAULT_PATH)

    write_env_file(ENV_FILE, lines)
    print("[OK] Serena MCP has been ENABLED in .env")


def disable():
    if not ENV_FILE.exists():
        print("[FAIL] .env file not found!")
        return

    lines = read_env_file(ENV_FILE)
    lines = set_env_variable(lines, KEY_ENABLE, "false")
    write_env_file(ENV_FILE, lines)
    print("[U+26AA] Serena MCP has been DISABLED in .env")


def main():
    if len(sys.argv) < 2:
        print("Usage: python manage_serena.py [status|enable|disable]")
        return

    command = sys.argv[1].lower()

    if command == "status":
        status()
    elif command == "enable":
        enable()
    elif command == "disable":
        disable()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python manage_serena.py [status|enable|disable]")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# scripts/install-hooks.sh
#
# Installs git hooks from scripts/hooks/ into .git/hooks/.
# Run once after cloning: bash scripts/install-hooks.sh
#
# Safe to re-run: overwrites existing hooks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SRC="$SCRIPT_DIR/hooks"

# De GEDEELDE .git-map, ook vanuit een gelinkte worktree.
#
# Hier stond `$REPO_ROOT/.git/hooks`. In een gelinkte worktree is `.git` geen MAP maar een
# BESTAND dat naar `<hoofdrepo>/.git/worktrees/<naam>` wijst, dus dat pad bestaat daar niet
# en dit script viel af met "Run this script from inside the git repository" -- terwijl je
# er wel degelijk in stond. Gemeten 2026-09-17 vanuit `C:/tmp/ss-op154`.
#
# Dat is erger dan een ongemak: CLAUDE.md schrijft voor dat elke parallelle sessie in een
# EIGEN worktree werkt. Een wijziging aan `scripts/hooks/pre-push` was daar dus niet te
# installeren, en omdat `.git/hooks/pre-push` een KOPIE is (geen symlink), draaide de oude
# hook stil door. Een reparatie aan de poort deed dan niets, zonder enige melding.
#
# Hooks zijn per repository en niet per worktree: git zoekt ze altijd in de gedeelde map.
# Een installatie vanuit welke worktree dan ook geldt daarmee meteen voor allemaal.
GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
if [ -z "$GIT_COMMON_DIR" ]; then
  echo "[install-hooks] ERROR: dit is geen git-repository (git rev-parse faalde)."
  exit 1
fi
case "$GIT_COMMON_DIR" in
  /*|[A-Za-z]:*) ;;                                  # al absoluut
  *) GIT_COMMON_DIR="$REPO_ROOT/$GIT_COMMON_DIR" ;;  # relatief t.o.v. de repo-root
esac
GIT_HOOKS_DIR="$GIT_COMMON_DIR/hooks"

if [ ! -d "$GIT_HOOKS_DIR" ]; then
  mkdir -p "$GIT_HOOKS_DIR"
fi

if [ ! -d "$HOOKS_SRC" ]; then
  echo "[install-hooks] ERROR: hooks source directory not found: $HOOKS_SRC"
  exit 1
fi

echo "[install-hooks] Installing hooks from scripts/hooks/ -> .git/hooks/"

for hook in "$HOOKS_SRC"/*; do
  [ -f "$hook" ] || continue
  name="$(basename "$hook")"
  dest="$GIT_HOOKS_DIR/$name"
  cp "$hook" "$dest"
  chmod +x "$dest"
  echo "[install-hooks]   installed: $name"
done

echo "[install-hooks] Done. Hooks active:"
ls -la "$GIT_HOOKS_DIR/" | grep -v '^total' || true

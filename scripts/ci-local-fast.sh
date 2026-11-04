#!/usr/bin/env bash
# ci-local-fast.sh - snelle pre-push checks (<2 minuten)
#
# Checks die identiek zijn aan CI (blokkeren push als ze falen):
#   1. ruff check src/          -- volledige scan, identiek aan ci-feature + cd-staging
#   2. check_fastapi_di_patterns.py --ci  -- identiek aan ci-feature + cd-staging
#   3. bandit -r src/ HIGH+HIGH -- identiek aan ci-feature security job
#   4. pyproject.toml guard     -- identiek aan ci-feature (grep check)
#   5. architecture fitness tests (ADR-033)
#
# Checks die NIET haalbaar zijn in de hook (te traag / externe services nodig):
#   - pyright (60-120s)
#   - mypy --fail-on-increase (complex, 60-120s) → hier warning-only
#   - pip-audit (vereist volledige dep-install)
#   - pytest unit tests (vereist PostgreSQL)
#   - frontend tests + build (aparte job, minuten)
#   - docker builds + migratie chain (vereist Docker, minuten)
#
# Overgeslagen: integratietests, docker build, alembic
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "[CI-FAST] Starten snelle checks..."
FAILED=0

# Determine the correct python executable path (bulletproof detection)
PYTHON_EXE="python"
if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_EXE=".venv/Scripts/python.exe"
elif [ -f ".venv/Scripts/python" ]; then
    PYTHON_EXE=".venv/Scripts/python"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
elif [ -f "venv/Scripts/python.exe" ]; then
    PYTHON_EXE="venv/Scripts/python.exe"
elif [ -f "venv/Scripts/python" ]; then
    PYTHON_EXE="venv/Scripts/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_EXE="venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXE="python3"
elif command -v python &>/dev/null; then
    PYTHON_EXE="python"
fi

echo "[CI-FAST] Gebruikt python interpreter: $PYTHON_EXE"

# ---------------------------------------------------------------------------
# 1. Ruff linting — ALTIJD volledige src/ scan, identiek aan CI
#    (ruff is <5s op 1700 bestanden; file-scope zou pre-existing errors missen)
# ---------------------------------------------------------------------------
echo "[CI-FAST] Ruff check (volledige src/ scan, identiek aan CI)..."
if ! "$PYTHON_EXE" -m ruff check src/ --exclude src/alembic --quiet; then
    echo "[CI-FAST] FAIL: Ruff gevonden stijlfouten."
    echo "[CI-FAST] Tip: run '$PYTHON_EXE -m ruff check src/ --exclude src/alembic' voor details."
    FAILED=1
fi

# ---------------------------------------------------------------------------
# Get staged/modified Python files — voor file-scoped checks (mypy, bandit)
# ---------------------------------------------------------------------------
FILES=$(git diff --name-only --cached --diff-filter=d | grep '\.py$' | grep -v '^src/alembic/' | grep -v '^tests/' || true)
if [ -z "$FILES" ]; then
    FILES=$(git diff --name-only --diff-filter=d | grep '\.py$' | grep -v '^src/alembic/' | grep -v '^tests/' || true)
fi

if [ -z "$FILES" ]; then
    echo "[CI-FAST] Geen gewijzigde Python bestanden — mypy/bandit overgeslagen."
else
    echo "[CI-FAST] Valideren van gewijzigde bestanden:"
    echo "$FILES"
    echo ""

    # 2. Mypy type checking (warning-only — preserveert developer flow)
    #    CI gebruikt --fail-on-increase (blokkerend); lokaal te traag voor pre-push gate.
    #    --follow-imports=silent: alleen de opgegeven bestanden, geen transitive chain
    #    (snel; volledige src/ check via 'python scripts/run_mypy_audit.py')
    echo "[CI-FAST] Mypy type check (waarschuwing — CI gebruikt --fail-on-increase)..."
    # set -e reageert op het exitcode van een command-substitutie in een kale
    # toekenning (MYPY_OUT=$(...)) alsof het een gewoon commando is -- zonder de
    # &&/|| hieronder verlaat het script hier meteen zodra mypy 1 fout vindt, VOOR
    # de "waarschuwing, niet blokkerend"-tak hieronder ooit bereikt wordt. Precies
    # het scenario dat deze stap juist moest voorkomen (gevonden 2026-08-25 tijdens
    # het pushen van de HITL-ticket-volledigheid-sprint: mypy-fouten in bestanden
    # van een andere, gelijktijdig lopende sessie blokkeerden een ongerelateerde push
    # zonder enige foutmelding van deze stap).
    MYPY_OUT=$("$PYTHON_EXE" -m mypy $FILES --no-error-summary --follow-imports=silent 2>&1) \
        && MYPY_EXIT=0 || MYPY_EXIT=$?
    if [ $MYPY_EXIT -ne 0 ]; then
        echo "[CI-FAST] WAARSCHUWING: Mypy type errors in gewijzigde bestanden. Push NIET geblokkeerd."
        echo "[CI-FAST] Let op: CI blokkeert als het totaal aantal errors TOENEEMT (--fail-on-increase)."
        echo "[CI-FAST] Tip: run 'python scripts/run_mypy_audit.py' om de impact te meten."
        echo "$MYPY_OUT" | grep ": error:" | head -10
    fi
fi

# ---------------------------------------------------------------------------
# 2. FastAPI DI anti-pattern check — ALTIJD, identiek aan ci-feature + cd-staging
# ---------------------------------------------------------------------------
echo "[CI-FAST] FastAPI DI anti-pattern check (identiek aan CI)..."
if ! "$PYTHON_EXE" scripts/check_fastapi_di_patterns.py --ci 2>/dev/null; then
    echo "[CI-FAST] FAIL: FastAPI DI anti-patterns gevonden."
    echo "[CI-FAST] Tip: run 'python scripts/check_fastapi_di_patterns.py --ci' voor details."
    FAILED=1
fi

# ---------------------------------------------------------------------------
# 3. Bandit security scan — ALTIJD volledige src/ scan, identiek aan CI
#    CI gebruikt: bandit -r src/ -ll -ii + filter HIGH severity + HIGH confidence
# ---------------------------------------------------------------------------
echo "[CI-FAST] Bandit security scan (volledige src/ scan, identiek aan CI)..."

# Eerst: BESTAAT bandit? (ADR-036 OP-244)
#
# Tot 2026-09-15 was dit niet gecontroleerd, en de keten eronder maakte van een ontbrekende
# bandit een GROENE melding: `|| true` slikte de fout, `2>/dev/null` verborg "No module named
# bandit", het JSON-bestand werd nooit geschreven, de `except Exception` hieronder drukte 0
# af, en het script meldde "geen HIGH+HIGH findings". Gemeten: bandit stond NIET in
# requirements-test.txt en was niet geinstalleerd -- de enige beveiligingsscan die er na het
# stilleggen van GitHub Actions nog is, gaf al die tijd een valse veiligverklaring.
if ! "$PYTHON_EXE" -m bandit --version >/dev/null 2>&1; then
    echo "[CI-FAST] FAIL: bandit is niet geinstalleerd, dus de beveiligingsscan kan NIET draaien."
    echo "[CI-FAST] Dit is geen 'geen bevindingen' -- er is niets gemeten."
    echo "[CI-FAST] Installeer met: $PYTHON_EXE -m pip install -r requirements-test.txt"
    FAILED=1
fi

BANDIT_JSON=$(mktemp /tmp/bandit-ci-XXXXXX.json)
"$PYTHON_EXE" -m bandit -r src/ -ll -ii \
    -x "tests,src/alembic" \
    -f json -o "$BANDIT_JSON" -q 2>/dev/null || true

# En: is er daadwerkelijk een rapport geschreven? Een bandit die halverwege omvalt laat
# hetzelfde lege gat achter als een bandit die ontbreekt.
if [ ! -s "$BANDIT_JSON" ]; then
    echo "[CI-FAST] FAIL: bandit heeft geen rapport geschreven -- er is niets gemeten."
    FAILED=1
fi
CRITICAL=$("$PYTHON_EXE" -c "
import json, sys
try:
    r = json.load(open('$BANDIT_JSON'))
    findings = [i for i in r.get('results', [])
                if i['issue_severity'] == 'HIGH' and i['issue_confidence'] == 'HIGH']
    print(len(findings))
    for f in findings:
        print(f'  {f[\"filename\"]}:{f[\"line_number\"]} - {f[\"issue_text\"]}', file=sys.stderr)
except Exception as e:
    print(0)
" 2>/tmp/bandit-critical-details.txt)
rm -f "$BANDIT_JSON"
if [ "${CRITICAL:-0}" -gt 0 ]; then
    echo "[CI-FAST] FAIL: $CRITICAL HIGH+HIGH bandit findings gevonden:"
    cat /tmp/bandit-critical-details.txt
    FAILED=1
else
    echo "[CI-FAST] Bandit: geen HIGH+HIGH findings."
fi
rm -f /tmp/bandit-critical-details.txt

# ---------------------------------------------------------------------------
# 4. pyproject.toml warning-filter guard — identiek aan ci-feature
# ---------------------------------------------------------------------------
echo "[CI-FAST] pyproject.toml warning-filter guard..."
if grep -qE 'ignore::gevent\.monkey\._errors\.MonkeyPatchWarning' pyproject.toml; then
    echo "[CI-FAST] FAIL: Verboden pytest warning-filter gevonden in pyproject.toml."
    echo "[CI-FAST] Gebruik een message-based filter i.p.v. een class-based filter voor gevent."
    FAILED=1
fi

# ---------------------------------------------------------------------------
# 5. Architecture contracts (ADR-033)
# ---------------------------------------------------------------------------
echo "[CI-FAST] Checking architectural contracts..."
if ! lint-imports 2>/dev/null; then
    echo "[CI-FAST] WAARSCHUWING: lint-imports contract violations gevonden (verwacht voor legacy bestanden)."
    echo "[CI-FAST] Tip: run 'lint-imports' voor details. Nieuwe code in src/core/api/v1/*/router.py moet contracts naleven."
fi

# ---------------------------------------------------------------------------
# 6. Architecture fitness tests (ADR-033)
# ---------------------------------------------------------------------------
echo "[CI-FAST] Running architecture fitness tests..."
if ! "$PYTHON_EXE" -m pytest tests/architecture/test_api_layer.py -x -q --timeout=60 2>/dev/null; then
    echo "[CI-FAST] FAIL: Architecture fitness tests gefaald."
    echo "[CI-FAST] Run 'pytest tests/architecture/test_api_layer.py -v' voor details."
    FAILED=1
fi

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "[CI-FAST] GEBLOKKEERD: Los bovenstaande fouten op voor je pusht."
    echo "[CI-FAST] Tip: gebruik 'git push --no-verify' om te bypassen (niet aanbevolen)."
    exit 1
fi

echo "[CI-FAST] Alle snelle checks geslaagd."
exit 0

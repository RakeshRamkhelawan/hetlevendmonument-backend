#!/bin/bash
# =============================================================================
# PRE-DEPLOY VALIDATIE — SanskritiSetu.org
# =============================================================================
# Draai dit script ALTIJD voordat je een versietag aanmaakt of een pipeline
# herstart. Elke falende check blokkeert de deploy.
#
# Gebruik: bash scripts/pre-deploy-check.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0
OVERGESLAGEN=()

ok()   { echo -e "${GREEN}  OK${NC}  $1"; }
fail() { echo -e "${RED}  FAIL${NC} $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo -e "${YELLOW}  WARN${NC} $1"; }

# Stappen die op de aanroeper niet kunnen draaien overslaan, MET reden en zichtbaar als WARN
# (OP-227): `PRE_DEPLOY_SLA_OVER="4 5"`. Leeg of niet gezet = alles draait, zoals handmatig.
# Een overgeslagen stap is nooit groen: hij wordt als WARN gemeld en telt niet als OK.
slaan_over() { [[ " ${PRE_DEPLOY_SLA_OVER:-} " == *" $1 "* ]]; }

echo ""
echo "=== PRE-DEPLOY VALIDATIE ==="
echo ""

# -----------------------------------------------------------------------
# 1. Alle bestanden die Dockerfile COPYt zitten in git
# -----------------------------------------------------------------------
echo "1. Docker-bestanden aanwezig in git..."
while IFS= read -r line; do
    # Pak COPY-regels, strip commentaar
    [[ "$line" =~ ^COPY[[:space:]] ]] || continue
    # `COPY --from=<stage> /pad ./doel` kopieert uit een EERDERE BUILDFASE, niet uit de repo.
    # Die bronpaden horen niet in git en een controle erop zou onterecht falen. Vandaag komt
    # deze vorm niet voor in de Dockerfile (gemeten 2026-09-18: nul treffers), dus dit is
    # vooruitkijken, niet repareren.
    [[ "$line" == *"--from="* ]] && continue
    # De bronpaden zijn ALLE velden na `COPY` behalve de vlaggen en het laatste veld (de
    # bestemming). `awk '{print $2}'` stond hier tot 2026-09-18 en gaf op
    # `COPY --chown=appuser:appuser src/ ./src/` de VLAG terug. Gemeten op die dag: 9 van de
    # 10 COPY-regels in de Dockerfile gebruiken `--chown`, dus deze stap toetste negen keer
    # of `--chown=appuser:appuser` in git staat -- dat staat het nooit, dus negen FAILs en
    # NUL gecontroleerde paden. De deploygate stond daarmee permanent rood op een gezonde
    # repo, en een poort die altijd rood is wordt genegeerd. Gevonden tijdens ADR-036 OP-227
    # door het script ECHT te draaien; alleen de diff lezen had dit niet laten zien.
    #
    # Ook de LUS is nieuw. Een regel kan meer dan een bron hebben -- regel 58 heeft er drie
    # (`COPY requirements-base.txt requirements-prod.txt requirements-prod.lock ./`) -- en
    # zowel de oude `$2` als een eerste versie van deze fix keek alleen naar de eerste. Dan
    # klopt "alle paden worden gecontroleerd" niet, en een overclaim in een poort is precies
    # wat OP-148 hier al eerder moest rechtzetten (Gate 2-code-review, 2026-09-18).
    bronnen=$(echo "$line" | awk '{for (i = 2; i < NF; i++) if ($i !~ /^--/) print $i}')
    for src in $bronnen; do
        # Skip globs en ./
        [[ "$src" == *"*"* || "$src" == "./" || "$src" == "." ]] && continue
        # Strip trailing slash voor directory-check
        src="${src%/}"
        if git ls-files --error-unmatch "$src" > /dev/null 2>&1; then
            ok "$src"
        elif git ls-files "$src/" | grep -q .; then
            ok "$src/ (directory)"
        else
            fail "$src staat NIET in git -- pipeline zal falen"
        fi
    done
done < Dockerfile

echo ""

# -----------------------------------------------------------------------
# 1b. Docker Compose configuratie valideren (prod overlay vereist)
# -----------------------------------------------------------------------
echo "1b. Docker Compose prod config valideren..."
# ZONDER interpolatie (OP-261). De prod-overlay eist met opzet variabelen (`${X:?...}`); met
# interpolatie was deze stap op elke machine zonder die variabelen per definitie rood (gemeten
# 2026-09-18, en opnieuw 2026-10-24: exit 1), en een gate die nooit groen kan worden leert zijn
# gebruiker dat rood normaal is. `--no-interpolate` toetst de STRUCTUUR (YAML, services, extends)
# en zet bovendien geen waarden uit `.env` in de uitvoer. Dat een variabele in de omgeving
# aanwezig is, toetst stap 4 (GitHub Secrets) en de preflight van de CD-workflow.
if docker compose -f docker-compose.yml -f docker-compose.prod.yml config --no-interpolate --quiet > /dev/null 2>&1; then
    ok "docker compose prod config valide"
else
    fail "docker compose prod config ONGELDIG — controleer docker-compose.yml en docker-compose.prod.yml"
fi

echo ""

# -----------------------------------------------------------------------
# 2. Docker build — production-api
# -----------------------------------------------------------------------
echo "2. Docker build testen (production-api)..."
if docker build --target production-api -t sanskritisetu:precheck . -q > /dev/null 2>&1; then
    ok "Docker build production-api geslaagd"
    docker rmi sanskritisetu:precheck -f > /dev/null 2>&1 || true
else
    # Herhaal met output zichtbaar
    echo ""
    docker build --target production-api -t sanskritisetu:precheck . 2>&1 | tail -20
    fail "Docker build production-api MISLUKT — fix eerst de build, dan pas deployen"
fi

echo ""

# -----------------------------------------------------------------------
# 3. Docker build — frontend
# -----------------------------------------------------------------------
echo "3. Docker build testen (frontend)..."
if docker build -t sanskritisetu-frontend:precheck frontend/ -q > /dev/null 2>&1; then
    ok "Docker build frontend geslaagd"
    docker rmi sanskritisetu-frontend:precheck -f > /dev/null 2>&1 || true
else
    echo ""
    docker build -t sanskritisetu-frontend:precheck frontend/ 2>&1 | tail -20
    fail "Docker build frontend MISLUKT"
fi

echo ""

# -----------------------------------------------------------------------
# 3b. Alembic migration chain validation
# -----------------------------------------------------------------------
echo "3b. Alembic migratie-keten valideren..."
# Reuse the precheck image from step 2 if it exists
IMG=""
if docker images -q sanskritisetu:precheck 2>/dev/null | grep -q .; then
    IMG="sanskritisetu:precheck"
elif docker build --target production-api -t sanskritisetu:migcheck . -q > /dev/null 2>&1; then
    IMG="sanskritisetu:migcheck"
fi

if [ -n "$IMG" ]; then
    # MSYS_NO_PATHCONV=1 prevents Git Bash on Windows from converting
    # /app/src/alembic.ini to a Windows path (C:/Program Files/Git/app/...)
    # Chain compile check
    if MSYS_NO_PATHCONV=1 docker run --rm --pull=never \
        --entrypoint python3 \
        -e DATABASE_URL="postgresql://x:x@localhost/x" "$IMG" \
        -m alembic -c /app/src/alembic.ini upgrade head --sql \
        > /dev/null 2>&1; then
        ok "Migratie-keten is syntactisch geldig (GEEN volledig schema -- zie ADR-036 OP-148)"
    else
        fail "Migratie-keten KAPOT — alembic upgrade head --sql faalt"
    fi

    # Waarom die formulering en niet "de keten compileert" (ADR-036 OP-148).
    #
    # `upgrade head --sql` draait OFFLINE. Elke migratie die haar werk achter
    # `if not _is_offline(bind):` zet, of die `sa.inspect(op.get_bind())` gebruikt om te
    # kijken of iets al bestaat, slaat in die modus stil over. Gemeten 2026-08-30: 109
    # revisies in de keten, waarvan 9 bestanden `sa.inspect(op.get_bind())` gebruiken.
    #
    # Het gevolg is dat deze stap GROEN wordt op een uitvoer die het echte eindschema niet
    # bevat -- en dat terwijl dit de poort van de deploy is. "Compileert" suggereert dat het
    # schema klopt; het enige wat bewezen is, is dat de keten zonder syntaxfout doorloopt.
    #
    # Deze stap blijft daarom staan voor wat hij WEL is: een goedkope syntaxcontrole die
    # binnen seconden een kapotte keten vindt. De echte schematoets staat sinds
    # 2026-09-18 in stap 3c hieronder en draait blokkerend tegen een verse PostgreSQL
    # (ADR-036 OP-227). Tot die dag stond hier dat zo'n toets "hoort te" bestaan -- hij
    # werd nergens aangeroepen, en dat is precies wat OP-227 heeft gerepareerd.

    # Single head check
    HEADS_RAW=$(MSYS_NO_PATHCONV=1 docker run --rm --pull=never \
        --entrypoint python3 \
        -e DATABASE_URL="postgresql://x:x@localhost/x" "$IMG" \
        -m alembic -c /app/src/alembic.ini heads 2>&1)
    HEAD_COUNT=$(echo "$HEADS_RAW" | grep -c '(head)' || echo "0")
    if [ "$HEAD_COUNT" -eq 1 ]; then
        ok "Enkele migratie-head (correct)"
    else
        fail "Aantal migratie-heads: $HEAD_COUNT (verwacht: 1)"
    fi

    # Cleanup migcheck image if we built it
    docker rmi sanskritisetu:migcheck -f > /dev/null 2>&1 || true
else
    warn "Docker image niet gebouwd — migratie-keten niet gevalideerd"
fi

echo ""

# -----------------------------------------------------------------------
# 3c. Migratie-keten op een ECHTE database (ADR-036 OP-227)
# -----------------------------------------------------------------------
# Stap 3b hierboven is een SYNTAXcontrole en zegt dat zelf. Deze stap is de
# schematoets: de keten draait op een verse PostgreSQL en het resultaat wordt
# vergeleken met `Base.metadata`. Gemeten 2026-09-18: 8 tests, 18,5s pytest,
# 32,5s wandklok inclusief het opstarten van de container.
#
# De container bindt op 127.0.0.1 en niet op 0.0.0.0. De bestaande testdatabases in dit
# project (`docker-compose.test-db.yml`, `make test-db-up`) binden wel op alle interfaces met
# postgres/postgres, maar dit is de eerste keer dat dat patroon in de LAATSTE poort voor een
# productiedeploy komt te staan -- en op een gedeelde CI-runner of een laptop op een
# onvertrouwd netwerk is die database dan van buiten bereikbaar. De testsuite verbindt
# sowieso via 127.0.0.1 (`tests/fixtures/testdatabase.py::_server_dsn`), dus dit kost niets.
# Aanbeveling uit de Gate 2-security-review van 2026-09-18.
#
# Waarom netwerkpoort 5457. Gemeten 2026-09-18 op deze machine: 5432/5433/5434 zijn in
# gebruik of geclaimd door compose (5433 luisterde daadwerkelijk), 5435 is de poort waar
# op 2026-09-14 zes uur lang een vergeten `act`-servicecontainer stond (ADR-036 OP-243),
# 5455 is de testdatabase waar gelijktijdige sessies tegen draaien, en 55433 hoort bij
# tests/e2e/phase7. 5456, 5457 en 5458 waren alle drie vrij (`netstat -ano -p tcp`);
# 5457 is gekozen. De poort alleen is niet de bescherming -- de container en de
# databaseverbinding hebben ook een EIGEN naam, en de testsuite krijgt die database
# EXPLICIET opgegeven via SANSKRITISETU_TEST_DATABASE_URL in plaats van hem te zoeken.
# Dat raden is in OP-243 juist weggehaald en wordt hier niet opnieuw ingevoerd.
echo "3c. Migratie-keten op een ECHTE database valideren..."

SCHEMA_TEST="tests/integration/database/test_the_chain_builds_the_whole_schema.py"
SCHEMA_DB_CONTAINER="sanskritisetu_predeploy_schema"
SCHEMA_DB_POORT=5457
# Naam op `_test`: de testsuite wist alleen een aantoonbare testdatabase (tests/fixtures/testdatabase.py,
# brief 2026-10-26) en weigert een andere naam. Deze wegwerpdatabase staat op 5457, niet op de dev-poort 5435.
SCHEMA_DB_NAAM="sanskritisetu_test"
SCHEMA_DB_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:${SCHEMA_DB_POORT}/${SCHEMA_DB_NAAM}"

# De opruiming hangt aan EXIT en niet aan het einde van deze stap: valt het script
# halverwege om (`set -e`), dan blijft er anders een PostgreSQL op 5457 achter. Een
# achtergebleven container is in deze repo geen theorie -- op 2026-09-14 liet er een de
# integratiesuite tegen de verkeerde database meten zonder dat iets dat meldde (OP-243).
_schema_db_opruimen() {
    docker rm -f "$SCHEMA_DB_CONTAINER" > /dev/null 2>&1 || true
}
trap _schema_db_opruimen EXIT

# Fail-secure: een poort die niet kan meten meldt niet groen. Daarom fail() en geen warn()
# als de interpreter of pytest ontbreekt -- anders is "deploy mag door" een uitspraak over
# een toets die nooit heeft gedraaid.
PYTHON_BIN=""
for kandidaat in python3 python; do
    if command -v "$kandidaat" > /dev/null 2>&1; then
        PYTHON_BIN="$kandidaat"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    fail "Geen python-interpreter gevonden -- de schematoets kan niet draaien, dus de keten is NIET op een echte database gevalideerd"
elif ! "$PYTHON_BIN" -c "import pytest" > /dev/null 2>&1; then
    fail "pytest ontbreekt in $PYTHON_BIN -- installeer met: $PYTHON_BIN -m pip install -r requirements-test.txt"
else
    _schema_db_opruimen
    if docker run -d --name "$SCHEMA_DB_CONTAINER" \
        -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB="$SCHEMA_DB_NAAM" \
        -p "127.0.0.1:${SCHEMA_DB_POORT}:5432" pgvector/pgvector:pg15 > /dev/null 2>&1; then

        # Bovengrens op het wachten: zonder die grens hangt een deploy-poort stil bij een
        # container die nooit opkomt. Gemeten opstarttijd op deze machine: 1 seconde.
        SCHEMA_DB_KLAAR=0
        for _ in $(seq 1 60); do
            if docker exec "$SCHEMA_DB_CONTAINER" pg_isready -U postgres -q > /dev/null 2>&1; then
                SCHEMA_DB_KLAAR=1
                break
            fi
            sleep 1
        done

        if [ "$SCHEMA_DB_KLAAR" -eq 1 ]; then
            SCHEMA_LOG=$(mktemp)
            if SANSKRITISETU_TEST_DATABASE_URL="$SCHEMA_DB_URL" \
                "$PYTHON_BIN" -m pytest "$SCHEMA_TEST" -q --tb=short > "$SCHEMA_LOG" 2>&1; then
                ok "Migratie-keten bouwt het VOLLEDIGE schema op een verse database"
            else
                echo ""
                tail -40 "$SCHEMA_LOG"
                echo ""
                fail "Schematoets MISLUKT -- de keten levert op een echte database geen schema op dat bij de modellen past ($SCHEMA_TEST)"
            fi
            rm -f "$SCHEMA_LOG"
        else
            fail "PostgreSQL op netwerkpoort $SCHEMA_DB_POORT kwam niet op binnen 60s -- schematoets NIET gedraaid"
        fi
    else
        fail "Kon geen PostgreSQL starten op netwerkpoort $SCHEMA_DB_POORT -- schematoets NIET gedraaid"
    fi
    _schema_db_opruimen
fi

echo ""

# -----------------------------------------------------------------------
# 4. Verplichte GitHub Secrets aanwezig
# -----------------------------------------------------------------------
echo "4. GitHub Secrets controleren..."
REQUIRED_SECRETS=(
    "AZURE_CREDENTIALS"
    "GH_PAT_MAIN_MERGE"
    # Container registry
    "ACR_PASSWORD"
    "REGISTRY_LOGIN_SERVER"
    "REGISTRY_PASSWORD"
    "REGISTRY_USERNAME"
    # Productie backend
    "PROD_BACKEND_APP"
    "PROD_DATABASE_URL"
    "PROD_FRONTEND_APP"
    "PROD_JWT_SECRET_KEY"
    "PROD_SECRET_KEY"
    "PROD_WORKER_APP"
    # Productie ActivePieces
    "PROD_AP_ENCRYPTION_KEY"
    "PROD_AP_JWT_SECRET"
    # Staging backend
    "STAGING_BACKEND_APP"
    "STAGING_DATABASE_URL"
    "STAGING_FRONTEND_APP"
    "STAGING_JWT_SECRET_KEY"
    "STAGING_RESOURCE_GROUP"
    "STAGING_SECRET_KEY"
)
if slaan_over 4; then
    OVERGESLAGEN+=("4")
    warn "stap 4 overgeslagen (PRE_DEPLOY_SLA_OVER): een CD-job heeft met GITHUB_TOKEN geen recht om secrets te lijsten; de aanwezigheid controleert de preflight-job van de workflow"
elif command -v gh &> /dev/null; then
    # Onder `set -euo pipefail` brak de oude vorm `EXISTING=$(gh secret list | awk ...)` het script
    # STIL af zodra `gh` faalde (niet ingelogd, geen recht): exit 1 en geen woord in het log. Nu is
    # een falende `gh` een FAIL met reden -- een gate die zijn controle niet kan uitvoeren meldt niet
    # groen. De staging-runner slaat deze stap bewust over via PRE_DEPLOY_SLA_OVER.
    if ! GH_LIJST=$(gh secret list 2>/dev/null); then
        fail "gh secret list mislukte (niet ingelogd of geen recht) -- de GitHub Secrets zijn NIET gecontroleerd"
    else
        EXISTING=$(echo "$GH_LIJST" | awk '{print $1}')
        for secret in "${REQUIRED_SECRETS[@]}"; do
            if echo "$EXISTING" | grep -qx "$secret"; then
                ok "$secret"
            else
                fail "$secret ONTBREEKT in GitHub Secrets"
            fi
        done
    fi
else
    warn "gh CLI niet gevonden — GitHub Secrets niet gecontroleerd"
fi

echo ""

# -----------------------------------------------------------------------
# 5. Azure service principal heeft toegang
# -----------------------------------------------------------------------
echo "5. Azure service principal toegang controleren..."
SP_APP_ID="34923a6f-3f24-47f1-bb56-ce8416bc850f"
if slaan_over 5; then
    OVERGESLAGEN+=("5")
    warn "stap 5 overgeslagen (PRE_DEPLOY_SLA_OVER): deze job logt niet in bij Azure; de uitrolstap doet dat zelf"
elif command -v az &> /dev/null && az account show &> /dev/null; then
    ASSIGNMENTS=$(az role assignment list --assignee "$SP_APP_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
    if [ "$ASSIGNMENTS" -gt 0 ] 2>/dev/null; then
        ok "Service principal heeft $ASSIGNMENTS roltoewijzing(en)"
    else
        fail "Service principal heeft GEEN roltoewijzingen — pipeline faalt bij Azure login"
        warn "Fix: Azure Portal → Subscriptions → Azure subscription 1 → IAM → Roltoewijzing toevoegen → Inzender → sanskritisetu-github-actions"
    fi
else
    warn "az CLI niet ingelogd — Azure-toegang niet gecontroleerd"
fi

echo ""

# -----------------------------------------------------------------------
# Resultaat
# -----------------------------------------------------------------------
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}=== ALLE CHECKS GESLAAGD — DEPLOY MAG DOOR ===${NC}"
    if [ "${#OVERGESLAGEN[@]}" -gt 0 ]; then
        echo -e "${YELLOW}    maar stap ${OVERGESLAGEN[*]} is overgeslagen (PRE_DEPLOY_SLA_OVER) -- zie de WARN-regels hierboven${NC}"
    fi
    echo ""
    echo "Volgende stap:"
    echo "  git checkout develop && git merge main --no-edit && git push origin develop"
    echo "  git tag vX.Y.Z && git push origin vX.Y.Z"
    exit 0
else
    echo -e "${RED}=== $ERRORS CHECK(S) MISLUKT — DEPLOY GEBLOKKEERD ===${NC}"
    echo "Los bovenstaande problemen op voordat je deployt."
    exit 1
fi

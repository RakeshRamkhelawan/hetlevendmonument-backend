"""De staging-uitrol: applicatierol, Mistral, alle werkers, mail en links.

Brief 2026-10-23 (staging uitrol klaarmaken). Gemeten op `df79d145`:

1. De migratietaak EN de applicatie gebruikten hetzelfde geheim `database-url` uit
   `STAGING_DATABASE_URL` (de eigenaar). `src/core/database/applicatierol_controle.py` weigert buiten
   ontwikkeling een rol die eigenaar, superuser of BYPASSRLS is: met de eigenaarsrol start de API op
   staging niet meer. Nu: migratie = eigenaar (`database-url`), API, werker, planner en leerwerker =
   `sanskritisetu_app` (`app-database-url`, uit `STAGING_APP_DATABASE_URL`).
2. De workflow zette `LLM_PROVIDER=deepseek` of `mock`. Besluit Rakesh 2026-10-15: Mistral (EU), en
   geen stille terugval op `mock`.
3. De leerwerker en de bonlezer stonden niet in de workflow.

**Structuur, geen tekst.** Alles hieronder leest de YAML, de `env:`-kaarten en de commando's via
`_ci_workflow` (comments eruit, aanhalingstekenbewust). Een naam in een comment telt dus niet.

MUTATIEBEWIJS (zie review-BE-CD-STAGING-001; een regel per element, beide richtingen):
    API-stap `APP_DB_URL` terug naar `secrets.STAGING_DATABASE_URL`           -> `krijgen_de_applicatierol` ROOD
    werkerstap `DB_URL` terug naar de eigenaar                                -> idem ROOD
    planner terug naar `secretref:database-url`                               -> `leest_het_eigenaarsgeheim` ROOD
    leerwerkerstap weg                                                        -> `de_leerwerker_wordt_neergezet` ROOD
    bonlezerstap weg of zonder alleen-lezen volume                            -> `de_bonlezer_...` ROOD
    `LLM_PROVIDER=mock` terug of `deepseek` terug                             -> `geen_deepseek_en_geen_stille_mock` ROOD
    de migratietaak naar het app-geheim                                       -> `de_migratietaak_houdt_de_eigenaar` ROOD
    legitiem: een NAAM `DeepSeek` in een comment                              -> GROEN
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.architecture._ci_workflow import containerapp_commandos, logische_regels

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/cd-staging.yml"

APP_GEHEIM = "secrets.STAGING_APP_DATABASE_URL"
EIGENAAR_GEHEIM = re.compile(r"secrets\.STAGING_DATABASE_URL\b")

#: De stappen die applicatiecode op Azure zetten en dus als de applicatierol moeten verbinden.
APP_STAPPEN = (
    "Deploy backend",
    "Deploy worker",
    "Deploy scheduler",
    "Deploy learning worker",
)


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _stappen() -> list[dict[str, Any]]:
    stappen: list[dict[str, Any]] = []
    for job in _workflow()["jobs"].values():
        stappen.extend(s for s in job.get("steps") or [] if isinstance(s, dict))
    return stappen


def _stap(prefix: str) -> dict[str, Any]:
    gevonden = [s for s in _stappen() if str(s.get("name", "")).startswith(prefix)]
    assert len(gevonden) == 1, (
        f"verwacht precies een stap die met '{prefix}' begint: {len(gevonden)}"
    )
    return gevonden[0]


def _script(stap: dict[str, Any]) -> str:
    """Het script van een stap ZONDER comments, als een tekst van logische regels."""
    return "\n".join(logische_regels(str(stap.get("run") or "")))


def _env_waarden(stap: dict[str, Any]) -> list[str]:
    return [re.sub(r"\s+", "", str(v)) for v in (stap.get("env") or {}).values()]


def _app_geheim_in_env(stap: dict[str, Any]) -> bool:
    return any(f"${{{{{APP_GEHEIM}}}}}" == w for w in _env_waarden(stap))


@pytest.mark.parametrize("prefix", APP_STAPPEN)
def test_api_werker_planner_en_leerwerker_krijgen_de_applicatierol(prefix: str) -> None:
    assert _app_geheim_in_env(_stap(prefix)), (
        f"de stap '{prefix}' haalt STAGING_APP_DATABASE_URL niet uit zijn `env:`; "
        "de applicatie hoort als sanskritisetu_app te verbinden"
    )


@pytest.mark.parametrize("prefix", APP_STAPPEN)
def test_geen_van_die_stappen_geeft_de_eigenaar_aan_de_applicatie(prefix: str) -> None:
    stap = _stap(prefix)

    assert not [w for w in _env_waarden(stap) if EIGENAAR_GEHEIM.search(w)], (
        f"de stap '{prefix}' zet STAGING_DATABASE_URL (de eigenaar) in zijn `env:`"
    )


@pytest.mark.parametrize("prefix", APP_STAPPEN)
def test_geen_van_die_stappen_leest_het_eigenaarsgeheim_van_de_migratie(prefix: str) -> None:
    script = _script(_stap(prefix))

    assert not re.search(r"secretref:\s*database-url\b|secretRef:\s*database-url\b", script), (
        f"de stap '{prefix}' verwijst naar het Key-Vault-geheim `database-url` (de eigenaar)"
    )


@pytest.mark.parametrize("prefix", APP_STAPPEN)
def test_die_stappen_wijzen_hun_databaseverbinding_naar_het_app_geheim(prefix: str) -> None:
    script = _script(_stap(prefix))

    # `(?<![A-Z_])`: `BYPASS_DATABASE_URL=secretref:app-database-url` is dus GEEN geldige treffer.
    assert re.search(
        r"(?<![A-Z_])DATABASE_URL=secretref:app-database-url|secretRef:\s*app-database-url", script
    )


#: Stappen die `secrets.STAGING_DATABASE_URL` (de eigenaar) mogen noemen, met reden. Een NIEUWE stap
#: die de eigenaar noemt, valt hier niet onder: dan moet iemand bewust een regel toevoegen
#: (Gate 2, 2026-10-23: de vaste lijst APP_STAPPEN hierboven liet een nieuwe app-stap met een
#: andere naam door).
EIGENAAR_TOEGESTAAN: dict[str, str] = {
    "Check that the app and the migration use different database roles": (
        "vergelijkt de rollen van de twee geheimen; de waarde komt via env:"
    ),
    "Push secrets to Key Vault": "zet de eigenaar als `database-url` voor de migratietaak",
    "Check required secrets": "controleert dat het geheim bestaat",
    "Deploy Activepieces (staging)": (
        "ActivePieces gebruikt de eigenaar voor zijn EIGEN database; open punt, eigen brief "
        "(docs/infra/UITROL-STAGING-2026-10.md, sectie 6)"
    ),
}


def _stappen_die_de_eigenaar_noemen() -> set[str]:
    namen: set[str] = set()
    for stap in _stappen():
        tekst = "\n".join(
            [str(stap.get("run") or "")] + [str(v) for v in (stap.get("env") or {}).values()]
        )
        if EIGENAAR_GEHEIM.search(tekst):
            namen.add(str(stap.get("name", "")))
    return namen


def test_alleen_benoemde_stappen_noemen_de_eigenaar() -> None:
    onverwacht = _stappen_die_de_eigenaar_noemen() - set(EIGENAAR_TOEGESTAAN)

    assert not onverwacht, (
        f"stappen die STAGING_DATABASE_URL noemen zonder reden: {sorted(onverwacht)}"
    )


def test_de_eigenaar_toegestaan_lijst_is_niet_verouderd() -> None:
    verouderd = set(EIGENAAR_TOEGESTAAN) - _stappen_die_de_eigenaar_noemen()

    assert not verouderd, f"deze regels noemen de eigenaar niet meer: {sorted(verouderd)}"


def test_de_preflight_controleert_dat_de_inlogrol_een_eigen_rol_is() -> None:
    rollen = _stap("Check that the app and the migration use different database roles")

    assert (
        "BYPASS_URL" in (rollen.get("env") or {}) and "bypass in (eigenaar, app)" in rollen["run"]
    )


def test_het_bonlezerwachtwoord_wordt_in_de_preflight_gecontroleerd_voor_de_backend() -> None:
    namen = [str(s.get("name", "")) for s in _stappen()]

    assert namen.index("Check that the bonlezer Redis password is URL-safe") < namen.index(
        next(n for n in namen if n.startswith("Deploy backend"))
    )


def test_de_migratietaak_houdt_de_eigenaar() -> None:
    kluis = _stap("Push secrets to Key Vault")
    taak = _stap("Update migration-job image")

    assert re.search(r"--name database-url\b", _script(kluis)) is not None
    # Het eigenaar-geheim staat sinds 2026-10-24 in `env:` van de stap en niet meer in de shell-tekst
    # (test_cd_geheimen_alleen_via_env); de `--value` in het script wijst ernaar met ${GH_...}.
    assert any(EIGENAAR_GEHEIM.search(w) for w in _env_waarden(kluis))
    assert "secrets/database-url" in taak["run"] and "app-database-url" not in taak["run"]


def test_de_preflight_eist_het_app_geheim_en_verschillende_rollen() -> None:
    controle = _script(_stap("Check required secrets"))
    rollen = _stap("Check that the app and the migration use different database roles")

    assert 'check_secret "STAGING_APP_DATABASE_URL"' in controle
    assert _app_geheim_in_env(rollen) and any(
        EIGENAAR_GEHEIM.search(w) for w in _env_waarden(rollen)
    )


def test_de_preflight_eist_het_inlogpad_onder_de_applicatierol() -> None:
    controle = _script(_stap("Check required secrets"))

    assert 'check_secret "STAGING_BYPASS_DATABASE_URL"' in controle


def _alle_uitvoerbare_tekst() -> str:
    delen: list[str] = []
    for stap in _stappen():
        delen.append(_script(stap))
        delen.extend(str(v) for v in (stap.get("env") or {}).values())
    return "\n".join(delen)


def test_geen_deepseek_en_geen_stille_mock() -> None:
    tekst = _alle_uitvoerbare_tekst()

    assert "deepseek" not in tekst.lower()
    assert not re.search(r"LLM_PROVIDER=mock\b", tekst)


def test_de_backend_draait_op_mistral_met_een_sleutel_uit_een_secret() -> None:
    script = _script(_stap("Deploy backend"))

    assert (
        "LLM_PROVIDER=mistral" in script and "MISTRAL_API_KEY=secretref:mistral-api-key" in script
    )


def test_de_preflight_eist_de_mistralsleutel() -> None:
    assert 'check_secret "STAGING_MISTRAL_API_KEY"' in _script(_stap("Check required secrets"))


def _commando_voor(app: str) -> list[Any]:
    return [
        c
        for c in containerapp_commandos()
        if c.workflow == "cd-staging.yml" and app in c.waarden_van("--name")
    ]


def _manifest_voor(app: str) -> dict[str, Any]:
    manifesten = [c.manifest for c in _commando_voor(app) if c.manifest]
    assert manifesten, f"geen `containerapp create --yaml` voor {app}"
    return manifesten[0]


def _containers(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return manifest["properties"]["template"]["containers"]


def test_de_leerwerker_wordt_neergezet_met_een_proces_en_een_vast_aantal_draden() -> None:
    args = _containers(_manifest_voor("learning-worker-staging"))[0]["args"]

    assert args[0] == "src.core.learning.worker:_broker"
    assert "--processes" in args and "--threads" in args


def test_de_bonlezer_werker_krijgt_een_eigen_wachtrij_en_alleen_het_leesvolume() -> None:
    manifest = _manifest_voor("bonlezer-worker-staging")
    container = _containers(manifest)[0]
    volumes = manifest["properties"]["template"]["volumes"]

    assert container["args"][0] == "src.core.als.bonlezer.worker:_broker"
    assert {e["name"] for e in container["env"]} >= {"BONLEZER_BROKER_URL", "BONLEZER_UPLOAD_ROOT"}
    assert [v["storageName"] for v in volumes] == ["bonlezer-uploads-ro"]


def test_de_bonlezer_redis_heeft_geen_poort_naar_buiten_en_een_wachtwoord() -> None:
    manifest = _manifest_voor("bonlezer-redis-staging")
    ingress = manifest["properties"]["configuration"]["ingress"]
    container = _containers(manifest)[0]
    geheimen = manifest["properties"]["configuration"]["secrets"]

    assert ingress["external"] is False and ingress["transport"] == "tcp"
    assert any(s["name"] == "bonlezer-redis-password" for s in geheimen)
    assert any(e["name"] == "BONLEZER_REDIS_PASSWORD" for e in container["env"])


def test_de_api_krijgt_het_schrijfvolume_via_een_patch_op_de_app() -> None:
    stap = _stap("Mount the bonlezer upload volume on the backend")
    script = _script(stap)

    assert "az rest --method PATCH" in script and "bonlezer-uploads-rw" in stap["run"]


def test_de_bonlezer_image_wordt_gebouwd_en_gepusht() -> None:
    job = _workflow()["jobs"]["build-bonlezer"]
    tekst = "\n".join(str(s.get("run") or "") for s in job["steps"])

    assert "--target bonlezer-worker" in tekst and "docker push" in tekst
    assert "build-bonlezer" in _workflow()["jobs"]["deploy-staging"]["needs"]


@pytest.mark.parametrize(
    "geheim",
    [
        "STAGING_FRONTEND_URL",
        "STAGING_SMTP_HOST",
        "STAGING_EMAIL_FROM",
        "STAGING_MASTER_ENCRYPTION_KEY",
        "STAGING_BONLEZER_REDIS_PASSWORD",
        "STAGING_BONLEZER_STORAGE_ACCOUNT",
        "STAGING_BONLEZER_STORAGE_KEY",
    ],
)
def test_de_preflight_eist_elk_nieuw_geheim(geheim: str) -> None:
    assert f'check_secret "{geheim}"' in _script(_stap("Check required secrets"))


def test_de_api_en_de_werker_krijgen_de_mailinstellingen_en_de_links() -> None:
    for prefix in ("Deploy backend", "Deploy worker"):
        script = _script(_stap(prefix))

        assert "SMTP_HOST=" in script and "EMAIL_FROM=" in script, prefix
        assert "FRONTEND_URL=" in script and "API_BASE_URL=" in script, prefix


def test_de_urls_worden_bepaald_voordat_de_backend_ze_gebruikt() -> None:
    namen = [str(s.get("name", "")) for s in _stappen()]

    assert namen.index("Resolve public URLs and mail settings") < namen.index(
        next(n for n in namen if n.startswith("Deploy backend"))
    )


def test_de_prod_compose_kent_geen_deepseek_meer() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    regels = [
        str(e)
        for service in compose["services"].values()
        for e in (service.get("environment") or [])
    ]

    assert not [r for r in regels if "DEEPSEEK" in r.upper()]


def test_de_compose_heeft_de_bonlezer_met_eigen_redis_en_uploadvolume() -> None:
    basis = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = basis["services"]

    assert {"bonlezer-worker", "bonlezer-redis"} <= set(services)
    assert any("bonlezer_uploads" in str(v) for v in services["backend"]["volumes"])

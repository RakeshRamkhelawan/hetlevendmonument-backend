"""Tests voor de poorten van de MCP-server (mcp-server/tools/).

Waarom dit bestand bestaat. De server belooft dat `complete_task()` een agent niet
doorlaat zonder Gate 2, zonder afgehandelde pre-existing issues en zonder
kwaliteitsratchet. Gemeten op 2026-09-10 (commit 15b7107f) met een eigen statebestand:
drie gaten.

  1. `check_preexisting_gate()` eiste Gate 2 alleen `if not gate2_submitted and files`,
     waarbij `files` de door de AGENT OPGEGEVEN lijst is. Een taak met een lege lijst
     sloot af met ok=True zonder een enkele poort, en diezelfde lege lijst zette ook de
     ratchet uit (geen `quality_snapshot` bij claim). De agent bepaalde dus zelf of hij
     gecontroleerd werd.
  2. `register_preexisting()` had geen severity-parameter. Alles wat via die ingang
     binnenkwam viel in de MEDIUM/LOW-tak en was met een OP-nummer weg te escaleren --
     terwijl HIGH via `submit_gate2_review()` wel aantoonbaar blokkeerde.
  3. De ratchet kende voor `.py` alleen datetime_naive, tenant_id_in_body, non_ascii en
     debug_var. Python-`Any` (7113 regels, ADR-036 OP-231/OP-232) was onzichtbaar.

Mutatiebewijs in BEIDE richtingen, zoals .claude/rules/quality-gates.md eist: elke
blokkade heeft een test die hem laat blokkeren EN een test die aantoont dat een legitiem
geval nog doorkomt. Zonder die tweede helft is "weiger alles" een geldige oplossing.

De state gaat naar tmp_path: de echte `.git/sanskritisetu-mcp-state.json` is gedeeld met
andere sessies en mag door een test niet worden aangeraakt.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, "mcp-server")

import store  # noqa: E402
from tools import coordination, quality  # noqa: E402

EEN_ANY_REGEL = "from typing import Any\n\nx: dict[str, Any] = {}\n"


@pytest.fixture
def eigen_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Leid de gedeelde state om naar tmp_path."""
    pad = tmp_path / "state.json"
    monkeypatch.setattr(store, "STATE_PATH", pad)
    monkeypatch.setattr(store, "LOCK_PATH", pad.with_suffix(".lock"))
    return pad


def _nieuwe_taak(task_id: str, files: list[str] | None = None) -> None:
    aangemaakt = coordination.register_task(task_id, "toets", "P2", None, files or [])
    assert aangemaakt["ok"], aangemaakt
    geclaimd = coordination.claim_task(task_id, "toetser", "iter/toets")
    assert geclaimd["ok"], geclaimd


def _zet_afleiding(
    monkeypatch: pytest.MonkeyPatch, paden: list[str] | None, fout: bool = False
) -> None:
    """Vervang de git-afleiding, zodat de poortlogica los van git te toetsen is."""

    def nep(*args: Any, **kwargs: Any) -> list[str]:  # noqa: ARG001
        if fout:
            raise subprocess.CalledProcessError(128, ["git", "diff"])
        assert paden is not None
        return paden

    monkeypatch.setattr(coordination, "_changed_files_since", nep, raising=False)


@pytest.mark.unit
def _git_omgeving() -> dict[str, str]:
    """De omgeving ZONDER de git-variabelen. Zonder dit herinitialiseert `git init` de
    ECHTE repo in plaats van de tijdelijke.

    Gemeten 2026-09-16, en het kostte een halve dag zoeken. `git push` zet `GIT_DIR` in de
    omgeving van zijn hooks -- maar ALLEEN als je vanuit een gelinkte worktree pusht:

        push vanuit een gewone repo        -> GIT_DIR leeg
        push vanuit een gelinkte worktree  -> GIT_DIR=<repo>/.git/worktrees/<naam>

    De pre-push hook van dit project start pytest, pytest erft die variabele, en `git`
    kiest ALTIJD `GIT_DIR` boven `cwd`. Het gevolg, in een wegwerp-repo nagebouwd:

        cd <lege map>; GIT_DIR=<worktree-gitdir> git init -q
        -> rc=0, de lege map blijft LEEG, en core.bare in de GEDEELDE config gaat op true

    Daarmee is de hele repo voor git ineens "bare": `git status`, `git grep` en
    `git rev-parse --show-toplevel` falen met "fatal: this operation must be run in a work
    tree", in de hoofdmap EN in elke worktree. Dat liet op 2026-09-16 twee volledige
    poortruns stuklopen op 32 failures die niets met de gewijzigde code te maken hadden.

    Het onderscheid dat het verklaart: wijst `GIT_DIR` naar een GEWONE `.git`, dan zet
    `git init` core.bare op FALSE en is er geen schade. Wijst hij naar een
    WORKTREE-gitdir, dan op TRUE. Pushen vanuit een worktree is dus geen detail maar de
    voorwaarde.

    Gevonden door sanskritisetu-org-39, die de proceskoppeling ving met een watcher op
    .git/config; mechanisme daarna door beide sessies los van elkaar gereproduceerd.
    """
    return {sleutel: waarde for sleutel, waarde in os.environ.items() if not sleutel.startswith("GIT_")}


class TestDePoortMeetDeEchteWijzigingen:
    """Gate 2 en de ratchet mogen niet afhangen van wat de agent zelf opgeeft."""

    def test_lege_bestandenlijst_met_echte_wijziging_eist_gate2(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De ontsnapping: geen bestanden opgeven en toch code wijzigen."""
        _zet_afleiding(monkeypatch, ["src/core/shared/interfaces.py"])
        _nieuwe_taak("t-leeg")
        resultaat = coordination.complete_task("t-leeg", "toetser", "bewijs: niets")
        assert resultaat["ok"] is False, resultaat
        assert "Gate 2" in resultaat["reason"]

    def test_zonder_enige_wijziging_kan_de_taak_dicht(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De legitieme kant: een taak die niets heeft aangeraakt hoort af te kunnen."""
        _zet_afleiding(monkeypatch, [])
        _nieuwe_taak("t-niets")
        resultaat = coordination.complete_task("t-niets", "toetser", "bewijs: alleen gelezen")
        assert resultaat["ok"] is True, resultaat

    def test_een_mislukte_afleiding_sluit_de_poort(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Geen git, geen antwoord: dan gaat de poort DICHT en niet open."""
        _zet_afleiding(monkeypatch, None, fout=True)
        _nieuwe_taak("t-kapot")
        resultaat = coordination.complete_task("t-kapot", "toetser", "bewijs")
        assert resultaat["ok"] is False, resultaat
        assert "afleiding" in resultaat["reason"].lower()

    def test_gate2_ingediend_laat_de_taak_dicht(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tweede legitieme kant: met Gate 2 ingediend moet afsluiten wel kunnen."""
        _zet_afleiding(monkeypatch, ["docs/whatever.md"])
        _nieuwe_taak("t-gate2")
        data = store.read()
        assert quality.submit_gate2_review(data["tasks"]["t-gate2"], "code-reviewer", [])["ok"]
        store.write(data)
        resultaat = coordination.complete_task("t-gate2", "toetser", "bewijs")
        assert resultaat["ok"] is True, resultaat


@pytest.mark.unit
class TestSeverityOpEenLosGeregistreerdIssue:
    """HIGH moet blokkeren via BEIDE ingangen, niet alleen via de Gate 2-review."""

    def test_high_via_register_preexisting_blokkeert(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _zet_afleiding(monkeypatch, [])
        _nieuwe_taak("t-high")
        data = store.read()
        toegevoegd = quality.register_preexisting(
            data["tasks"]["t-high"], "X-01", "src/x.py", 10, "security", "iets ergs", "HIGH"
        )
        store.write(data)
        assert toegevoegd["ok"], toegevoegd

        resultaat = coordination.complete_task("t-high", "toetser", "bewijs")
        assert resultaat["ok"] is False, resultaat
        assert "HIGH" in resultaat["reason"]

        data = store.read()
        # OP-232 en niet een verzonnen nummer: tests/architecture/
        # test_adr036_references_have_a_register_row.py verbiedt een verwijzing naar een
        # OP-nummer dat niet als registerrij bestaat, en die guard scant ook tests/. Mijn
        # eerste versie gebruikte een verzonnen nummer en maakte daarmee de volledige
        # selectie rood (1 failed van 16456) -- en het NOEMEN van dat nummer in deze
        # comment liet de guard een tweede keer afgaan, wat precies laat zien dat hij op
        # tekst zoekt en niet op code. OP-232 is de bestaande open rij over de Any-schuld.
        escalatie = quality.escalate_preexisting(
            data["tasks"]["t-high"], "X-01", "OP-232", "een reden van meer dan twintig tekens"
        )
        assert escalatie["ok"] is False, escalatie

    def test_medium_via_register_preexisting_is_wel_te_escaleren(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De legitieme kant: MEDIUM mag met een OP-nummer worden doorgeschoven."""
        _zet_afleiding(monkeypatch, [])
        _nieuwe_taak("t-medium")
        data = store.read()
        quality.register_preexisting(
            data["tasks"]["t-medium"], "X-02", "src/x.py", 10, "other", "iets kleins", "MEDIUM"
        )
        escalatie = quality.escalate_preexisting(
            data["tasks"]["t-medium"], "X-02", "OP-232", "een reden van meer dan twintig tekens"
        )
        store.write(data)
        assert escalatie["ok"] is True, escalatie
        assert coordination.complete_task("t-medium", "toetser", "bewijs")["ok"] is True

    def test_een_onzinnige_severity_wordt_geweigerd(self, eigen_state: Path) -> None:
        """Zonder validatie is severity een vrij tekstveld en betekent HIGH niets."""
        taak: dict[str, object] = {}
        resultaat = quality.register_preexisting(
            taak, "X-03", "src/x.py", 1, "other", "iets", "KRITIEK"
        )
        assert resultaat["ok"] is False, resultaat


@pytest.mark.unit
class TestPythonAnyInDeRatchet:
    """De ratchet moet Python-`Any` zien; dat is de schuld waar dit project op zit."""

    def test_scan_file_telt_python_any(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(quality, "REPO_ROOT", tmp_path)
        (tmp_path / "voorbeeld.py").write_text(EEN_ANY_REGEL, encoding="utf-8")
        metrieken = quality.scan_file("voorbeeld.py")
        assert metrieken.get("py_any") == 1, metrieken

    def test_een_typescriptbestand_houdt_ts_any_en_krijgt_geen_py_any(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De legitieme kant: de bestaande metriek voor .ts blijft ongemoeid."""
        monkeypatch.setattr(quality, "REPO_ROOT", tmp_path)
        (tmp_path / "voorbeeld.ts").write_text("const x: any = 1;\n", encoding="utf-8")
        metrieken = quality.scan_file("voorbeeld.ts")
        assert "ts_any" in metrieken
        assert "py_any" not in metrieken

    def test_een_extra_any_is_een_regressie(self) -> None:
        voor = {"src/x.py": {"py_any": 2}}
        na = {"src/x.py": {"py_any": 3}}
        rapport = quality.compare_snapshots(voor, na)
        assert rapport["ok"] is False
        assert rapport["regressions"][0]["metric"] == "py_any"

    def test_gelijk_aantal_any_is_geen_regressie(self) -> None:
        """Zonder deze helft zou "alles blokkeren" een geldige oplossing zijn."""
        gelijk = {"src/x.py": {"py_any": 2}}
        assert quality.compare_snapshots(gelijk, {"src/x.py": {"py_any": 2}})["ok"] is True


@pytest.mark.unit
class TestDeAfleidingUitGit:
    """De afleiding zelf, tegen een echte tijdelijke git-repo."""

    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            env=_git_omgeving(),
            check=True,
            capture_output=True,
            text=True,
        )

    def _init(self, repo: Path) -> str:
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t.t")
        self._git(repo, "config", "user.name", "toets")
        (repo / "basis.py").write_text("a = 1\n", encoding="utf-8")
        self._git(repo, "add", "basis.py")
        self._git(repo, "commit", "-qm", "basis")
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            env=_git_omgeving(),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_ziet_gecommit_staged_unstaged_en_ongetrackt(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        sha = self._init(repo)

        (repo / "basis.py").write_text("a = 2\n", encoding="utf-8")        # unstaged
        (repo / "gestaged.py").write_text("b = 1\n", encoding="utf-8")
        self._git(repo, "add", "gestaged.py")                               # staged
        (repo / "nieuw.py").write_text("c = 1\n", encoding="utf-8")        # ongetrackt
        (repo / "gecommit.py").write_text("d = 1\n", encoding="utf-8")
        self._git(repo, "add", "gecommit.py")
        self._git(repo, "commit", "-qm", "erna")                            # gecommit

        gevonden = set(coordination._changed_files_since(sha, repo))
        verwacht = {"basis.py", "gestaged.py", "nieuw.py", "gecommit.py"}
        assert verwacht <= gevonden, gevonden

    def test_geen_wijziging_geeft_een_lege_lijst(self, tmp_path: Path) -> None:
        """De legitieme kant: een schone boom levert niets op."""
        repo = tmp_path / "schoon"
        sha = self._init(repo)
        assert coordination._changed_files_since(sha, repo) == []


@pytest.mark.unit
class TestDeTellerEnDeMeetbasis:
    """De twee stille faalvormen: een teller die niet laadt en een basis die meeschuift."""

    def test_de_any_teller_laadt_in_deze_repo(self) -> None:
        """Een teller die niet laadt maakt de py_any-metriek geruisloos onzichtbaar.

        Gemeten 2026-09-10: de eerste versie laadde `scripts/scan_any_usage.py` met
        `importlib` zonder de module in `sys.modules` te zetten. `@dataclass` zoekt
        tijdens het decoreren `sys.modules[cls.__module__]` op, faalde met
        "NoneType object has no attribute __dict__", en `_count_py_any()` gaf None --
        waarna de metriek werd weggelaten en de poort niets meer over `Any` zei. Alle
        andere tests bleven groen. Deze test is het vangnet daarvoor.
        """
        quality._any_teller.cache_clear()
        assert quality._any_teller() is not None
        metrieken = quality.scan_file("src/core/shared/interfaces.py")
        assert "py_any" in metrieken, metrieken

    def test_de_meetbasis_schuift_niet_naar_voren_bij_herclaimen(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """release + herclaim mag de claim_head niet naar de nieuwe HEAD verplaatsen.

        Anders valt alles wat tussen de eerste claim en het herclaimen is gecommit buiten
        de afleiding. Gemeten door de Gate-2-reviewer op 2026-09-10.
        """
        monkeypatch.setattr(coordination, "_current_head", lambda *_a, **_k: "aaaaaaa")
        _nieuwe_taak("t-basis")
        assert store.read()["tasks"]["t-basis"]["claim_head"] == "aaaaaaa"

        coordination.release_task("t-basis", "toetser", "pauze")
        monkeypatch.setattr(coordination, "_current_head", lambda *_a, **_k: "bbbbbbb")
        coordination.claim_task("t-basis", "toetser", "iter/toets")
        assert store.read()["tasks"]["t-basis"]["claim_head"] == "aaaaaaa"

    def test_release_wist_de_gate2_stand(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een Gate 2 over ronde 1 mag niet gelden voor het werk van ronde 2."""
        _zet_afleiding(monkeypatch, ["src/x.py"])
        _nieuwe_taak("t-reset")
        data = store.read()
        quality.submit_gate2_review(data["tasks"]["t-reset"], "code-reviewer", [])
        store.write(data)
        assert store.read()["tasks"]["t-reset"]["gate2_submitted"] is True

        coordination.release_task("t-reset", "toetser", "pauze")
        coordination.claim_task("t-reset", "toetser", "iter/toets")
        assert "gate2_submitted" not in store.read()["tasks"]["t-reset"]
        resultaat = coordination.complete_task("t-reset", "toetser", "bewijs")
        assert resultaat["ok"] is False
        assert "Gate 2" in resultaat["reason"]

    def test_een_niet_geclaimde_taak_is_niet_af_te_sluiten(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zonder claim is er geen meetbasis, dus mag afsluiten niet.

        Gemeten door de Gate-2-reviewer op 2026-09-10: register_task(files=[]) plus
        complete_task() gaf ok=True zonder claim, zonder Gate 2 en zonder ratchet. De
        eigenaarscheck keek alleen naar taken die AL in behandeling waren.
        """
        _zet_afleiding(monkeypatch, ["src/x.py"])
        assert coordination.register_task("t-onclaimed", "toets", "P2", None, [])["ok"]
        resultaat = coordination.complete_task("t-onclaimed", "wie-dan-ook", "bewijs")
        assert resultaat["ok"] is False, resultaat
        assert "claim" in resultaat["reason"].lower()

    def test_een_geboekte_any_blokkeert_niet(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """py_any telt alleen ONGEBOEKTE Any -- dezelfde grens als de CI-poort.

        Anders blokkeert deze poort een `Any` die repo-breed juist is toegestaan (met
        TODO-marker plus een baseline-wijziging), en dat verschil leert agenten de poort
        te omzeilen.
        """
        monkeypatch.setattr(quality, "REPO_ROOT", tmp_path)
        (tmp_path / "geboekt.py").write_text(
            "from typing import Any\n\n"
            "x: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type\n",
            encoding="utf-8",
        )
        assert quality.scan_file("geboekt.py").get("py_any") == 0


@pytest.mark.unit
class TestDeAfleidingBijLastigePaden:
    """Rename en niet-ASCII bestandsnamen, allebei gemeten door de Gate-2-reviewer."""

    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            env=_git_omgeving(),
            check=True,
            capture_output=True,
            text=True,
        )

    def _repo_met_een_bestand(self, repo: Path, naam: str) -> str:
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t.t")
        self._git(repo, "config", "user.name", "toets")
        (repo / naam).write_text("from typing import Any\n\nx: Any = 1\n", encoding="utf-8")
        self._git(repo, "add", naam)
        self._git(repo, "commit", "-qm", "basis")
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            env=_git_omgeving(),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_een_rename_levert_oud_en_nieuw_pad(self, tmp_path: Path) -> None:
        """Zonder --no-renames gaf git alleen het nieuwe pad.

        Het oude pad viel dan buiten de "voor"-meting, en `git show <sha>:<nieuw pad>`
        bestaat niet -- waardoor een pure `git mv` als verse regressie las op elke `Any`
        in dat bestand. Gemeten door de Gate-2-reviewer op 2026-09-10.
        """
        repo = tmp_path / "hernoem"
        sha = self._repo_met_een_bestand(repo, "oud.py")
        self._git(repo, "mv", "oud.py", "nieuw.py")
        self._git(repo, "commit", "-qm", "hernoemd")
        gevonden = set(coordination._changed_files_since(sha, repo))
        assert {"oud.py", "nieuw.py"} <= gevonden, gevonden

    def test_een_bestandsnaam_met_niet_ascii_blijft_leesbaar(self, tmp_path: Path) -> None:
        """core.quotepath escapte zo'n naam naar "caf\\303\\251.py" -- met quotes en al.

        Het pad viel daarmee buiten de extensiecontrole en het bestand werd niet gemeten.
        """
        repo = tmp_path / "accent"
        sha = self._repo_met_een_bestand(repo, "basis.py")
        # De naam staat met een escape in de bron: het BESTAND krijgt een niet-ASCII
        # teken in zijn naam, de broncode zelf blijft ASCII (SOUL-principe 5).
        (repo / "caf\u00e9.py").write_text("x = 1\n", encoding="utf-8")
        gevonden = coordination._changed_files_since(sha, repo)
        met_py = [p for p in gevonden if p.endswith(".py")]
        assert len(met_py) == len(gevonden), gevonden
        assert not any(p.startswith('"') for p in gevonden), gevonden


@pytest.mark.unit
class TestDeMeetbasisStaatInHetAntwoord:
    """Een werkkopie-meting mag niet doorgaan voor een volledige meting."""

    def test_een_normale_claim_meldt_de_commit_als_basis(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De sterke kant: geclaimd op een echte commit, dus die commit is de basis."""
        _zet_afleiding(monkeypatch, [])
        _nieuwe_taak("t-basis-ok")
        resultaat = coordination.complete_task("t-basis-ok", "toetser", "bewijs")
        assert resultaat["ok"] is True, resultaat
        assert resultaat["meetbasis"].startswith("commit "), resultaat
        assert "meetbasis_waarschuwing" not in resultaat, resultaat

    def test_zonder_claim_head_meldt_de_poort_de_zwakkere_meting(
        self, eigen_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De zwakke kant: geen meetbasis, dus alleen de werkkopie -- en dat staat erbij."""
        _nieuwe_taak("t-basis-weg")
        data = store.read()
        data["tasks"]["t-basis-weg"].pop("claim_head", None)
        store.write(data)
        monkeypatch.setattr(coordination, "_wijzigingen_in_werkkopie", lambda *a, **k: [])
        resultaat = coordination.complete_task("t-basis-weg", "toetser", "bewijs")
        assert resultaat["ok"] is True, resultaat
        assert resultaat["meetbasis"] == "werkkopie", resultaat
        assert "WERKKOPIE" in resultaat["meetbasis_waarschuwing"], resultaat


@pytest.mark.unit
class TestValidateBriefVindtEenRelatiefPad:
    """Een relatief briefpad hoort tegen de repo te worden opgelost, niet tegen de cwd."""

    def test_een_relatief_pad_vanuit_de_repo_wordt_gevonden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De zwakke plek: een relatief pad terwijl de cwd NIET de repo is.

        De chdir is de kern van deze toets. Zonder hem draait pytest toevallig al vanuit
        de repowortel, en dan slaagt de test ook ZONDER de fix -- gemeten 2026-09-11:
        eerste versie van deze toets bleef groen met de fix eruit gehaald. Precies de
        holle guard uit valkuilen/SKILL.md.
        """
        brief = coordination.REPO_ROOT / "docs" / "agent-briefs" / "generated" / "_toets-relatief.md"
        brief.write_text("Geen placeholders hier.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        try:
            resultaat = coordination.validate_brief(
                "docs/agent-briefs/generated/_toets-relatief.md"
            )
        finally:
            brief.unlink()
        assert resultaat["ok"] is True, resultaat

    def test_een_absoluut_pad_blijft_werken(self, tmp_path: Path) -> None:
        """De legitieme kant die al werkte mag niet sneuvelen."""
        brief = tmp_path / "brief.md"
        brief.write_text("Niets open.\n", encoding="utf-8")
        assert coordination.validate_brief(str(brief))["ok"] is True

    def test_een_bestand_dat_echt_niet_bestaat_blijft_een_fout(self, tmp_path: Path) -> None:
        """Anders is "vind altijd iets" een geldige oplossing."""
        resultaat = coordination.validate_brief("docs/agent-briefs/generated/_bestaat-niet.md")
        assert resultaat["ok"] is False, resultaat
        assert "niet gevonden" in resultaat["reason"].lower()

    def test_een_onvervangen_placeholder_blokkeert_nog_steeds(self, tmp_path: Path) -> None:
        """De eigenlijke taak van deze functie moet onaangetast zijn."""
        brief = tmp_path / "brief.md"
        brief.write_text("Branch: [HUIDIGE BRANCH]\n", encoding="utf-8")
        resultaat = coordination.validate_brief(str(brief))
        assert resultaat["ok"] is False, resultaat
        assert "[HUIDIGE BRANCH]" in resultaat["placeholders_found"]

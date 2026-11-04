"""Gedeelde ontleding van de CD-workflows (ADR-036 OP-91/OP-102/HIGH-3).

**Waarom dit een gedeelde module is en geen tweede kopie per guard.** Er stonden twee
tokenizers in omloop die op hetzelfde script een ander antwoord gaven, en dat is exact de
faalvorm van deze reeks: twee plekken die uiteenlopen zonder dat iets dat merkt. De
plannerguard en de bootguard delen daarom EEN ontleding.

**De regel die hier wordt afgedwongen: toets STRUCTUUR, geen TEKST.** Elke guard die eerder
op dit bestand leunde is gesneuveld op een substring-toets -- de modulenaam in een comment,
in een env-var-waarde, of in een string die er toevallig op leek. Daarom: comments eruit,
regels samenvoegen, tokeniseren, en pas dan naar ARGUMENTEN kijken.

**Fail-closed, altijd.** Kan een script niet getokeniseerd worden, dan gooit deze module.
Een terugval op "dan maar tekst zoeken" is precies het mechanisme waarmee een guard stil
groen wordt: een enkele ongebalanceerde apostrof in een Nederlandstalig comment zou de hele
hardening uitschakelen in een diff die er onschuldig uitziet.

Bestand begint bewust met een underscore: pytest verzamelt hem dan niet als testmodule.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: `${{ env.ACR }}` bevat spaties en is in de scripts meestal NIET aangehaald. Tokeniseren
#: knipt zo'n expressie in stukken, en dan is `--image ${{ env.ACR }}/worker:...` opeens zes
#: tokens waarvan geen enkele het image is. Eerst de spaties eruit, dan is het een token.
#: Gemeten: zonder deze stap vond de scan NUL worker-images terwijl er zes zijn.
_EXPRESSIE = re.compile(r"\$\{\{\s*(.*?)\s*\}\}", re.DOTALL)


def _plak_expressies(script: str) -> str:
    """`${{ x.y }}` -> `${{x.y}}`, zodat het een enkel token blijft."""
    return _EXPRESSIE.sub(lambda m: "${{" + re.sub(r"\s+", "", m.group(1)) + "}}", script)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"

#: Beide extensies. `cd-production.yaml` hernoemen liet de workflow eerder STIL uit de scan
#: verdwijnen terwijl het vangnet groen bleef op de andere workflow.
CD_GLOB = "cd-*.y*ml"

#: Condities waaronder een stap NIET tot het normale deploypad hoort. Bewust een korte,
#: expliciete lijst en geen expressie-evaluator: alles wat we niet herkennen telt als ACTIEF,
#: zodat onbekende syntaxis een stap nooit stil uit de guard laat vallen.
_INACTIEVE_CONDITIES = ("false", "failure()", "cancelled()")


class WorkflowOntleedFout(RuntimeError):
    """Het script kon niet worden getokeniseerd. Fail-closed: dit is nooit 'dan maar niet'."""


def logische_regels(script: str) -> list[str]:
    """Het script opgeknipt in logische commandoregels, AANHALINGSTEKEN-BEWUST.

    Een regel-voor-regel benadering is hier aantoonbaar fout, en dat is gemeten en niet
    bedacht: `.github/workflows/cd-staging.yml` bevat een `python3 -c '...'`-blok dat over
    meerdere regels loopt. Naief per regel splitsen levert `python3 -c '` op, en shlex gooit
    daar terecht op. Een guard die die fout opvangt met "dan maar overslaan" is fail-open.

    Daarom een kleine scanner die bijhoudt of we binnen aanhalingstekens staan:
    - een `#` BUITEN aanhalingstekens begint een comment tot het regeleinde;
    - een backslash buiten aanhalingstekens escapet het volgende teken (ook een regeleinde);
    - een regeleinde buiten aanhalingstekens beeindigt de logische regel.

    Blijft een aanhalingsteken aan het eind van het script openstaan, dan gooit dit -- dat is
    een onontleedbaar script en geen reden om de bewaking uit te zetten.
    """
    script = _plak_expressies(script)
    regels: list[str] = []
    buffer: list[str] = []
    in_enkel = in_dubbel = False
    in_comment = False
    i = 0

    while i < len(script):
        teken = script[i]

        if in_comment:
            if teken == "\n":
                in_comment = False
                if "".join(buffer).strip():
                    regels.append("".join(buffer))
                buffer = []
            i += 1
            continue

        if teken == "\\" and not in_enkel and i + 1 < len(script):
            # Regelvervolg: het regeleinde verdwijnt, de regel loopt door.
            if script[i + 1] == "\n":
                buffer.append(" ")
            else:
                buffer.append(teken)
                buffer.append(script[i + 1])
            i += 2
            continue

        if teken == "'" and not in_dubbel:
            in_enkel = not in_enkel
        elif teken == '"' and not in_enkel:
            in_dubbel = not in_dubbel
        elif teken == "#" and not in_enkel and not in_dubbel:
            in_comment = True
            i += 1
            continue
        elif teken == "\n" and not in_enkel and not in_dubbel:
            if "".join(buffer).strip():
                regels.append("".join(buffer))
            buffer = []
            i += 1
            continue

        buffer.append(teken)
        i += 1

    if in_enkel or in_dubbel:
        raise WorkflowOntleedFout(
            "Het script eindigt met een openstaand aanhalingsteken; het is niet te ontleden. "
            "Fail-closed: een guard die hier terugvalt op een tekstzoektocht is met een enkele "
            "apostrof uit te zetten."
        )
    if "".join(buffer).strip():
        regels.append("".join(buffer))
    return regels


def tokeniseer(regel: str) -> list[str]:
    """Een logische regel als tokens. Gooit bij onontleedbare invoer -- nooit een terugval."""
    try:
        return shlex.split(regel)
    except ValueError as exc:
        raise WorkflowOntleedFout(
            f"Kon deze regel niet tokeniseren: {regel!r} ({exc}). Fail-closed: een guard die "
            "hierop terugvalt op een tekstzoektocht is met een enkele apostrof uit te zetten."
        ) from exc


@dataclass(frozen=True)
class Stap:
    """Een workflowstap met het script dat hij draait."""

    workflow: str
    naam: str
    script: str
    actief: bool


def _stap_is_actief(stap: dict[str, Any], job: dict[str, Any]) -> bool:
    """Hoort deze stap tot het normale deploypad? (ADR-036 HIGH-3)

    `step["if"]` werd niet gelezen. Een deploystap op `if: false` telde daardoor mee als
    "de planner wordt gestart", terwijl er in Azure niets draaide.
    """
    for conditie in (stap.get("if"), job.get("if")):
        if conditie is None:
            continue
        tekst = str(conditie).strip().lower()
        if any(merker in tekst for merker in _INACTIEVE_CONDITIES):
            return False
    return True


def cd_stappen() -> list[Stap]:
    """Elke stap uit elke CD-workflow, met zijn script.

    Naast `run:` ook `with.inlineScript` (`azure/cli`-action). Die vorm draait exact dezelfde
    commando's, maar viel volledig buiten de scan -- een omzeiling die er in een diff uitziet
    als een nette refactor naar een officiele action.
    """
    import yaml

    stappen: list[Stap] = []
    for workflow in sorted(WORKFLOW_DIR.glob(CD_GLOB)):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job in (parsed.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for stap in job.get("steps") or []:
                if not isinstance(stap, dict):
                    continue
                script = str(stap.get("run") or "")
                inline = (stap.get("with") or {}).get("inlineScript") if stap.get("with") else None
                if inline:
                    script = f"{script}\n{inline}"
                if not script.strip():
                    continue
                stappen.append(
                    Stap(
                        workflow=workflow.name,
                        naam=str(stap.get("name", "?")),
                        script=script,
                        actief=_stap_is_actief(stap, job),
                    )
                )
    return stappen


#: `cat > bestand << TAG` ... `TAG`. De YAML-vorm van een deploy schrijft de app-definitie
#: eerst naar een bestand en geeft dat mee met `--yaml`. Zonder deze ontleding ziet een guard
#: die alleen naar `--command`/`--env-vars` kijkt NIETS -- gemeten 2026-08-30: twee guards
#: stonden om die reden rood terwijl de deploy zelf correct was (ADR-036 OP-64/OP-87).
_HEREDOC = re.compile(
    r"^[ \t]*cat[ \t]+>[ \t]*(?P<bestand>[^\s<>]+)[ \t]*<<[-]?[ \t]*"
    r"(?P<q>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)(?P=q)[ \t]*$",
    re.MULTILINE,
)

#: `$( ... )` in een heredoc is shell, geen YAML. De scheduler-definitie hangt er een
#: voorwaardelijk env-blok mee aan. Weghalen VOOR het parsen; wat overblijft is de vorm die
#: altijd wordt gedeployd. Een voorwaardelijk deel telt dus niet mee -- bewust: een guard mag
#: niet groen worden door een tak die alleen onder een secret-conditie bestaat.
_SHELL_SUBSTITUTIE = re.compile(r"\$\([^)]*\)")


def heredoc_bestanden(script: str) -> dict[str, str]:
    """De bestanden die dit stapscript met een heredoc wegschrijft, als {naam: inhoud}."""
    gevonden: dict[str, str] = {}
    regels = script.split("\n")
    i = 0
    while i < len(regels):
        treffer = _HEREDOC.match(regels[i])
        if treffer is None:
            i += 1
            continue
        tag = treffer.group("tag")
        body: list[str] = []
        i += 1
        while i < len(regels) and regels[i].strip() != tag:
            body.append(regels[i])
            i += 1
        if i >= len(regels):
            raise WorkflowOntleedFout(
                f"Heredoc {tag!r} wordt nooit afgesloten in dit stapscript. Fail-closed: een "
                "guard die hier doorgaat leest een halve app-definitie."
            )
        gevonden[treffer.group("bestand")] = "\n".join(body)
        i += 1
    return gevonden


def ontleed_manifest(tekst: str) -> dict[str, Any]:
    """Een heredoc-body als Container-App-manifest. Gooit bij onontleedbare invoer."""
    import yaml

    schoon = _SHELL_SUBSTITUTIE.sub("", _plak_expressies(tekst))
    try:
        geparsed = yaml.safe_load(schoon)
    except yaml.YAMLError as exc:
        raise WorkflowOntleedFout(
            f"De app-definitie in de heredoc is geen geldige YAML ({exc}). Fail-closed: "
            "zonder ontleding weet deze guard niet wat er gedeployd wordt."
        ) from exc
    if not isinstance(geparsed, dict):
        raise WorkflowOntleedFout(
            "De app-definitie in de heredoc levert geen afbeelding op; onbruikbaar als manifest."
        )
    return geparsed


@dataclass(frozen=True)
class ContainerAppCommando:
    """Een `az containerapp create|update`-aanroep, ontleed tot argumenten."""

    workflow: str
    stap: str
    actie: str
    tokens: tuple[str, ...]
    #: De app-definitie uit `--yaml <bestand>`, als die vorm is gebruikt. Buiten de
    #: vergelijking gehouden: een dict is niet hashbaar en deze klasse is `frozen`.
    manifest: dict[str, Any] | None = field(default=None, compare=False)

    def waarden_van(self, *vlaggen: str) -> list[str]:
        """De argumenten die op `vlag` volgen, tot de volgende vlag.

        Dit IS het verschil met een substring-toets: `--command "python" "-m" "src.workers.scheduler"`
        levert hier de argumenten van `--command`, terwijl de modulenaam in een env-var-waarde
        of in een comment nergens opduikt.

        **Alleen `--`-tokens beeindigen de reeks, niet elk streepje.** Anders eindigt
        `--command "python" "-m" "src.workers.scheduler"` bij `-m` en verdwijnt precies de
        modulenaam die we willen toetsen -- gemeten, dit was de eerste versie. De prijs is dat
        een korte optie als `-o tsv` bij de voorgaande vlag wordt gerekend; dat raakt geen
        enkele `create|update`-aanroep, want die gebruiken uitsluitend lange opties.
        """
        gevonden: list[str] = []
        verzamelen = False
        for token in self.tokens:
            if token in vlaggen:
                verzamelen = True
                continue
            if token.startswith("--"):
                verzamelen = False
                continue
            if verzamelen:
                gevonden.append(token)
        return gevonden

    def _containers(self) -> list[dict[str, Any]]:
        """De containers uit het `--yaml`-manifest, of een lege lijst bij de vlaggenvorm."""
        if not self.manifest:
            return []
        sjabloon = (self.manifest.get("properties") or {}).get("template") or {}
        containers = sjabloon.get("containers") or []
        return [c for c in containers if isinstance(c, dict)]

    def env_vars(self) -> dict[str, str]:
        """De omgeving die dit commando op de app zet, als afbeelding.

        Twee vormen, allebei geldig en allebei in gebruik in dit project:

        - de vlaggenvorm `--env-vars "NAAM=waarde"`;
        - de manifestvorm `env: [{name: NAAM, value: ...}]` of `{name: NAAM, secretRef: x}`.

        Een `secretRef` wordt weergegeven als `secretref:<naam>`, exact zoals de vlaggenvorm
        hem schrijft, zodat een guard beide vormen op dezelfde manier kan toetsen.
        """
        omgeving: dict[str, str] = {}
        for container in self._containers():
            for ingang in container.get("env") or []:
                if not isinstance(ingang, dict) or not ingang.get("name"):
                    continue
                if "secretRef" in ingang:
                    omgeving[str(ingang["name"])] = f"secretref:{ingang['secretRef']}"
                else:
                    omgeving[str(ingang["name"])] = str(ingang.get("value", ""))
        for toewijzing in self.waarden_van("--env-vars", "--set-env-vars"):
            naam, _, waarde = toewijzing.partition("=")
            if naam:
                omgeving[naam] = waarde
        return omgeving

    def secret_namen(self) -> set[str]:
        """De secrets die dit commando op de app definieert, uit beide vormen."""
        namen: set[str] = set()
        if self.manifest:
            configuratie = (self.manifest.get("properties") or {}).get("configuration") or {}
            for ingang in configuratie.get("secrets") or []:
                if isinstance(ingang, dict) and ingang.get("name"):
                    namen.add(str(ingang["name"]))
        for toewijzing in self.waarden_van("--secrets", "--set-secrets"):
            naam, _, _rest = toewijzing.partition("=")
            if naam:
                namen.add(naam)
        return namen

    def start_argumenten(self) -> list[str]:
        """Het startcommando van de container: `command` gevolgd door `args`.

        De vlaggenvorm zet dat in `--command`/`--args`, de manifestvorm in de sleutels
        `command` en `args` van de container. `az containerapp create --command "python" "-m"
        "..."` bestaat niet als werkende aanroep (de argparser van az breekt op de leidende
        streep), dus de manifestvorm is de enige manier om een `-m`-start te deployen -- en
        precies daarom moet een guard hem kunnen lezen.
        """
        uit_vlaggen = self.waarden_van("--command") + self.waarden_van("--args")
        if uit_vlaggen:
            return uit_vlaggen
        argumenten: list[str] = []
        for container in self._containers():
            argumenten.extend(str(x) for x in (container.get("command") or []))
            argumenten.extend(str(x) for x in (container.get("args") or []))
        return argumenten

    def min_replicas(self) -> int | None:
        """Het minimum aantal replicas, uit beide vormen. `None` = niet opgegeven."""
        uit_vlag = self.waarden_van("--min-replicas")
        if uit_vlag and uit_vlag[0].lstrip("-").isdigit():
            return int(uit_vlag[0])
        if self.manifest:
            schaal = ((self.manifest.get("properties") or {}).get("template") or {}).get(
                "scale"
            ) or {}
            waarde = schaal.get("minReplicas")
            if isinstance(waarde, int):
                return waarde
            if isinstance(waarde, str) and waarde.lstrip("-").isdigit():
                return int(waarde)
        return None

    def image(self) -> str:
        waarden = self.waarden_van("--image")
        if waarden:
            return waarden[0]
        for container in self._containers():
            if container.get("image"):
                return str(container["image"])
        return ""

    def naam(self) -> str:
        waarden = self.waarden_van("--name")
        if waarden:
            return waarden[0]
        if self.manifest and self.manifest.get("name"):
            return str(self.manifest["name"])
        return ""


def secret_namen_per_stap(alleen_actief: bool = True) -> dict[tuple[str, str], set[str]]:
    """Per (workflow, stap): de secretnamen die daar met `az containerapp secret set` worden gezet.

    **Waarom dit erbij hoort.** `az containerapp update` KENT geen `--set-secrets`. Sinds
    2026-08-27 zet de worker-deploy zijn secrets daarom in een apart
    `containerapp secret set`-commando, direct boven de `update` in dezelfde stap. Een guard
    die alleen naar het `create|update`-commando zelf kijkt, ziet de secretwaarde dan niet
    meer -- gemeten 2026-08-30: precies daarop stond de REDIS_URL-guard rood terwijl de
    waarde wel degelijk werd gezet.

    Bewust per STAP en niet workflow-breed: secrets die in een andere stap worden gezet horen
    bij een andere app, en die mogen deze toets niet groen maken.
    """
    per_stap: dict[tuple[str, str], set[str]] = {}
    for stap in cd_stappen():
        if alleen_actief and not stap.actief:
            continue
        for regel in logische_regels(stap.script):
            tokens = tokeniseer(regel)
            if "containerapp" not in tokens or "secret" not in tokens or "set" not in tokens:
                continue
            commando = ContainerAppCommando(
                workflow=stap.workflow, stap=stap.naam, actie="secret set", tokens=tuple(tokens)
            )
            sleutel = (stap.workflow, stap.naam)
            per_stap.setdefault(sleutel, set()).update(commando.secret_namen())
    return per_stap


def containerapp_commandos(alleen_actief: bool = True) -> list[ContainerAppCommando]:
    """Elke `az containerapp create|update` uit de CD-workflows, getokeniseerd."""
    commandos: list[ContainerAppCommando] = []
    for stap in cd_stappen():
        if alleen_actief and not stap.actief:
            continue
        # De heredocs eerst, uit het RUWE script: `logische_regels()` strookt comments en
        # knipt op regeleinden, en beide zijn betekenisvol binnen een heredoc.
        bestanden = heredoc_bestanden(stap.script)
        for regel in logische_regels(stap.script):
            tokens = tokeniseer(regel)
            if "containerapp" not in tokens:
                continue
            index = tokens.index("containerapp")
            actie = tokens[index + 1] if index + 1 < len(tokens) else ""
            if actie not in ("create", "update"):
                continue
            voorlopig = ContainerAppCommando(
                workflow=stap.workflow,
                stap=stap.naam,
                actie=actie,
                tokens=tuple(tokens),
            )
            manifest: dict[str, Any] | None = None
            for bestandsnaam in voorlopig.waarden_van("--yaml"):
                if bestandsnaam not in bestanden:
                    raise WorkflowOntleedFout(
                        f"{stap.workflow}:{stap.naam} deployt met `--yaml {bestandsnaam}`, maar "
                        "dat bestand wordt in deze stap nergens met een heredoc geschreven. "
                        "Fail-closed: zonder de definitie weet deze guard niet wat er draait."
                    )
                manifest = ontleed_manifest(bestanden[bestandsnaam])
            commandos.append(
                ContainerAppCommando(
                    workflow=stap.workflow,
                    stap=stap.naam,
                    actie=actie,
                    tokens=tuple(tokens),
                    manifest=manifest,
                )
            )
    return commandos

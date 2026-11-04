"""PII-lekkage in logs -- architecture fitness functions.

Alle vier tests zijn ROOD op het moment van committen (problemen bestaan nu).
Ze worden GROEN zodra SP-DLP-001 de betreffende bestanden fixt.

Geen src-imports, geen pytest fixtures -- alleen stdlib + pathlib + re.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# SEC-001: email verbatim in auth logs
# ---------------------------------------------------------------------------


def test_sec001_email_not_logged_verbatim_in_auth() -> None:
    """SEC-001 (SP-DLP-001): auth.py mag email NIET verbatim in logger aanroepen loggen.

    Een logger.info/warning/error die 'email' als f-string of %-format argument
    bevat, stuurt PII naar de logbundel. Dit schendt GDPR Art. 5(1)(f) en de
    interne DLP-policy.

    Test faalt als het patroon GEVONDEN wordt (probleem aanwezig).
    Test wordt GROEN als email-waarden gemaskeerd worden (bijv. hash of [REDACTED]).

    TODO(SP-DLP-001): vervang email-interpolatie door masked_email() of een
    structureel log-veld dat buiten de plaintext logstream valt.
    """
    target = Path("src/core/frontend/auth.py")
    assert target.exists(), (
        f"Bestand niet gevonden: {target} -- pas het pad aan als het bestand verplaatst is."
    )

    source = target.read_text(encoding="utf-8")

    pattern_fstring = re.compile(r"logger\.(info|warning|error)[^)]*\{email[^}]*\}")
    pattern_percent = re.compile(r"logger\.(info|warning|error)[^)]*email")

    matches_fstring = pattern_fstring.findall(source)
    matches_percent = pattern_percent.findall(source)

    found = matches_fstring or matches_percent

    assert not found, (
        "SEC-001 ROOD: src/core/frontend/auth.py logt email verbatim via logger.\n"
        f"  f-string matches: {matches_fstring}\n"
        f"  %-format matches: {matches_percent}\n"
        "Maskeer de waarde met masked_email() of vervang door [REDACTED] -- SP-DLP-001."
    )


# ---------------------------------------------------------------------------
# SEC-002: user_input verbatim in CVA logs
# ---------------------------------------------------------------------------


def test_sec002_user_input_not_logged_verbatim_in_cva() -> None:
    """SEC-002 (SP-DLP-001): cva agent.py mag user_input NIET verbatim via logger.info loggen.

    Eindgebruikersinvoer kan namen, adressen en andere PII bevatten.
    Directe string-interpolatie in logger.info lekt die data naar de logbundel.

    Test faalt als het patroon GEVONDEN wordt (probleem aanwezig).
    Test wordt GROEN als user_input gemaskeerd of weggelaten wordt uit logs.

    TODO(SP-DLP-001): log alleen geanonimiseerde metadata (bijv. lengte, taal-code),
    niet de inhoud van user_input.
    """
    target = Path("src/core/agents/ultimate_cva/agent.py")
    assert target.exists(), (
        f"Bestand niet gevonden: {target} -- pas het pad aan als het bestand verplaatst is."
    )

    source = target.read_text(encoding="utf-8")

    pattern = re.compile(r"logger\.info[^)]*user_input")

    matches = pattern.findall(source)

    assert not matches, (
        "SEC-002 ROOD: src/core/agents/ultimate_cva/agent.py logt user_input verbatim via logger.info.\n"
        f"  Matches: {matches}\n"
        "Log alleen geanonimiseerde metadata, niet de inhoud -- SP-DLP-001."
    )


# ---------------------------------------------------------------------------
# SEC-006: agent upload endpoint zonder authenticatie
# ---------------------------------------------------------------------------


def test_sec006_upload_agent_yaml_requires_auth() -> None:
    """SEC-006 (SP-DLP-001): upload_agent_yaml MOET Depends(get_current_user) in de signature hebben.

    Een endpoint zonder authenticatie-dependency accepteert anonieme YAML-uploads.
    Dit maakt willekeurige agent-injectie mogelijk zonder enige identiteitscontrole.

    Test faalt als 'get_current_user' NIET gevonden wordt in de 20 regels rond
    de functiedefinitie (probleem aanwezig).
    Test wordt GROEN zodra de dependency aanwezig is.

    TODO(SP-DLP-001): voeg `current_user: UserClaims = Depends(get_current_user)`
    toe aan de signature van upload_agent_yaml.
    """
    target = Path("src/core/api/v1/agentic/agents.py")
    assert target.exists(), (
        f"Bestand niet gevonden: {target} -- pas het pad aan als het bestand verplaatst is."
    )

    source = target.read_text(encoding="utf-8")
    lines = source.splitlines()

    # Zoek de regelnummers van 'upload_agent_yaml'
    func_lines = [i for i, line in enumerate(lines) if "upload_agent_yaml" in line]

    assert func_lines, (
        "SEC-006: functie 'upload_agent_yaml' niet gevonden in src/core/api/v1/agentic/agents.py.\n"
        "Controleer of de functienaam gewijzigd is en pas de test aan."
    )

    # Controleer een venster van 20 regels rond elke vindplaats op get_current_user
    auth_found = False
    for func_line in func_lines:
        start = max(0, func_line)
        end = min(len(lines), func_line + 20)
        window = "\n".join(lines[start:end])
        if "get_current_user" in window:
            auth_found = True
            break

    assert auth_found, (
        "SEC-006 ROOD: upload_agent_yaml in src/core/api/v1/agentic/agents.py mist Depends(get_current_user).\n"
        "Voeg `current_user: UserClaims = Depends(get_current_user)` toe aan de signature -- SP-DLP-001."
    )


# ---------------------------------------------------------------------------
# SEC-007: JWT token fragment in logs
# ---------------------------------------------------------------------------


def test_sec007_jwt_token_not_sliced_into_logs() -> None:
    """SEC-007 (SP-DLP-001): jwt_handler.py mag geen token-slice (token[:N]) via logger loggen.

    Een gedeeltelijk JWT-token in logs is voldoende voor header/payload-decodering
    (Base64url, geen padding vereist). Dit lekt claims en subject-identiteit.

    Test faalt als het patroon GEVONDEN wordt (probleem aanwezig).
    Test wordt GROEN als token-slicing uit logger aanroepen verwijderd is.

    TODO(SP-DLP-001): vervang token[:N] door '[TOKEN REDACTED]' of log alleen
    de jti-claim (niet reconstructeerbaar naar het volledige token).
    """
    target = Path("src/core/auth/jwt_handler.py")
    assert target.exists(), (
        f"Bestand niet gevonden: {target} -- pas het pad aan als het bestand verplaatst is."
    )

    source = target.read_text(encoding="utf-8")

    pattern = re.compile(r"logger\.[a-z]+.*token\[")

    matches = pattern.findall(source)

    assert not matches, (
        "SEC-007 ROOD: src/core/auth/jwt_handler.py logt een token-slice (token[:N]) via logger.\n"
        f"  Matches: {matches}\n"
        "Verwijder de slice en gebruik '[TOKEN REDACTED]' of log alleen de jti-claim -- SP-DLP-001."
    )

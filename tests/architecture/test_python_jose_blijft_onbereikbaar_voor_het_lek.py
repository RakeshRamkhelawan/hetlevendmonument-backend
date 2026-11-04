"""PYSEC-2026-4298 (python-jose) blijft voor ons onbereikbaar zolang we hem niet vervangen (2026-10-23).

Het lek (bron: OSV, gemeten 2026-10-23): python-jose tot en met 3.5.0 (de nieuwste versie op PyPI; er bestaat geen herstelde) valideert
asymmetrische sleutels niet goed bij de HMAC-initialisatie. Een DER-gecodeerde PUBLIEKE sleutel wordt als HMAC-geheim geaccepteerd; wie de
publieke sleutel van een dienst kent kan dan HS256-tokens vervalsen, als de aanroep zijn toegestane algoritmen NIET beperkt. Het is een
onvolledige reparatie van CVE-2024-33663 (algoritmeverwarring).

Waarom het ons (nu) niet raakt, gemeten door elke `jose`-aanroep in `src/` te lezen: elke `jwt.decode` van python-jose geeft een EXPLICIETE
lijst HS-algoritmen mee en verifieert met een geheime sleutel als tekst, nooit met een publieke sleutel. De RS256-tokens (`token_service.py`)
gebruiken PyJWT, niet python-jose, en beperken zich tot `["RS256"]`.

De CI-uitzondering `--ignore-vuln PYSEC-2026-4298` is alleen verdedigbaar zolang dat waar blijft. Deze guard maakt het structureel
afdwingbaar: een module die python-jose importeert mag (1) geen `decode` zonder `algorithms=` aanroepen en (2) geen asymmetrisch algoritme of
publieke sleutel noemen. Komt dat er wel in, dan hoort eerst de risicoacceptatie opnieuw beoordeeld te worden, of python-jose te worden
vervangen (PyJWT staat al in `requirements-base.txt`).

De tests lezen STRUCTUUR (de AST: een aanroep, een trefwoord, een constante), niet de tekst van een commentaar of docstring.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ASYMMETRISCH = re.compile(r"^(RS|ES|PS)\d{3}$")
#: Zoveel `decode`-aanroepen van python-jose bestonden bij de meting (2026-10-23); minder betekent dat de scan iets mist.
MINIMUM_AANROEPEN = 5
#: Wat uit `jose` wordt binnengehaald is gemeten: `jwt` (met expliciete HS-algoritmen) en de uitzonderingsklassen. Alles anders
#: (jws, jwk, jwe, `from jose.jwt import decode`, ...) is NIET gemeten en moet eerst een eigen bereikbaarheidsmeting krijgen.
TOEGESTAAN_UIT_JOSE = {"jwt", "JWTError", "ExpiredSignatureError", "JWTClaimsError"}
ONDERDELEN_ZONDER_METING = {"jws", "jwk", "jwe"}


def _onbekende_jose_imports(knoop: ast.ImportFrom) -> list[str]:
    """Meldingen voor een `from jose...` die iets anders binnenhaalt dan het gemeten gebruik."""
    if knoop.module == "jose":
        return [
            f"regel {knoop.lineno}: from jose import {alias.name} (niet gemeten)"
            for alias in knoop.names
            if alias.name not in TOEGESTAAN_UIT_JOSE
        ]
    if knoop.module == "jose.exceptions":
        return []
    return [
        f"regel {knoop.lineno}: import uit {knoop.module} (alleen `from jose import jwt` is gemeten)"
    ]


def _basis_naam(knoop: ast.Attribute) -> str | None:
    basis: ast.expr = knoop
    while isinstance(basis, ast.Attribute):
        basis = basis.value
    return basis.id if isinstance(basis, ast.Name) else None


def _jose_namen(boom: ast.AST) -> set[str]:
    """De namen waaronder python-jose of een onderdeel ervan in dit bestand is binnengehaald (ook binnen een functie)."""
    namen: set[str] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom) and (knoop.module or "").split(".")[0] == "jose":
            namen.update(alias.asname or alias.name for alias in knoop.names)
        elif isinstance(knoop, ast.Import):
            namen.update(
                (alias.asname or alias.name).split(".")[0]
                for alias in knoop.names
                if alias.name.split(".")[0] == "jose"
            )
    return namen


def _is_decode_van_jose(knoop: ast.AST, namen: set[str]) -> bool:
    if not (
        isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Attribute)
        and knoop.func.attr == "decode"
    ):
        return False
    basis = knoop.func.value
    while isinstance(basis, ast.Attribute):
        basis = basis.value
    return isinstance(basis, ast.Name) and basis.id in namen


def decode_aanroepen(bron: str) -> int:
    """Het aantal `decode`-aanroepen van python-jose in dit bronbestand."""
    boom = ast.parse(bron)
    namen = _jose_namen(boom)
    return sum(_is_decode_van_jose(knoop, namen) for knoop in ast.walk(boom))


def schendingen(bron: str) -> list[str]:
    """De schendingen in een bronbestand dat python-jose gebruikt; een bestand zonder jose geeft er geen."""
    boom = ast.parse(bron)
    namen = _jose_namen(boom)
    if not namen:
        return []
    gevonden: list[str] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom) and (knoop.module or "").split(".")[0] == "jose":
            gevonden.extend(_onbekende_jose_imports(knoop))
        elif isinstance(knoop, ast.Import):
            gevonden.extend(
                f"regel {knoop.lineno}: import {alias.name} (alleen jose.jwt is gemeten)"
                for alias in knoop.names
                if alias.name.startswith("jose.")
            )
        elif (
            isinstance(knoop, ast.Attribute)
            and knoop.attr in ONDERDELEN_ZONDER_METING
            and _basis_naam(knoop) in namen
        ):
            gevonden.append(f"regel {knoop.lineno}: jose.{knoop.attr} (niet gemeten)")
        elif _is_decode_van_jose(knoop, namen):
            assert isinstance(knoop, ast.Call)
            sleutelwoorden = {kw.arg: kw.value for kw in knoop.keywords if kw.arg}
            algoritmen = sleutelwoorden.get("algorithms")
            if algoritmen is None or (
                isinstance(algoritmen, ast.Constant) and algoritmen.value is None
            ):
                gevonden.append(
                    f"regel {knoop.lineno}: decode zonder een expliciete lijst algorithms"
                )
        elif isinstance(knoop, ast.Constant) and isinstance(knoop.value, str):
            if ASYMMETRISCH.match(knoop.value) or "PUBLIC KEY" in knoop.value:
                gevonden.append(
                    f"regel {knoop.lineno}: asymmetrisch algoritme of publieke sleutel ({knoop.value[:20]!r})"
                )
        elif isinstance(knoop, ast.Name) and "public_key" in knoop.id:
            gevonden.append(f"regel {knoop.lineno}: publieke sleutel ({knoop.id})")
        elif isinstance(knoop, ast.Attribute) and "public_key" in knoop.attr:
            gevonden.append(f"regel {knoop.lineno}: publieke sleutel ({knoop.attr})")
    return gevonden


def _bronbestanden_met_jose() -> list[str]:
    namen = subprocess.run(
        ["git", "ls-files", "--", "src"], capture_output=True, text=True, cwd=REPO, check=True
    ).stdout.splitlines()
    return [
        naam
        for naam in namen
        if naam.endswith(".py") and "jose" in (REPO / naam).read_text(encoding="utf-8")
    ]


class TestDeBroncode:
    def test_de_scan_ziet_de_bekende_decode_aanroepen(self) -> None:
        totaal = sum(
            decode_aanroepen((REPO / naam).read_text(encoding="utf-8"))
            for naam in _bronbestanden_met_jose()
        )

        assert totaal >= MINIMUM_AANROEPEN, (
            f"de scan vindt maar {totaal} decode-aanroepen van python-jose"
        )

    def test_geen_module_met_python_jose_schendt_de_voorwaarden(self) -> None:
        gevonden = {
            naam: meldingen
            for naam in _bronbestanden_met_jose()
            if (meldingen := schendingen((REPO / naam).read_text(encoding="utf-8")))
        }

        assert not gevonden, f"python-jose wordt onveilig gebruikt (PYSEC-2026-4298): {gevonden}"


class TestDeMeting:
    """De meetfunctie op losse bronteksten, beide richtingen."""

    def test_een_decode_zonder_algorithms_wordt_gevonden(self) -> None:
        bron = "from jose import jwt\ndef f(t, k):\n    return jwt.decode(t, k)\n"

        assert schendingen(bron)

    def test_een_decode_met_algorithms_none_wordt_gevonden(self) -> None:
        bron = "from jose import jwt\ndef f(t, k):\n    return jwt.decode(t, k, algorithms=None)\n"

        assert schendingen(bron)

    @pytest.mark.parametrize("algoritme", ["RS256", "ES256", "PS384"])
    def test_een_asymmetrisch_algoritme_in_een_jose_module_wordt_gevonden(
        self, algoritme: str
    ) -> None:
        bron = f'from jose import jwt\nALG = "{algoritme}"\n'

        assert schendingen(bron)

    def test_een_publieke_sleutel_in_een_jose_module_wordt_gevonden(self) -> None:
        bron = "from jose import jwt\ndef f(t, public_key):\n    return jwt.decode(t, public_key, algorithms=['HS256'])\n"

        assert schendingen(bron)

    def test_een_decode_via_een_alias_wordt_ook_gevonden(self) -> None:
        bron = "from jose import jwt as jose_jwt\ndef f(t, k):\n    return jose_jwt.decode(t, k)\n"

        assert schendingen(bron)

    def test_een_import_binnen_een_functie_wordt_ook_gevonden(self) -> None:
        bron = "def f(t, k):\n    from jose import jwt\n    return jwt.decode(t, k)\n"

        assert schendingen(bron)

    @pytest.mark.parametrize(
        "bron",
        [
            "from jose import jws\n",
            "from jose import jwk\n",
            "from jose import jwe\n",
            "from jose.jwt import decode\n",
            "from jose.jws import verify\n",
            "import jose.jws\n",
            "import jose\n\n\ndef f(t, k):\n    return jose.jws.verify(t, k, algorithms=['HS256'])\n",
        ],
    )
    def test_een_onderdeel_van_python_jose_waarvoor_niets_is_gemeten_wordt_gevonden(
        self, bron: str
    ) -> None:
        # Security-review Gate 2 (2026-10-23): de guard zag `from jose.jwt import decode` (een kale aanroep) en `jws.verify` niet. Alleen
        # `jose.jwt` via `from jose import jwt` en de uitzonderingsklassen zijn gemeten.
        assert schendingen(bron)

    @pytest.mark.parametrize(
        "bron",
        [
            "from jose import JWTError, jwt\n",
            "from jose import JWTError as _JWTError, jwt\n",
            "from jose.exceptions import ExpiredSignatureError\n",
            "import jose\n",
        ],
    )
    def test_het_gemeten_gebruik_van_python_jose_wordt_niet_gevonden(self, bron: str) -> None:
        assert schendingen(bron) == []

    def test_een_correcte_decode_wordt_niet_gevonden(self) -> None:
        bron = "from jose import jwt\ndef f(t, k):\n    return jwt.decode(t, k, algorithms=['HS256'])\n"

        assert schendingen(bron) == []

    def test_een_decode_met_een_variabele_lijst_wordt_niet_gevonden(self) -> None:
        bron = (
            "from jose import jwt\ndef f(t, k, a):\n    return jwt.decode(t, k, algorithms=[a])\n"
        )

        assert schendingen(bron) == []

    def test_pyjwt_met_rs256_wordt_niet_gevonden(self) -> None:
        # token_service.py gebruikt PyJWT en een publieke sleutel met RS256; dat is het goede gebruik en geen python-jose.
        bron = "import jwt\ndef f(t, public_key):\n    return jwt.decode(t, public_key, algorithms=['RS256'])\n"

        assert schendingen(bron) == []

    def test_een_decode_van_pyjwt_telt_niet_mee_als_python_jose(self) -> None:
        bron = "import jwt\ndef f(t, k):\n    return jwt.decode(t, k, algorithms=['HS256'])\n"

        assert decode_aanroepen(bron) == 0

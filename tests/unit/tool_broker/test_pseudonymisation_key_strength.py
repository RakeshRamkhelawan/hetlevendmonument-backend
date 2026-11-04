"""De pseudonimiseringssleutel is sterk EN wordt op beide plekken gelijk beoordeeld (OP-27).

Twee eisen, en de tweede is de reden dat dit een eigen bestand is.

**De afleiding moet een KDF zijn.** `pseudonymisation_key()` deed een enkele
`hashlib.sha256(configured)`. Voor een sleutel uit `secrets.token_urlsafe(32)` maakt dat weinig
uit, maar de eis was alleen LENGTE -- en een lange, arme sleutel (`"a" * 43`) haalde die eis. Een
enkele hashronde is dan een woordenboekaanval per gok; een KDF maakt elke gok duur.

**Dezelfde eis moet in de RUNTIME en in de BOOT-CHECK staan.** Dit is de valkuil die deze sprint
al eens heeft gemaakt en die in `config/config_validator.py` boven de lengte-eis staat
opgeschreven: een variabele die de boot-check HAALT maar door de runtime wordt GEWEIGERD betekent
een geslaagde deploy waarna elke tool-aanroep faalt. Een entropie-eis die alleen in
`pseudonymisation_key()` staat, bouwt precies die stille storing opnieuw. Daarom toetst dit bestand
beide kanten met DEZELFDE sleutels.

**Waarom nu en niet later.** De sleutel mag na de eerste productie-digest nooit meer wijzigen,
anders is al het eerdere bewijs niet meer na te rekenen. De afleiding versterken is daarmee een
breaking change zodra er iets is gedeployed. Er is nog niets gedeployed, dus dit is het enige
goedkope moment.

**Wat deze check NIET is.** Geen raadbaarheids-orakel. Gemeten: `sanskritisetu-staging-key-2026-08`
heeft 16 verschillende tekens en is geen herhaling, dus hij komt erdoor -- terwijl hij te raden is.
Een dictionary- of patrooncheck zou dat moeten vangen en is bewust buiten scope: brittle, en de
echte verdediging is dat de sleutel met `secrets` wordt gegenereerd (zo staat het in de
deploy-instructie en in `docs/BACKLOG.md` DEPLOY-001). Deze check vangt de MECHANISCH zwakke
sleutel: te weinig verschillende tekens, of een herhaald blokje.
"""

from __future__ import annotations

import hashlib
import secrets

import pytest

#: Vier generatoren die alle vier legitiem zijn. `token_hex` staat er met opzet bij: die heeft een
#: alfabet van 16 tekens, dus zijn aantal VERSCHILLENDE tekens zakt tot 8 bij
#: `token_hex(16)` -- gemeten over 200.000 uitkomsten. Een drempel die alleen naar het aantal
#: verschillende tekens kijkt en boven de 8 ligt, weigert dus een sleutel met 128 bits entropie en
#: laat productie niet meer opstarten. Dat is de reden dat de check twee regels heeft en niet een.
KEY_GENERATORS = {
    "token_urlsafe(32)": lambda: secrets.token_urlsafe(32),
    "token_urlsafe(24)": lambda: secrets.token_urlsafe(24),
    "token_hex(16)": lambda: secrets.token_hex(16),
    "token_hex(32)": lambda: secrets.token_hex(32),
}

#: Sleutels die lang genoeg zijn voor `MIN_KEY_LENGTH` maar mechanisch zwak. Elk hiervan haalde
#: de oude lengte-eis.
MECHANICALLY_WEAK_KEYS = {
    "een teken": "a" * 43,
    "twee tekens afwisselend": "ab" * 22,
    "blokje van acht": "abcdefgh" * 6,
    "een woord herhaald": "changeme" * 6,
    "cijferreeks herhaald": "0123456789" * 5,
    "twee blokken": "a" * 22 + "b" * 22,
    # Afgekapte herhaling. De klassieke `s in (s + s)[1:-1]`-truc ziet alleen EXACTE
    # herhalingen en laat deze door; gemeten tijdens het bouwen van de check.
    "projectnaam, afgekapt herhaald": ("SanskritiSetu" * 4)[:45],
}


@pytest.fixture(autouse=True)
def _forget_the_cached_key() -> object:
    """De sleutel wordt per proces gecacht; zonder dit lekt hij tussen tests."""
    from src.core.tool_broker import redaction

    redaction.reset_key_cache()
    yield
    redaction.reset_key_cache()


def _runtime_refuses(key: str, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Weigert `pseudonymisation_key()` deze sleutel?"""
    from src.core.tool_broker import redaction

    monkeypatch.setattr(redaction, "_configured_key", lambda: key)
    redaction.reset_key_cache()
    try:
        redaction.pseudonymisation_key()
    except RuntimeError:
        return True
    return False


def _boot_check_refuses(key: str, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Meldt `ConfigValidator.validate()` deze sleutel als ERROR?"""
    from src.core.config.config_validator import ConfigValidator
    from src.core.tool_broker.redaction import KEY_ENV_VAR

    monkeypatch.setenv(KEY_ENV_VAR, key)
    result = ConfigValidator().validate()
    return any(issue.key == KEY_ENV_VAR for issue in result.errors)


@pytest.mark.unit
class TestAMechanicallyWeakKeyIsRefused:
    @pytest.mark.parametrize("description", sorted(MECHANICALLY_WEAK_KEYS))
    def test_the_runtime_refuses_it(
        self, description: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lang genoeg is niet sterk genoeg.

        Met bekende klaartekst-paren -- en die zijn er, want opsombare velden als `status` en
        `None` staan leesbaar in hetzelfde log -- is zo'n sleutel offline te kraken tegen een
        hashronde per gok.
        """
        key = MECHANICALLY_WEAK_KEYS[description]

        assert _runtime_refuses(key, monkeypatch), (
            f"De runtime accepteert een mechanisch zwakke sleutel ({description}, "
            f"{len(set(key))} verschillende tekens, lengte {len(key)}). Lengte alleen is geen "
            "sterkte-eis."
        )

    @pytest.mark.parametrize("description", sorted(MECHANICALLY_WEAK_KEYS))
    def test_the_boot_check_refuses_it_too(
        self, description: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dezelfde sleutel, dezelfde uitkomst -- anders is de deploy stil kapot.

        Dit is de valkuil die in `config_validator.py` boven de lengte-eis staat: haalt een
        variabele de boot-check maar weigert de runtime hem, dan slaagt de deploy en faalt daarna
        ELKE tool-aanroep. Een eis die maar op een van de twee plekken staat, bouwt die storing.
        """
        key = MECHANICALLY_WEAK_KEYS[description]

        assert _boot_check_refuses(key, monkeypatch), (
            f"De boot-check laat een sleutel door die de runtime weigert ({description}). Dan "
            "slaagt de deploy en faalt daarna elke tool-aanroep -- exact de stille storing die de "
            "boot-check moest voorkomen."
        )


@pytest.mark.unit
class TestEveryGeneratedKeyIsAccepted:
    """Een te strenge eis laat productie niet opstarten. Dat is erger dan geen eis."""

    @pytest.mark.parametrize("generator", sorted(KEY_GENERATORS))
    def test_the_rule_accepts_hundreds_of_real_keys(self, generator: str) -> None:
        """Geen enkele echte sleutel mag afketsen.

        Rechtstreeks op `key_strength_problem()` en niet via `pseudonymisation_key()`, met opzet.
        De eigenschap die hier bewezen wordt zit in de REGEL, niet in de KDF -- en de KDF er
        1200 keer bij halen kostte 60 seconden aan scrypt-afleidingen van 16 MB zonder dat het
        iets extra's aantoont. Dat beide kanten deze regel DAADWERKELIJK gebruiken, wordt bewezen
        door de zwakke-sleutel-tests hierboven (die toetsen runtime en boot-check apart) en door
        `test_the_runtime_accepts_a_real_key_end_to_end` hieronder.

        300 per generator. Gemeten over 200.000 uitkomsten per generator tijdens het bouwen:
        `token_urlsafe(32)` zakt niet onder 22 verschillende tekens, maar `token_hex(16)` zakt tot
        8. De drempel moet dus onder 8 liggen, en de herhalingsregel doet het echte werk.
        """
        from src.core.tool_broker.redaction import key_strength_problem

        make = KEY_GENERATORS[generator]
        refused = [
            (key, problem)
            for key, problem in ((k, key_strength_problem(k)) for k in (make() for _ in range(300)))
            if problem is not None
        ]

        assert not refused, (
            f"De sterkte-regel weigert {len(refused)} van 300 sleutels uit {generator}, "
            f"bijvoorbeeld {refused[0][0]!r}: {refused[0][1]} Een eis die een echte sleutel "
            "afwijst, laat productie niet opstarten -- en dat is erger dan geen eis."
        )

    @pytest.mark.parametrize("generator", sorted(KEY_GENERATORS))
    def test_the_runtime_accepts_a_real_key_end_to_end(
        self, generator: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En de runtime leidt er daadwerkelijk een sleutel uit af.

        Klein aantal: dit toetst de WIRING (regel plus KDF plus cache), niet de regel. De regel
        is hierboven op 300 sleutels per generator getoetst.
        """
        make = KEY_GENERATORS[generator]
        refused = [key for key in (make() for _ in range(3)) if _runtime_refuses(key, monkeypatch)]

        assert not refused, (
            f"De runtime weigert een correct gegenereerde sleutel uit {generator}: "
            f"{refused[0]!r}. De regel accepteert hem wel, dus de wiring wijkt af van de regel."
        )

    @pytest.mark.parametrize("generator", sorted(KEY_GENERATORS))
    def test_the_boot_check_accepts_hundreds_of_real_keys(
        self, generator: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En de boot-check mag ze evenmin afwijzen -- anders stopt CD op een goede sleutel."""
        make = KEY_GENERATORS[generator]
        refused = [
            key for key in (make() for _ in range(300)) if _boot_check_refuses(key, monkeypatch)
        ]

        assert not refused, (
            f"De boot-check weigert {len(refused)} van 300 sleutels uit {generator}. Dan stopt de "
            "deploy op een correct gegenereerde sleutel."
        )


@pytest.mark.unit
class TestTheDerivationIsAKdf:
    def test_a_single_sha256_round_is_not_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """De afgeleide sleutel is niet simpelweg sha256(configured).

        Een enkele hashronde kost een aanvaller met een woordenlijst niets. Deze test is
        mutatie-resistent: hij vergelijkt met de UITKOMST van de oude constructie, dus hij wordt
        alleen groen als de afleiding daadwerkelijk iets anders doet.
        """
        from src.core.tool_broker import redaction

        configured = secrets.token_urlsafe(32)
        monkeypatch.setattr(redaction, "_configured_key", lambda: configured)
        redaction.reset_key_cache()

        derived = redaction.pseudonymisation_key()

        assert derived != hashlib.sha256(configured.encode("utf-8")).digest(), (
            "De afleiding is nog een enkele SHA-256-ronde. Gebruik een KDF (hashlib.scrypt), "
            "zodat een gok duur is in plaats van gratis."
        )

    def test_the_derivation_is_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dezelfde geconfigureerde sleutel geeft dezelfde afgeleide sleutel.

        Zonder deze eigenschap geeft dezelfde waarde per proces een andere digest, en dan valt de
        koppelbaarheid weg waar art. 12(2) op rust. Een KDF met een willekeurige salt zou dat
        stilletjes doen -- vandaar een VASTE salt.
        """
        from src.core.tool_broker import redaction

        configured = secrets.token_urlsafe(32)
        monkeypatch.setattr(redaction, "_configured_key", lambda: configured)

        redaction.reset_key_cache()
        first = redaction.pseudonymisation_key()
        redaction.reset_key_cache()
        second = redaction.pseudonymisation_key()

        assert first == second, (
            "Dezelfde geconfigureerde sleutel levert twee verschillende afgeleide sleutels. "
            "Gebruikt de KDF een willekeurige salt? Dan is geen enkele eerdere digest meer na te "
            "rekenen."
        )


@pytest.mark.unit
class TestTheHmacDomainMovesWithTheDerivation:
    def test_the_domain_is_v2_now_that_the_derivation_changed(self) -> None:
        """Verandert de afleiding, dan moet het domein mee.

        Digests van voor en na deze wijziging zijn niet vergelijkbaar. Zou het domein `:v1`
        blijven, dan lijken ze uit dezelfde reeks te komen en zou iemand kunnen concluderen dat
        twee verschillende digests twee verschillende WAARDEN zijn, terwijl het dezelfde waarde
        onder een andere afleiding is. Nu gratis: er is nog niets gedeployed.
        """
        from src.core.tool_broker.redaction import _HMAC_DOMAIN

        assert _HMAC_DOMAIN.endswith(b":v2"), (
            f"Het HMAC-domein is {_HMAC_DOMAIN!r}. De afleiding is gewijzigd, dus het domein hoort "
            "mee te bewegen -- anders zijn digests van voor en na de wijziging niet te "
            "onderscheiden terwijl ze onvergelijkbaar zijn."
        )

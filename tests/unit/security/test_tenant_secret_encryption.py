"""De klantsleutel is per tenant gescheiden, en zonder hoofdsleutel gebeurt er niets.

Achtergrond (2026-09-20). Het bestaande `TokenEncryptionService` valt zonder
`MASTER_ENCRYPTION_KEY` terug op een proces-lokale sleutel. Bij het schrijven van deze tests
stond die variabele in nul van `.env.example`, `docker-compose.yml` en `docker-compose.prod.yml`;
de twee compose-bestanden zijn intussen bijgewerkt, de terugval zelf niet. Voor een
OAuth-token is dat vervelend; voor een sleutel die een klant ons geeft is het stil
gegevensverlies -- je merkt het pas als iemand belt.

Deze tests leggen de twee eigenschappen vast die dat moeten voorkomen: gesloten falen, en een
eigen sleutel per tenant.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.fernet import InvalidToken

from src.core.security.tenant_secret_encryption import (
    HoofdsleutelOntbreekt,
    HoofdsleutelTeZwak,
    OnbekendeSleutelversie,
    TenantSecretEncryption,
)

#: Opgebouwd in plaats van opgeschreven, en in de vorm die de code sinds Gate 2 EIST:
#: minstens 32 bytes willekeur in urlsafe-base64. De vorige waarde was een leesbare zin,
#: en die wordt nu terecht geweigerd -- HKDF heeft geen werkfactor, dus een wachtwoordzin
#: maakt elke opgeslagen klantsleutel offline kraakbaar.
HOOFDSLEUTEL = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
ANDERE_HOOFDSLEUTEL = base64.urlsafe_b64encode(bytes(range(32, 64))).decode("ascii")
GEHEIM = "sk-" + "x" * 20


# --------------------------------------------------------------------- gesloten falen


def test_zonder_hoofdsleutel_weigert_hij_dienst(monkeypatch: pytest.MonkeyPatch) -> None:
    """Geen terugvalsleutel. Dat is het hele verschil met het bestaande object."""
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY", raising=False)

    with pytest.raises(HoofdsleutelOntbreekt):
        TenantSecretEncryption()


def test_een_lege_hoofdsleutel_telt_als_geen_hoofdsleutel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Een variabele die wel bestaat maar leeg is, is de valkuil van elke configuratiecontrole."""
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "   ")

    with pytest.raises(HoofdsleutelOntbreekt):
        TenantSecretEncryption()


def test_de_melding_zegt_WAT_er_moet_gebeuren(monkeypatch: pytest.MonkeyPatch) -> None:
    """Een fout zonder uitweg kost de inrichter een uur zoeken.

    **De `delenv` is op 2026-09-22 toegevoegd en niet uit netheid.** Deze test gaf
    `master_key=""` mee en leunde er stilzwijgend op dat `MASTER_ENCRYPTION_KEY` NIET in de
    omgeving stond -- een lege waarde is falsy, dus de constructor valt terug op `os.getenv`.
    Die aanname hield precies zolang niemand de sleutel had ingericht. Op de dag dat hij in
    `.env` kwam te staan, werd de test rood: `src/core/env_loader.py` laadt dat bestand wel
    degelijk in `os.environ` zodra hij geimporteerd is, dus in de testrun stond er een echte
    sleutel van 43 tekens (gemeten). De test toetste toen niets meer van wat hij belooft.
    """
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY", raising=False)

    with pytest.raises(HoofdsleutelOntbreekt) as fout:
        TenantSecretEncryption(master_key="")

    assert "MASTER_ENCRYPTION_KEY" in str(fout.value)


# --------------------------------------------------------------------- scheiding per tenant


def test_heen_en_terug_levert_hetzelfde_geheim() -> None:
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    assert enc.decrypt(1, enc.encrypt(1, GEHEIM)) == GEHEIM


def test_een_andere_tenant_kan_het_geheim_NIET_lezen() -> None:
    """De kern: een lek van de sleutel van tenant A opent tenant B niet."""
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    versleuteld = enc.encrypt(1, GEHEIM)

    with pytest.raises(InvalidToken):
        enc.decrypt(2, versleuteld)


def test_dezelfde_tekst_levert_per_tenant_een_ANDERE_versleuteling() -> None:
    """Zonder scheiding per tenant zouden deze twee dezelfde sleutel gebruiken.

    Fernet zet een tijdstempel en een willekeurige IV in elke tekst, dus twee versleutelingen
    verschillen sowieso. Daarom toetst deze test niet dat de TEKSTEN verschillen -- dat zou
    altijd slagen, ook zonder scheiding -- maar dat ze elkaars sleutel niet accepteren.
    """
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    with pytest.raises(InvalidToken):
        enc.decrypt(7, enc.encrypt(42, GEHEIM))
    with pytest.raises(InvalidToken):
        enc.decrypt(42, enc.encrypt(7, GEHEIM))


def test_een_andere_hoofdsleutel_opent_niets() -> None:
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    andere = TenantSecretEncryption(master_key=ANDERE_HOOFDSLEUTEL)

    with pytest.raises(InvalidToken):
        andere.decrypt(1, enc.encrypt(1, GEHEIM))


def test_beschadigde_tekst_wordt_geweigerd() -> None:
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    versleuteld = enc.encrypt(1, GEHEIM)

    with pytest.raises(InvalidToken):
        enc.decrypt(1, versleuteld[:-4] + "AAAA")


# --------------------------------------------------------------------- de tenant zelf


@pytest.mark.parametrize("tenant_id", [0, -1, True, "1", None, 1.0])
def test_een_onbruikbare_tenant_wordt_geweigerd(tenant_id: object) -> None:
    """`True` staat er expliciet bij: als bool zou hij als tenant 1 doorgaan.

    Dat is geen theorie -- `isinstance(True, int)` is waar in Python, dus zonder de expliciete
    controle zouden twee verschillende aanroepen stilzwijgend dezelfde sleutel delen.
    """
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    with pytest.raises(ValueError, match="tenant_id"):
        enc.encrypt(tenant_id, GEHEIM)  # type: ignore[arg-type]  # het weigeren IS wat getoetst wordt


def test_de_versleutelde_tekst_bevat_het_geheim_niet() -> None:
    """Klinkt vanzelfsprekend; is de goedkoopste controle op een verkeerd aangesloten laag."""
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    assert GEHEIM not in enc.encrypt(1, GEHEIM)


# ------------------------------------------------------- de sterkte van de hoofdsleutel


@pytest.mark.parametrize(
    "zwak",
    [
        "x",
        "geheim",
        "een-hoofdsleutel-voor-de-test",  # precies de waarde die dit bestand eerst gebruikte
        base64.urlsafe_b64encode(bytes(range(31))).decode("ascii"),  # 31 bytes: net te kort
        # De vier gevallen hieronder kwamen ALLEMAAL door de eerste versie van de controle
        # heen, gemeten door een Gate 2-reviewer. Ze staan hier zodat dezelfde claim niet
        # opnieuw kan dichtrotten.
        "correct horse battery staple is my master key for sanskritisetu!!",
        "dit-is-mijn-wachtwoordzin-voor-de-sanskritisetu-hoofdsleutel",
        "a" * 43,  # geldige base64, 32 bytes, DRIE verschillende waarden
        "wachtwoord" * 5,
    ],
)
def test_een_hoofdsleutel_zonder_genoeg_willekeur_wordt_geweigerd(zwak: str) -> None:
    """HKDF is een AFLEIDING, geen VERSTERKING -- er zit geen werkfactor in.

    Een Gate 2-reviewer mat dat `TenantSecretEncryption(master_key="x")` gewoon versleutelde.
    Met een wachtwoordzin als hoofdsleutel is elke opgeslagen klantsleutel offline te kraken
    met een woordenboekaanval, en HKDF vertraagt dat met niets.
    """
    with pytest.raises(HoofdsleutelTeZwak):
        TenantSecretEncryption(master_key=zwak)


def test_een_te_zwakke_sleutel_telt_als_GEEN_bruikbare_sleutel() -> None:
    """De router vangt `HoofdsleutelOntbreekt` af en hoort dit geval mee te pakken.

    Zonder deze overerving zou een te zwakke sleutel een kale 500 geven waar een ontbrekende
    sleutel een nette 503 met uitleg geeft -- terwijl het voor de beheerder dezelfde situatie is.
    """
    with pytest.raises(HoofdsleutelOntbreekt):
        TenantSecretEncryption(master_key="x")


def test_een_hexadecimale_hoofdsleutel_mag_ook() -> None:
    """De andere richting: zonder deze test is 'weiger alles' een geldige oplossing.

    `secrets.token_hex(32)` is net zo goed als `token_urlsafe(32)`, en een uitrol die hem zo
    heeft gezet hoort niet te stranden.
    """
    # Echte hex van 32 VERSCHILLENDE bytes. Bewust niet `"ab" * 32`: dat is 32 keer dezelfde
    # byte en wordt sinds de variatie-eis terecht geweigerd -- dat stond hier eerst, en het
    # was een testsleutel die in productie niets waard zou zijn.
    enc = TenantSecretEncryption(master_key=bytes(range(32)).hex())

    assert enc.decrypt(1, enc.encrypt(1, GEHEIM)) == GEHEIM


# ------------------------------------------------------- de versie-aanduiding


def test_de_versleutelde_tekst_draagt_een_versie() -> None:
    """Zonder versie is een rotatie van de hoofdsleutel stil gegevensverlies."""
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    assert enc.encrypt(1, GEHEIM).startswith("v1:")


def test_tekst_zonder_bekende_versie_geeft_een_EIGEN_fout() -> None:
    """ "Beschadigd" en "van voor de rotatie" vragen om verschillende antwoorden.

    Geven ze dezelfde fout, dan valt er geen migratiescript te schrijven dat weet welke rijen
    het moet aanpakken -- en dat is precies wat een rotatie nodig heeft.
    """
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    zonder_versie = enc.encrypt(1, GEHEIM).split(":", 1)[1]

    with pytest.raises(OnbekendeSleutelversie):
        enc.decrypt(1, zonder_versie)

    with pytest.raises(OnbekendeSleutelversie):
        enc.decrypt(1, "v99:" + zonder_versie)


def test_een_onbekende_versie_is_GEEN_InvalidToken() -> None:
    """De keten slaat een onleesbare rij over; hij mag die twee niet door elkaar halen."""
    enc = TenantSecretEncryption(master_key=HOOFDSLEUTEL)

    with pytest.raises(OnbekendeSleutelversie) as fout:
        enc.decrypt(1, "v99:onzin")

    assert not isinstance(fout.value, InvalidToken)

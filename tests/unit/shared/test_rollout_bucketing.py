"""De gedeelde bucketformule (ADR-036 OP-02).

`stable_bucket()` is niet nieuw bedacht: het is de formule die als
`company.feature_flags._stable_bucket()` al in productie de company-laag uitrolde. Die is
hierheen verplaatst zodat de skill-manifest-uitrol dezelfde verdeling gebruikt in plaats
van een tweede kopie te worden.

Bij die verplaatsing hoort een bewijs dat er NIETS verschoven is, want de company-laag
draait al bij tenants: een tenant die vandaag binnen de uitrol valt, moet dat morgen nog
steeds doen. `_stable_bucket()` had tot deze wijziging GEEN ENKELE test -- gemeten met
`git grep -rn "_stable_bucket" -- tests/` op de basiscommit: nul treffers.
"""

from __future__ import annotations

import hashlib

from src.core.company.feature_flags import _stable_bucket
from src.core.shared.rollout import BUCKETS, is_in_rollout, stable_bucket


# De formule zoals hij VOOR deze wijziging in company/feature_flags.py stond, letterlijk
# overgeschreven uit de basiscommit. Dit is het ijkpunt; het is geen tweede implementatie
# van iets nieuws maar een vastgelegde kopie van de oude waarheid.
def _formule_van_voor_de_verplaatsing(tenant_id: int) -> int:
    digest = hashlib.md5(str(tenant_id).encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % 100


def test_de_lege_salt_geeft_exact_de_oude_verdeling() -> None:
    """Geen enkele bestaande tenant mag door de verplaatsing van bucket wisselen."""
    verschoven = [
        tenant_id
        for tenant_id in range(1, 5001)
        if stable_bucket(tenant_id) != _formule_van_voor_de_verplaatsing(tenant_id)
    ]
    assert not verschoven, (
        f"{len(verschoven)} tenants kregen een ander bucket dan voor de verplaatsing "
        f"(eerste tien: {verschoven[:10]}). De company-laag draait al bij klanten; een "
        "verschuiving zou tenants ongemerkt in of uit een lopende uitrol duwen."
    )


def test_de_company_laag_gebruikt_de_gedeelde_formule() -> None:
    """`_stable_bucket` moet delegeren, niet zijn eigen kopie houden.

    Zonder deze test kan iemand de gedeelde functie aanpassen terwijl de company-laag stil
    op zijn eigen versie blijft draaien -- precies de twee-implementaties-situatie die deze
    wijziging opheft.
    """
    afwijkend = [t for t in range(1, 1001) if _stable_bucket(t) != stable_bucket(t)]
    assert not afwijkend, (
        f"company._stable_bucket wijkt af van shared.stable_bucket voor {afwijkend[:10]}; "
        "er zijn weer twee verdelingen in omloop."
    )


def test_het_bucket_ligt_altijd_binnen_het_bereik() -> None:
    """Een bucket buiten [0, BUCKETS) zou percentages betekenisloos maken."""
    for tenant_id in range(1, 1001):
        bucket = stable_bucket(tenant_id, salt="willekeurige-vlag")
        assert 0 <= bucket < BUCKETS, f"tenant {tenant_id} kreeg bucket {bucket}"


def test_verschillende_salts_kiezen_verschillende_tenants() -> None:
    """De reden dat de salt bestaat: niet altijd dezelfde proefkonijnen.

    Zonder salt zit dezelfde tenant in ELKE uitrol van het platform. Met de agent-id als
    salt rolt elke skill zijn eigen groep uit.
    """
    een = {t for t in range(1, 501) if is_in_rollout(t, percentage=10, salt="skill-manifest:a")}
    twee = {t for t in range(1, 501) if is_in_rollout(t, percentage=10, salt="skill-manifest:b")}

    assert een and twee, "beide uitrollen horen tenants te bevatten bij 10 procent"
    assert een != twee, (
        "Twee verschillende skills kozen exact dezelfde tenants. Dan doet de salt niets en "
        "krijgt een ongelukkige tenant elke canary van het platform tegelijk."
    )


def test_de_toewijzing_is_herhaalbaar() -> None:
    """Twee aanroepen, dezelfde uitkomst -- anders is een canary onbruikbaar."""
    for tenant_id in range(1, 201):
        assert stable_bucket(tenant_id, salt="x") == stable_bucket(tenant_id, salt="x")


def test_de_grenzen_nul_en_honderd_raadplegen_de_verdeling_niet() -> None:
    """0 procent is voor iedereen uit, 100 procent voor iedereen aan."""
    assert not any(is_in_rollout(t, percentage=0, salt="x") for t in range(1, 501))
    assert all(is_in_rollout(t, percentage=100, salt="x") for t in range(1, 501))


def test_uitsluiting_wint_van_opname() -> None:
    """De terugvalknop voor een enkele tenant moet altijd winnen.

    Staat een tenant in beide lijsten, dan is dat een vergissing, en de veilige uitkomst is
    de stabiele versie -- niet de nieuwe.
    """
    assert not is_in_rollout(7, percentage=100, included=[7], excluded=[7])
    assert not is_in_rollout(7, percentage=100, excluded=[7])
    assert is_in_rollout(7, percentage=0, included=[7])


def test_het_percentage_wordt_ongeveer_gehaald() -> None:
    """Een uitrol van 5 procent hoort ook echt ongeveer 5 procent te raken.

    Ruime marge: de verdeling is deterministisch, niet statistisch, dus dit bewaakt alleen
    dat er geen systematische scheefheid in de formule zit (bijvoorbeeld door een fout in de
    modulo of door alleen even tenants te raken).
    """
    aantal = sum(1 for t in range(1, 10001) if is_in_rollout(t, percentage=5, salt="skill:x"))
    fractie = aantal / 10000
    assert 0.03 <= fractie <= 0.07, (
        f"5 procent uitrol raakte {fractie:.1%} van 10.000 tenants. Dat wijst op scheefheid "
        "in de bucketverdeling."
    )

"""Deterministische percentage-uitrol: een subject op een vast bucket afbeelden.

ADR-036 OP-02. Dit is GEEN nieuw mechanisme maar de bestaande huisregel, hierheen gehaald
zodat er een implementatie is in plaats van twee.

**Herkomst.** De formule stond als `_stable_bucket()` in
`src/core/company/feature_flags.py` en werd daar sinds de company-laag gebruikt voor
precies dit doel: een tenant stabiel in of buiten een gefaseerde uitrol plaatsen. Die
module roept nu deze functie aan; met de standaard (lege) salt is de uitkomst
BYTE-IDENTIEK aan de oude formule, zodat geen enkele tenant van bucket wisselt. Dat is
vastgelegd in `tests/unit/shared/test_rollout_bucketing.py` en het is de reden dat de salt
optioneel is en niet verplicht.

**Waarom hier en niet in `company/`.** `src.core.als` (agent_runtime) mag niet naar
`src.core.company` (domain_pack) importeren -- dat is een koppeling de verkeerde kant op,
en de Ce-teller voor agent_runtime staat met 225 van de 227 vrijwel vol
(`tests/architecture/test_dsm_008_reclassification.py`). `src.core.shared` is in
`scripts/dsm_full_analysis.py` als `shared` geclassificeerd en telt daarom niet mee. Deze
module importeert zelf niets uit `src`, zodat `test_shared_fan_out_is_zero` blijft gelden.

**Waarom de salt.** Zonder salt hangt het bucket alleen van het subject af, en dan zit
DEZELFDE tenant in elke uitrol van het hele platform -- altijd dezelfde proefkonijnen, en
een tenant die bij een eerdere canary problemen gaf, zit bij de volgende weer vooraan. De
gangbare oplossing is de sleutel van de vlag mee te hashen; Unleash doet dat als
`murmur3(groupId + ":" + id)` en flagd concateneert `flagKey` met de `targetingKey`. Hier
is dat `md5(salt + ":" + subject_id)`, met MD5 omdat dat de bestaande huisconventie is
(`usedforsecurity=False`; dit is een verdelingsfunctie, geen beveiligingsmaatregel).

**Waarom 100 buckets en niet 10.000.** De actuele praktijk gaat richting fijnere
resolutie -- Statsig gebruikt 10.000, LaunchDarkly 100.000 -- omdat 100 buckets de
kleinste uitrol op 1 procent vastzet. Hier is bewust de bestaande 100 aangehouden: het
platform heeft niet de tenantaantallen waarbij een uitrol onder 1 procent nog iets meet
(bij enkele honderden tenants levert 0,5 procent nul of een tenant op), en hergebruik van
de ongewijzigde formule is meer waard dan een theoretische fijnmazigheid. Wordt dat ooit
te grof, dan is `BUCKETS` de enige plek die verandert -- maar let op: dat verplaatst ELKE
tenant naar een ander bucket en is dus zelf een uitrol.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

# Aantal emmers waarover subjecten worden verdeeld. Een percentage wordt hiertegen
# afgezet, dus 100 betekent: de kleinste zinvolle stap is 1 procent.
BUCKETS = 100


def stable_bucket(subject_id: int, *, salt: str = "") -> int:
    """Beeld `subject_id` af op een vast bucket in [0, BUCKETS).

    Deterministisch en procesonafhankelijk: bewust `hashlib.md5` en niet de ingebouwde
    `hash()`, want die is voor strings per proces gerandomiseerd (PYTHONHASHSEED) en zou
    een tenant bij elke herstart in een andere groep laten belanden.

    Met de standaard lege salt is dit exact de oude `company.feature_flags._stable_bucket`:
    `md5(str(subject_id))`, eerste 8 hex-tekens, modulo 100.
    """
    sleutel = f"{salt}:{subject_id}" if salt else str(subject_id)
    digest = hashlib.md5(sleutel.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % BUCKETS


def is_in_rollout(
    subject_id: int,
    *,
    percentage: int,
    salt: str = "",
    included: Iterable[int] = (),
    excluded: Iterable[int] = (),
) -> bool:
    """Valt dit subject binnen de uitrol?

    Volgorde van beslissen, en die volgorde is onderdeel van het contract:

      1. `excluded` wint altijd. Dit is de terugvalknop voor EEN tenant: meldt een klant een
         probleem, dan gaat hij hiermee terug naar de stabiele versie zonder dat de uitrol
         voor iedereen stopt. Een uitsluiting die door een whitelist overruled kan worden,
         is geen uitsluiting.
      2. `included` daarna. Bewust opgenomen tenants (de eigen tenant, een klant die mee wil
         testen) krijgen de nieuwe versie ongeacht hun bucket.
      3. `percentage <= 0` is uit, `>= 100` is aan -- beide zonder de hash aan te roepen,
         zodat een uitrol op 0 of 100 procent niet van de verdeling kan afhangen.
      4. Anders beslist het bucket.

    Dit is dezelfde volgorde als `company.feature_flags.is_company_layer_enabled` hanteert
    (kill switch, whitelist, grenzen, bucket); de globale kill switch zit daar op
    configuratieniveau en hoort daarom bij de aanroeper, niet in deze pure functie.
    """
    if subject_id in set(excluded):
        return False
    if subject_id in set(included):
        return True
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    return stable_bucket(subject_id, salt=salt) < percentage

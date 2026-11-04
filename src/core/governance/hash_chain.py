"""
HashChainVerifier Service

Verifies the integrity of the audit log hash chain (SHA-256 hash chain as per ADR-019).
Each audit log entry contains:
- hash: SHA-256 hash of current entry data
- previous_hash: Hash of the previous entry in the chain
- timestamp: Entry timestamp

Sprint 7, Task 3.1
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import json

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.audit_chain_key import ALGORITHM_NAME, chain_mac
from src.core.governance.models import AuditLog, OfficerVerdict

#: HET GEDATEERDE WATERMERK OP ONGEHASHTE GATEN (ADR-036 OP-108, voorstel onder OP-118).
#:
#: Op 2026-08-10 zijn beide levende rauwe schrijvers (`retention_cleanup.py`,
#: `contest_service.py`) omgezet naar `AuditService.log_event`, dus sindsdien krijgt elke
#: nieuwe auditregel een `audit_hash`. Voor de rijen die de dagelijkse opruimactor DAARVOOR
#: heeft geschreven bestaat geen backfill: omhashen zou de bewijswaarde van de keten
#: vernietigen. Zonder watermerk houdt daardoor elke tenant die de opruimactor ooit heeft
#: geraakt permanent `is_valid=False` -- en een oordeel dat altijd False is, is geen oordeel.
#:
#: **Dit is bewust GEEN generieke ontsnapping.** Het watermerk verzacht het oordeel
#: uitsluitend voor rijen met een tijdstempel VOOR deze datum. Een gat op een rij van NA
#: deze datum blijft `is_valid` op False zetten, want sinds de fix vult elke schrijver de
#: keten en is een nieuwe ongehashte rij per definitie verdacht (OP-118: hash-strippen).
#: De datum is een module-constante -- geen parameter van `verify_chain()` en geen
#: omgevingsvariabele -- zodat geen enkele aanroeper hem kan opschuiven.
#:
#: Middernacht is de conservatieve kant van de fixdatum: rijen die op 2026-08-10 zelf nog
#: voor de deploy zijn geschreven tellen als NIEUW en alarmeren dus, in plaats van stil
#: onder het watermerk te verdwijnen.
#:
#: **Bekende restrisico (niet gedekt, zie rapport):** voor een ONGEHASHTE rij is `timestamp`
#: door niets beschermd -- die rij wordt immers overgeslagen. Wie een hash leegmaakt kan de
#: tijdstempel meebackdaten en zo onder het watermerk duiken. Dat restrisico wordt gedekt
#: door de TELLING in `audit_chain_anchors.unhashed_count` (OP-118), die op een TOENAME
#: alarmeert en geen datum gebruikt.
UNHASHED_GAP_WATERMARK = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _is_van_voor_het_watermerk(entry: AuditLog) -> bool:
    """Staat deze (ongehashte) rij aantoonbaar VOOR de OP-108-fixdatum?

    Fail-secure op het ONTBREKEN van een tijdstempel: dan is de rij niet aantoonbaar oud en
    telt hij als NIEUW. Andersom zou de tijdstempel leegmaken de ontsnappingsroute onder het
    watermerk zijn.

    Een NAIEVE tijdstempel wordt wel geplaatst, als UTC -- dat is de conventie van deze
    kolom (`DateTime(timezone=True)`, overal met `datetime.now(timezone.utc)` gevuld). Hem
    als "nieuw" behandelen zou elke bestaande legacy-rij in een omgeving die naief
    terugleest onterecht laten alarmeren.
    """
    tijdstempel = entry.__dict__.get("timestamp")
    if not isinstance(tijdstempel, datetime):
        return False
    if tijdstempel.tzinfo is None:
        tijdstempel = tijdstempel.replace(tzinfo=timezone.utc)
    return tijdstempel < UNHASHED_GAP_WATERMARK


def _hash_volgens_markering(entry: AuditLog, preimage: str) -> str:
    """Kale SHA-256 of gesleutelde HMAC, afhankelijk van `hash_algorithm` (ADR-036 OP-120).

    **De markering zit ZELF in de preimage.** Zonder dat is de HMAC gratis te omzeilen: een
    aanvaller zet `hash_algorithm` op `NULL`, valt daarmee in de sleutelloze tak, en herberekent
    de rij zonder de sleutel te kennen.

    **Waarom de legacy-tak blijft bestaan.** Bestaande rijen zijn met SHA-256 gehasht en er is
    geen backfill mogelijk -- omhashen zou de bewijswaarde vernietigen. Zonder deze tak zou elke
    bestaande tenant `tampering_detected=True` melden op vier endpoints tegelijk, permanent. Dat
    de legacy-tak sleutelloos is, is precies waarom er daarnaast een knippunt bestaat: zie
    `verify_chain(chain_epoch_id=...)`.
    """
    markering = entry.__dict__.get("hash_algorithm")

    if markering == ALGORITHM_NAME:
        return chain_mac(f"{ALGORITHM_NAME}:{preimage}")

    return hashlib.sha256(preimage.encode()).hexdigest()


@dataclass
class ChainVerificationResult:
    """Result of verifying the entire hash chain for a tenant."""

    is_valid: bool
    total_entries: int
    verified_entries: int
    broken_at_entry_id: int | None  # First broken entry
    broken_at_index: int | None  # Index in chain
    expected_hash: str | None  # What hash should be
    actual_hash: str | None  # What hash was found
    verification_time_ms: float
    tenant_id: int
    checked_at: datetime
    # ADR-036 OP-108. Een GAT is iets anders dan MANIPULATIE, en dat onderscheid moet uit het
    # antwoord te lezen zijn. `is_valid` blijft False in beide gevallen: na de traversal-fix is
    # een rij met `audit_hash IS NULL` niet te onderscheiden van een rij waarvan een aanvaller de
    # hash heeft LEEGGEMAAKT na een inhoudswijziging. Gaten uit het oordeel halen zou
    # hash-strippen tot een stille manipulatieroute maken.
    #
    # Defaults, want vier bestaande testconstructies geven deze velden niet mee.
    tampering_detected: bool = False
    unhashed_entries: int = 0
    # HET GEDATEERDE WATERMERK (ADR-036 OP-108/OP-118). `unhashed_entries` blijft het TOTAAL,
    # zodat bestaande aanroepers en het anker (OP-118) ongewijzigd blijven werken. De splitsing
    # eronder is wat het oordeel bepaalt: alleen gaten NA de fixdatum maken de keten ongeldig.
    unhashed_before_watermark: int = 0
    unhashed_after_watermark: int = 0


@dataclass
class EntryVerificationResult:
    """Result of verifying a single audit log entry."""

    entry_id: int
    is_valid: bool
    hash_matches: bool
    previous_hash_matches: bool
    computed_hash: str
    stored_hash: str
    tenant_id: int


@dataclass
class ChainStatus:
    """Overall chain health status for a tenant."""

    status: str  # 'healthy', 'broken', 'unverified'
    last_verified_at: datetime | None
    total_entries: int
    broken_entries_count: int
    health_percentage: float  # 0-100
    tenant_id: int
    # ADR-036 OP-108: een GAT is geen BREUK. Zonder dit onderscheid telde deze status twee
    # gebroken regels per ongehashte rij. Default, want bestaande constructies geven hem niet mee.
    unhashed_entries: int = 0


class HashChainVerifier:
    """
    Verifies SHA-256 hash chain integrity for audit logs.

    ADR-019 compliant audit logging with hash chain verification.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize with database session."""
        self.db_session = db_session

    def _verify_bound_evidence(
        self, entry: AuditLog, *, tenant_bestaat: bool | None = None
    ) -> bool | None:
        """Klopt de bewijs-digest in `resource` nog met wat er in de rij staat?

        Twee onafhankelijke bindingen delen deze ene verificatieplek: HITL-beslissingen (H-2)
        en de opruimactor (ADR-036 OP-121). Elke `evidence_matches` geeft `None` terug voor een
        `resource` die niet zijn EIGEN vorm heeft, dus de tweede check draait alleen als de
        eerste "niets na te rekenen" meldt -- nooit "manipulatie" voor een rij van de andere
        soort of voor een gewone auditregel zonder binding.

        Ook `None` voor rijen van voor de betreffende fix: die hebben geen `|ev=`-deel en zijn
        niet gedekt. Dat eerlijk melden is beter dan doen alsof.
        """
        from src.core.governance.hitl_evidence import evidence_matches as hitl_evidence_matches
        from src.core.governance.retention_evidence import (
            evidence_matches as retention_evidence_matches,
        )

        metadata = entry.__dict__.get("event_metadata") or {}
        if not isinstance(metadata, dict):
            return None

        resource = entry.__dict__.get("resource")

        # Een regel die bij het opheffen van een tenant is geanonimiseerd (AVG C,
        # `avg_auditlog.py`) heeft geen `user_id` meer; de HITL-digest is dan niet meer na te
        # rekenen. Dat is geen manipulatie -- ALLEEN als de tenantrij zelf niet meer bestaat
        # (`tenant_bestaat is False`), plus een lege user_id en de markering. Op een bestaande
        # tenant zou "user_id leeg + markering" anders een vrijbrief zijn om achteraf te wijzigen
        # WIE iets goedkeurde zonder dat de verificatie het meldt (precies wat H-2 voorkomt).
        geanonimiseerd = (
            tenant_bestaat is False
            and entry.__dict__.get("user_id") is None
            and metadata.get("geanonimiseerd") is True
        )
        hitl_result = (
            None
            if geanonimiseerd
            else hitl_evidence_matches(
                resource,
                tool_name=metadata.get("tool_name"),
                user_id=entry.__dict__.get("user_id"),
                binding=metadata.get("approval_binding"),
            )
        )
        if hitl_result is not None:
            return hitl_result

        return retention_evidence_matches(
            resource,
            records_deleted=metadata.get("records_deleted"),
            cutoff_date=metadata.get("cutoff_date"),
            regulatory_basis=metadata.get("regulatory_basis"),
        )

    def _compute_hash(self, entry: AuditLog, previous_hash: str | None) -> str:
        """
        Compute SHA-256 hash for an audit log entry.

        The hash is computed from entry data excluding the stored hash field.
        Backward compatible: indien `ai_context is None` wordt het hash-resultaat
        exact gelijk aan voor deze release voor entries zonder AI metadata.
        """
        # Determine if this entry has AI Act context fields
        # Use __dict__.get to avoid MagicMock auto-creation of unset attributes
        has_ai_context = any(
            entry.__dict__.get(field) is not None
            for field in [
                "ai_proposal_id",
                "ai_model_id",
                "ai_model_version",
                "ai_reasoning_hash",
                "ai_data_classification",
                "ai_explanation_summary",
                "officer_verdicts_hash",
            ]
        )

        if not has_ai_context:
            # Build content string from entry fields (Legacy Format)
            content_parts = [
                str(entry.tenant_id) if entry.tenant_id else "",
                entry.action or "",
                entry.resource or "",
                entry.timestamp.isoformat() if entry.timestamp else "",
                previous_hash or "",
            ]
            content = ":".join(content_parts)
            return _hash_volgens_markering(entry, content)

        # Build canonical JSON format including AI Context
        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": entry.tenant_id if entry.tenant_id else "",
            "action": entry.action or "",
            "resource": entry.resource or "",
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
            "previous_hash": previous_hash or "",
            "ai_context": {
                "proposal_id": str(entry.__dict__.get("ai_proposal_id", ""))
                if entry.__dict__.get("ai_proposal_id") is not None
                else "",
                "model_id": entry.__dict__.get("ai_model_id", "") or "",
                "model_version": entry.__dict__.get("ai_model_version", "") or "",
                "reasoning_hash": entry.__dict__.get("ai_reasoning_hash", "") or "",
                "data_classification": entry.__dict__.get("ai_data_classification", "") or "",
                "officer_verdicts_hash": entry.__dict__.get("officer_verdicts_hash", "") or "",
            },
        }

        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return _hash_volgens_markering(entry, canonical)

    async def verify_chain(
        self,
        tenant_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        chain_epoch_id: int | None = None,
    ) -> ChainVerificationResult:
        """
        Verify hash chain integrity for a tenant's audit logs.

        Args:
            tenant_id: The tenant ID to verify
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            ChainVerificationResult with verification details
        """
        start_time = time.time()

        # Build query for audit logs ordered by timestamp
        query = (
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            # `id` als tiebreak, want de zes SCHRIJVERS ketenen met
            # `ORDER BY timestamp DESC, id DESC`. Sorteerde de verifier alleen op tijdstempel,
            # dan liep hij bij twee rijen met dezelfde tijdstempel in een andere volgorde dan
            # waarin geketend is -- en dan meldt hij manipulatie die er niet is (ADR-036 OP-110).
            .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
        )

        if start_date:
            query = query.where(AuditLog.timestamp >= start_date)
        if end_date:
            query = query.where(AuditLog.timestamp <= end_date)

        result = await self.db_session.execute(query)
        entries = result.scalars().all()

        total_entries = len(entries)
        verified_entries = 0
        broken_at_entry_id: int | None = None
        broken_at_index: int | None = None
        expected_hash: str | None = None
        actual_hash: str | None = None

        previous_hash: str | None = None
        unhashed_entries = 0
        unhashed_before_watermark = 0
        unhashed_after_watermark = 0
        tampering_detected = False

        # DE BASISLIJN ZAAIEN BIJ EEN DATUMVENSTER (ADR-036 OP-108, blinde ronde 2026-08-10).
        #
        # Met `start_date` begint het venster midden in de keten. De eerste rij daarin heeft een
        # echte `previous_hash` naar een rij ERBUITEN. Startte de traversal met een lege
        # basislijn, dan week de hercompute af en heette dat MANIPULATIE -- op een volkomen gave
        # keten. Dat gaf voorheen al een breuk, maar sinds `tampering_detected` naar buiten komt
        # als "the P0 signal" is het een vals P0-alarm op precies de vraag die een auditor stelt.
        #
        # Dezelfde lookup als de zes schrijvers, beperkt tot voor het venster.
        if start_date:
            voorloper = await self.db_session.execute(
                select(AuditLog.audit_hash)
                .where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.audit_hash.isnot(None),
                    AuditLog.timestamp < start_date,
                )
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(1)
            )
            previous_hash = voorloper.scalar_one_or_none()

        for index, entry in enumerate(entries):
            stored_hash = entry.audit_hash if hasattr(entry, "audit_hash") else None
            entry_previous_hash = entry.previous_hash if hasattr(entry, "previous_hash") else None

            # EEN GAT IS GEEN MANIPULATIE (ADR-036 OP-108).
            #
            # Rijen zonder hash komen van schrijvers die de ketenkolommen niet vulden. De zes
            # schrijvers die dat WEL doen, ketenen aan de laatste rij MET een hash:
            #     .where(audit_hash.isnot(None)).order_by(timestamp.desc(), id.desc())
            # De verificatie moet dus exact dezelfde regel volgen: overslaan, en de basislijn
            # NIET verzetten. Deed hij dat niet, dan brak hij in twee vormen:
            #   - gat in het midden: de gat-rij heeft ook `previous_hash = NULL`, dus de
            #     link-controle viel om OP DIE RIJ en meldde hem als manipulatie;
            #   - gat vooraan: `previous_hash = stored_hash or computed_hash` zette een
            #     VERZONNEN basislijn, waarna de volgende, onschuldige rij omviel.
            # En `break` zorgde dat alles daarna nooit meer werd bekeken -- inclusief het
            # art.-14-bewijs uit H-2.
            if not stored_hash:
                unhashed_entries += 1
                # HET GEDATEERDE WATERMERK (ADR-036 OP-108, voorstel onder OP-118). Een gat op
                # een rij van VOOR de fixdatum is een bekend, geregistreerd OP-108-gat waarvoor
                # geen backfill mogelijk is. Een gat op een rij van NA die datum hoort niet te
                # bestaan -- alle schrijvers vullen de keten -- en is dus verdacht.
                if _is_van_voor_het_watermerk(entry):
                    unhashed_before_watermark += 1
                else:
                    unhashed_after_watermark += 1
                continue

            # HET KNIPPUNT (ADR-036 OP-120). Na de omschakeling naar een gesleutelde hash hoort
            # er geen ongesleutelde rij meer bij te komen. Zonder deze controle blijft
            # terugvallen op het oude algoritme een geldige manier om de sleutel te omzeilen: de
            # aanvaller schrijft een legacy-rij met een kloppende SHA-256 en alles verifieert.
            #
            # Alleen actief als de aanroeper een knippunt MEEGEEFT. De drie admin-endpoints doen
            # dat niet -- die kennen de ankertabel niet -- en gedragen zich dus als voorheen. De
            # strengere controle draait in de verificatiejob, die het knippunt uit het anker
            # haalt. Zou dit altijd aanstaan, dan meldt elk endpoint elke bestaande tenant als
            # gemanipuleerd, en dat is precies de valse-P0 die OP-108 heeft opgeruimd.
            if (
                chain_epoch_id is not None
                and entry.id is not None
                and entry.id >= chain_epoch_id
                and entry.__dict__.get("hash_algorithm") != ALGORITHM_NAME
            ):
                tampering_detected = True
                if broken_at_entry_id is None:
                    broken_at_entry_id = entry.id
                    broken_at_index = index
                    expected_hash = ALGORITHM_NAME
                    actual_hash = entry.__dict__.get("hash_algorithm")
                previous_hash = stored_hash
                continue

            computed_hash = self._compute_hash(entry, previous_hash)

            # De link-controle staat voorop: een verbroken schakel wijst op knoeien met de
            # VOLGORDE, en dat is ernstiger dan een gewijzigd veld. Overgeslagen zolang er nog
            # geen gehashte voorganger is gezien -- dan valt er niets te vergelijken.
            afwijking: tuple[str | None, str | None] | None = None
            if previous_hash is not None and entry_previous_hash != previous_hash:
                afwijking = (previous_hash, entry_previous_hash)
            elif stored_hash != computed_hash:
                afwijking = (computed_hash, stored_hash)

            if afwijking is not None:
                tampering_detected = True
                # NIET stoppen, maar wel de EERSTE afwijking blijven aanwijzen: dat is wat
                # `broken_at_entry_id` belooft en waar forensiek mee begint.
                if broken_at_entry_id is None:
                    broken_at_entry_id = entry.id
                    broken_at_index = index
                    expected_hash, actual_hash = afwijking
            else:
                verified_entries += 1

            # Doorketenen op wat er STAAT, niet op wat we hadden verwacht -- anders sleept een
            # enkele gemanipuleerde rij elke volgende rij mee als vals positief.
            previous_hash = stored_hash

        verification_time_ms = (time.time() - start_time) * 1000

        # Gaten tellen mee in het oordeel, maar zijn APART te lezen (ADR-036 OP-108).
        #
        # Sinds het gedateerde watermerk telt alleen een gat NA de fixdatum mee. De bekende
        # OP-108-gaten van voor die datum zijn niet te backfillen; ze permanent in het oordeel
        # laten meewegen maakte `is_valid` voor elke geraakte tenant blijvend False, en juist
        # daarin verdwijnt hash-strippen uit het zicht (OP-118). `unhashed_entries` blijft het
        # volledige aantal, zodat een auditor de gaten nog steeds ziet staan.
        is_valid = not tampering_detected and unhashed_after_watermark == 0

        return ChainVerificationResult(
            is_valid=is_valid,
            total_entries=total_entries,
            verified_entries=verified_entries,
            broken_at_entry_id=broken_at_entry_id,
            broken_at_index=broken_at_index,
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            verification_time_ms=verification_time_ms,
            tenant_id=tenant_id,
            checked_at=datetime.now(timezone.utc),
            tampering_detected=tampering_detected,
            unhashed_entries=unhashed_entries,
            unhashed_before_watermark=unhashed_before_watermark,
            unhashed_after_watermark=unhashed_after_watermark,
        )

    async def verify_entry(self, entry_id: int, tenant_id: int) -> EntryVerificationResult:
        """
        Verify a single audit log entry.

        Args:
            entry_id: The entry ID to verify
            tenant_id: The tenant ID for isolation

        Returns:
            EntryVerificationResult with verification details
        """
        # Fetch the entry with tenant isolation
        query = (
            select(AuditLog).where(AuditLog.id == entry_id).where(AuditLog.tenant_id == tenant_id)
        )
        result = await self.db_session.execute(query)
        entry = result.scalar_one_or_none()

        if entry is None:
            # Entry not found - return invalid result
            return EntryVerificationResult(
                entry_id=entry_id,
                is_valid=False,
                hash_matches=False,
                previous_hash_matches=False,
                computed_hash="",
                stored_hash="",
                tenant_id=tenant_id,
            )

        # Get previous entry's hash if not first entry
        previous_hash: str | None = None
        if hasattr(entry, "previous_hash") and entry.previous_hash:
            # Find the previous entry by timestamp
            # EXACT dezelfde lookup als de zes SCHRIJVERS doen (ADR-036 OP-108/OP-110).
            #
            # Zonder `audit_hash IS NOT NULL` wordt een ongehashte voorganger de basislijn, en
            # dan faalt de ONSCHULDIGE rij hier op zowel de hercompute als de link. Juist dit
            # endpoint vraagt een auditor per regel op voor het art.-14-bewijs uit H-2.
            #
            # `id` als tiebreak omdat de schrijvers dat ook doen: bij twee rijen met dezelfde
            # tijdstempel koos de verifier anders een andere voorganger dan degene waaraan
            # daadwerkelijk is geketend.
            prev_query = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .where(AuditLog.timestamp < entry.timestamp)
                .where(AuditLog.audit_hash.isnot(None))
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(1)
            )
            prev_result = await self.db_session.execute(prev_query)
            prev_entry = prev_result.scalar_one_or_none()
            if prev_entry:
                previous_hash = prev_entry.audit_hash if hasattr(prev_entry, "audit_hash") else None

        # Compute expected hash
        computed_hash = self._compute_hash(entry, previous_hash)

        # Get stored hash
        stored_hash = entry.audit_hash if hasattr(entry, "audit_hash") else ""
        stored_hash = stored_hash or ""

        # EEN GAT IS GEEN MANIPULATIE -- OOK HIER (ADR-036 OP-108, blinde ronde 2026-08-10).
        #
        # Zonder deze tak gaf een rij zonder hash `stored_hash = ""`, dus `hash_matches = False`
        # en `is_valid = False`: ononderscheidbaar van manipulatie. En dit is juist het endpoint
        # waarop een auditor per regel het art.-14-bewijs opvraagt. `verify_chain` en
        # `get_chain_status` maakten dat onderscheid al wel; deze was vergeten, terwijl de
        # commitboodschap "alle vier gelijkgetrokken" claimde.
        #
        # `is_valid=False` blijft: een ongehashte rij is niet na te rekenen, en niet te
        # onderscheiden van een rij waarvan de hash is leeggemaakt. Maar `hash_matches` op False
        # zetten zou beweren dat de hash NIET klopt, en dat is een andere -- onware -- uitspraak.
        if not stored_hash:
            return EntryVerificationResult(
                entry_id=entry_id,
                is_valid=False,
                hash_matches=False,
                previous_hash_matches=True,
                computed_hash=computed_hash,
                stored_hash="",
                tenant_id=tenant_id,
            )

        # Check hash match
        hash_matches = stored_hash == computed_hash

        # Check previous hash link
        entry_previous_hash = entry.previous_hash if hasattr(entry, "previous_hash") else None
        previous_hash_matches = True
        if previous_hash is not None and entry_previous_hash is not None:
            previous_hash_matches = entry_previous_hash == previous_hash
        elif previous_hash is None and entry_previous_hash is not None:
            # First entry should not have previous_hash
            previous_hash_matches = False

        # HET GEBONDEN BEWIJS NAREKENEN (ADR-036 H-2).
        #
        # `_compute_hash` dekt `event_metadata` en `user_id` niet. Op het HITL-pad zit daar
        # precies het art.-14-bewijs: WIE keurde goed, en WELKE aanroep. Daarom draagt
        # `resource` een digest over die drie velden, en `resource` WORDT gehasht.
        #
        # Zonder deze stap zou die digest wel geschreven maar nooit gecontroleerd worden: wie
        # `event_metadata` achteraf bijwerkt laat `resource` ongemoeid, de ketenhash klopt nog,
        # en de verificatie meldt niets. Dan is het bewijs gebonden en nooit getoetst -- dezelfde
        # klasse als de holle guards die deze sprintdag repareert.
        # Alleen opzoeken als de regel de markering draagt: gewone regels kosten geen extra query.
        tenant_bestaat: bool | None = None
        metadata_rij = entry.__dict__.get("event_metadata")
        if (
            entry.__dict__.get("user_id") is None
            and isinstance(metadata_rij, dict)
            and metadata_rij.get("geanonimiseerd") is True
        ):
            tenant_bestaat = (
                await self.db_session.execute(
                    text("SELECT 1 FROM tenants WHERE id = :tid"), {"tid": tenant_id}
                )
            ).first() is not None
        evidence_matches = self._verify_bound_evidence(entry, tenant_bestaat=tenant_bestaat)
        is_valid = hash_matches and previous_hash_matches and evidence_matches is not False

        return EntryVerificationResult(
            entry_id=entry_id,
            is_valid=is_valid,
            hash_matches=hash_matches,
            previous_hash_matches=previous_hash_matches,
            computed_hash=computed_hash,
            stored_hash=stored_hash,
            tenant_id=tenant_id,
        )

    async def get_chain_status(self, tenant_id: int) -> ChainStatus:
        """
        Get overall chain health status for a tenant.

        Args:
            tenant_id: The tenant ID to check

        Returns:
            ChainStatus with health metrics
        """
        # Get total entries count
        count_query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        result = await self.db_session.execute(count_query)
        entries = result.scalars().all()
        total_entries = len(entries)

        if total_entries == 0:
            # No entries - consider unverified but healthy
            return ChainStatus(
                status="healthy",
                last_verified_at=None,
                total_entries=0,
                broken_entries_count=0,
                health_percentage=100.0,
                tenant_id=tenant_id,
            )

        # Count broken entries by verifying each one
        broken_count = 0
        unhashed_count = 0
        previous_hash: str | None = None

        for entry in sorted(
            entries,
            key=lambda e: (
                e.timestamp or datetime.min.replace(tzinfo=timezone.utc),
                e.id or 0,
            ),
        ):
            stored_hash = entry.audit_hash if hasattr(entry, "audit_hash") else None

            # Zelfde regel als `verify_chain` en als de schrijvers (ADR-036 OP-108): een rij
            # zonder hash is een GAT, geen breuk. Deze lus telde er vroeger TWEE per gat -- de
            # gat-rij zelf viel om op de link-controle, en daarna zette
            # `previous_hash = stored_hash or computed_hash` een verzonnen basislijn waardoor
            # ook de volgende, onschuldige rij omviel. Gemeten op een keten van vier met een
            # gat: broken_entries_count=2, health_percentage=50.0, status="broken" -- zonder
            # dat er iets was gemanipuleerd.
            if not stored_hash:
                unhashed_count += 1
                continue

            computed_hash = self._compute_hash(entry, previous_hash)

            if stored_hash != computed_hash:
                broken_count += 1
            elif previous_hash is not None:
                entry_previous_hash = (
                    entry.previous_hash if hasattr(entry, "previous_hash") else None
                )
                if entry_previous_hash != previous_hash:
                    broken_count += 1

            previous_hash = stored_hash

        health_percentage = (
            ((total_entries - broken_count - unhashed_count) / total_entries) * 100
            if total_entries > 0
            else 100.0
        )

        # Determine status. Een gat is niet "healthy" -- anders zou dit endpoint het
        # tegenovergestelde zeggen van `/integrity/verify`, dat bij een gat `is_valid=False`
        # geeft. Maar het is ook niet "broken", want er is niets gemanipuleerd. "unverified"
        # bestond al en betekent precies dat: niet na te rekenen.
        if broken_count == 0:
            status = "healthy" if unhashed_count == 0 else "unverified"
        elif broken_count < total_entries * 0.1:  # Less than 10% broken
            status = "unverified"
        else:
            status = "broken"

        return ChainStatus(
            status=status,
            last_verified_at=datetime.now(timezone.utc),
            total_entries=total_entries,
            broken_entries_count=broken_count,
            health_percentage=health_percentage,
            unhashed_entries=unhashed_count,
            tenant_id=tenant_id,
        )


def compute_chain_hash(
    *,
    decision_id: str,
    timestamp: str,  # ISO-8601 UTC
    tenant_id: int,
    user_id: int,
    action_type: str,
    action_params_canonical: str,
    previous_hash: str | None,
    ai_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> str:
    """Compute SHA-256 hash for chain entry.

    Backward compatible: indien `ai_context is None` wordt het hash-resultaat
    exact gelijk aan voor deze release voor entries zonder AI metadata.
    Indien `ai_context` is opgegeven, wordt de canonical JSON uitgebreid met
    AI Act velden -- dit produceert een nieuw, gespecificeerd hash-resultaat
    dat in nieuwe rows wordt opgeslagen.
    """
    data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "decision_id": decision_id,
        "timestamp": timestamp,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "action_type": action_type,
        "action_params_canonical_sha256": hashlib.sha256(
            action_params_canonical.encode("utf-8")
        ).hexdigest(),
        "previous_hash": previous_hash or "",
    }

    if ai_context is not None:
        # Strict whitelist van AI Act-velden -- geen overige keys
        data["ai_context"] = {
            "proposal_id": ai_context.get("proposal_id", ""),
            "model_id": ai_context.get("model_id", ""),
            "model_version": ai_context.get("model_version", ""),
            "reasoning_hash": ai_context.get("reasoning_hash", ""),
            "data_classification": ai_context.get("data_classification", ""),
            "officer_verdicts_hash": ai_context.get("officer_verdicts_hash", ""),
        }

    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_officer_verdicts_hash(verdicts: list[OfficerVerdict]) -> str:
    """Merkle-style aggregate over officer verdicts.

    Sorteer op officer_name voor determinisme. Hash van alle individuele
    verdict-hashes in volgorde.
    """
    individual = []
    for v in sorted(verdicts, key=lambda x: x.officer_name):
        canonical = json.dumps(
            {
                "officer_name": v.officer_name,
                "officer_version": v.officer_version,
                "verdict": v.verdict.value,
                "confidence": round(v.confidence, 6),
                "reason_code": v.reason_code,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        individual.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    return hashlib.sha256("|".join(individual).encode("utf-8")).hexdigest()

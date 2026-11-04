# -*- coding: utf-8 -*-
"""Bouwt scripts/seed/levend_monument_lesmateriaal.json; draai vanuit de repo-root (ASCII, \\u-escapes).

Alle feiten in de blokken 'Wat echt gebeurde' en 'Achtergrond' zijn gecontroleerd in
de bronnen die erbij staan (feitencheck 2026-11-02).
"""

import json
import re

SITE = "https://hetlevendmonument.nl"

B = {
    "canon_slavernij": {
        "titel": "Venster Slavernij",
        "uitgever": "Canon van Nederland",
        "url": "https://www.canonvannederland.nl/nl/slavernij",
    },
    "canon_voc": {
        "titel": "Venster VOC en WIC",
        "uitgever": "Canon van Nederland",
        "url": "https://www.canonvannederland.nl/nl/vocenwic",
    },
    "canon_carib": {
        "titel": "Venster Het Caribisch gebied",
        "uitgever": "Canon van Nederland",
        "url": "https://www.canonvannederland.nl/nl/caribischgebied",
    },
    "asc": {
        "titel": "Dutch involvement in the transatlantic slave trade and abolition",
        "uitgever": "Afrika-Studiecentrum Leiden",
        "url": "https://ascleiden.nl/content/webdossiers/dutch-involvement-transatlantic-slave-trade-and-abolition",
    },
    "cbs1863": {
        "titel": "Op 1 juli 1863 47 duizend slaven vrijgemaakt in Suriname en op de Antillen",
        "uitgever": "CBS",
        "url": "https://www.cbs.nl/nl-nl/achtergrond/2013/27/op-1-juli-1863-47-duizend-slaven-vrijgemaakt-in-suriname-en-op-de-antillen",
    },
    "eur_keti": {
        "titel": "Keti Koti is een herdenking en een viering in een",
        "uitgever": "Erasmus Universiteit Rotterdam",
        "url": "https://www.eur.nl/nieuws/keti-koti-een-herdenking-en-een-viering-een",
    },
    "rijk_excuses": {
        "titel": "Excuses regering voor slavernijverleden Nederland",
        "uitgever": "Rijksoverheid",
        "url": "https://www.rijksoverheid.nl/actueel/nieuws/2022/12/19/excuses-regering-voor-slavernijverleden-nederland",
    },
    "koning": {
        "titel": "Toespraak Koning Willem-Alexander, Nationale Herdenking Slavernijverleden 2023",
        "uitgever": "Koninklijk Huis",
        "url": "https://www.koninklijkhuis.nl/documenten/toespraken/2023/07/01/toespraak-van-koning-willem-alexander-tijdens-de-nationale-herdenking-slavernijverleden-2023",
    },
    "rijk_tula": {
        "titel": "Nederland rehabiliteert Curacaose verzetsheld Tula",
        "uitgever": "Rijksoverheid",
        "url": "https://www.rijksoverheid.nl/actueel/nieuws/2023/10/05/nederland-rehabiliteert-curacaose-verzetsheld-tula",
    },
    "npo_tula": {
        "titel": "Wie is verzetsheld Tula?",
        "uitgever": "NPO Kennis",
        "url": "https://npokennis.nl/story/554/wie-is-verzetsheld-tula",
    },
    "nos_lalla": {
        "titel": "150 jaar Hindostaanse migratie naar Suriname",
        "uitgever": "NOS",
        "url": "https://nos.nl/l/2477831",
    },
    "dijkgraaf": {
        "titel": "Toespraak minister Dijkgraaf bij het Hindostaans Immigratiemonument",
        "uitgever": "Rijksoverheid",
        "url": "https://www.rijksoverheid.nl/documenten/2023/06/06/toespraak-minister-dijkgraaf-bij-het-hindostaans-immigratiemonument-in-den-haag",
    },
    "hr_hind": {
        "titel": "Hindostaanse immigratie",
        "uitgever": "Hogeschool Rotterdam",
        "url": "https://www.hogeschoolrotterdam.nl/go/included/kennisartikelen/artikelen/hindostaanse-immigratie",
    },
    "nos_java": {
        "titel": "Javaanse migratie naar Suriname",
        "uitgever": "NOS",
        "url": "https://nos.nl/l/2578044",
    },
    "cbs1975": {
        "titel": "Sinds onafhankelijkheid ruim 250 duizend Surinamers naar Nederland gekomen",
        "uitgever": "CBS",
        "url": "https://www.cbs.nl/nl-nl/nieuws/2025/47/sinds-onafhankelijkheid-ruim-250-duizend-surinamers-naar-nederland-gekomen",
    },
    "cbs_tijdlijn": {
        "titel": "Tijdlijn migratie 1960-1979",
        "uitgever": "CBS",
        "url": "https://www.cbs.nl/nl-nl/longread/diversen/2025/tijdlijn-migratie-1849-2025/4-1960-1979",
    },
    "rembrandthuis": {
        "titel": "HIER. Zwart in Rembrandts tijd (persbericht)",
        "uitgever": "Museum Het Rembrandthuis",
        "url": "https://www.rembrandthuis.nl/wp-content/uploads/2020/02/persbericht-hier.-zwart-in-rembrandts-tijd.-museum-het-rembrandthuis-amsterdam-2.pdf",
    },
    "vanpolanen": {
        "titel": "Snak, Claas and Bastiaan's Struggle for Freedom",
        "uitgever": "BMGN - Low Countries Historical Review (2021)",
        "url": "https://bmgn-lchr.nl/article/view/6984",
    },
    "maassluis": {
        "titel": "Een moriaan als logo",
        "uitgever": "Historische Vereniging Maassluis",
        "url": "https://histvermaassluis.nl/bezienswaardigheden/een-moriaan-als-logo/",
    },
    "schiedam_pichot": {
        "titel": "Pichot. Een Schiedamse regentenfamilie en haar betrokkenheid bij de Surinaamse plantageslavernij",
        "uitgever": "Gemeentearchief Schiedam (2025)",
        "url": "https://archief.schiedam.nl/sites/archief.schiedam.nl/files/inline-files/2025.slavernijverleden.sep_.2.pdf",
    },
    "words_matter": {
        "titel": "Woorden doen ertoe",
        "uitgever": "Nationaal Museum van Wereldculturen",
        "url": "https://www.materialculture.nl/sites/default/files/2018-08/woorden_doen_ertoe.pdf",
    },
    "slo": {
        "titel": "Conceptkerndoelen Mens en maatschappij (november 2024)",
        "uitgever": "SLO",
        "url": "https://slo.nl/publish/pages/22308/conceptkerndoelen-mens-maatschappij.pdf",
    },
    "schooltv": {
        "titel": "Waarom wordt Keti Koti groot gevierd in 2023?",
        "uitgever": "Schooltv",
        "url": "https://schooltv.nl/video-item/waarom-wordt-keti-koti-groot-gevierd-in-2023-150-jaar-geleden-eindigde-de-slavernij",
    },
    "prodemos": {
        "titel": "Lespakket Slavernijverleden, tijdlijnkaartjes",
        "uitgever": "ProDemos",
        "url": "https://prodemos.nl/app/uploads/sites/5/2023/06/ProDemos-Slavernijverleden_Tijdlijnkaartjes_Versie2_1.pdf",
    },
    "atlas_elmina": {
        "titel": "Battle between Dutch and Africans near El Mina in 1637",
        "uitgever": "Atlas of Mutual Heritage",
        "url": "https://www.atlasofmutualheritage.nl/en/id/9328",
    },
    "nos_rotterdam": {
        "titel": "Gemeente Rotterdam biedt excuses aan voor slavernijverleden",
        "uitgever": "NOS",
        "url": "https://nos.nl/artikel/2408945-gemeente-rotterdam-biedt-excuses-aan-voor-slavernijverleden",
    },
    "radboud": {
        "titel": "Surinaamse sterfteregisters onthullen lot Hindostaanse contractarbeiders na slavernij",
        "uitgever": "Radboud Universiteit",
        "url": "https://www.ru.nl/over-ons/nieuws/surinaamse-sterfteregisters-onthullen-lot-hindostaanse-contractarbeiders-na-slavernij",
    },
    "kvk_stichting": {
        "titel": "Uittreksel handelsregister Stichting Ketikotivlaardingen.NL (KvK 95265104), activiteiten",
        "uitgever": "Kamer van Koophandel",
        "url": "",
    },
    "gemeenteblad_vld": {
        "titel": "Gemeenteblad Vlaardingen 2025, 239839 (Keti Koti op het Ketikotiplein)",
        "uitgever": "Officiele Bekendmakingen",
        "url": "https://zoek.officielebekendmakingen.nl/gmb-2025-239839.pdf",
    },
}


def bronnen(*keys):
    return [B[k] for k in keys]


def bronnenlijst(*keys):
    return "\n".join(
        f"- {B[k]['titel']} ({B[k]['uitgever']})" + (f": {B[k]['url']}" if B[k]["url"] else "")
        for k in keys
    )


# Verhalen op de site: id en titel (gecontroleerd op de live API, 2026-11-02).
V = {
    "schiedam": (3, "Schiedam, 1602: het gezicht op het uithangbord"),
    "curacao": (4, "Cura\u00e7ao, 17 augustus 1795: Maria legt haar schoffel neer"),
    "paramaribo": (1, "Paramaribo, 1 juli 1863: de dag van de gebroken keten"),
    "commewijne": (2, "Commewijne, 1873: Kofi loopt weg, Sita komt aan"),
    "vlaardingen": (5, "Vlaardingen, november 1975: een brief naar Commewijne"),
}


def verhaal_link(k):
    i, t = V[k]
    return f"\u201c{t}\u201d. Je vindt het hier: {SITE}/item/{i}"


FICTIE_PO = (
    "Let op: het verhaal is verzonnen. De personen hebben niet echt bestaan. "
    "Wat er om hen heen gebeurt, is wel echt gebeurd. Dat lees je hieronder."
)
FICTIE_VO = (
    "Het verhaal is fictie: de personen zijn verzonnen, de historische achtergrond niet. "
    "Hieronder staan de gecontroleerde feiten, met bron. Gebruik die om het verhaal te toetsen."
)

items = []


#: Kopjes van een werkblad waaronder vragen staan die een leerling kan beantwoorden
#: (BE-EP-055). Genummerde regels worden losse vragen; een alinea is een vraag.
VRAAG_SECTIES = {
    "Vragen bij het verhaal": "vraag",
    "Onderzoeksvragen": "onderzoek",
    "Denk mee": "denk-mee",
    "Opdracht": "opdracht",
    "Perspectief": "perspectief",
    "Doorwerking": "doorwerking",
}


def vragen_uit(body):
    """De vragen van een werkblad als [{sleutel, sectie, tekst}], in volgorde."""
    vragen = []
    sectie = None
    alinea = []

    def sluit_alinea():
        if sectie and alinea and VRAAG_SECTIES[sectie] not in ("vraag", "onderzoek"):
            vragen.append(
                {
                    "sleutel": VRAAG_SECTIES[sectie],
                    "sectie": sectie,
                    "tekst": " ".join(alinea).strip(),
                }
            )
        alinea.clear()

    for regel in body.strip().split("\n"):
        if regel.startswith("## "):
            sluit_alinea()
            kop = regel[3:].strip()
            sectie = kop if kop in VRAAG_SECTIES else None
            continue
        if sectie is None:
            continue
        if not regel.strip():
            sluit_alinea()
            continue
        nummer = re.match(r"^(\d+)\. (.*)$", regel)
        if nummer and VRAAG_SECTIES[sectie] in ("vraag", "onderzoek"):
            vragen.append(
                {
                    "sleutel": f"{VRAAG_SECTIES[sectie]}-{nummer.group(1)}",
                    "sectie": sectie,
                    "tekst": nummer.group(2).strip(),
                }
            )
            continue
        alinea.append(regel.strip())
    sluit_alinea()
    sleutels = [v["sleutel"] for v in vragen]
    assert len(sleutels) == len(set(sleutels)), f"dubbele vraagsleutels: {sleutels}"
    return vragen


def item(
    slug,
    typ,
    niveau,
    titel,
    titel_en,
    beschrijving,
    beschrijving_en,
    body,
    bron_keys,
    les=None,
    verhaal=None,
):
    zichtbaar = "public" if typ == "teacher_guide" else "edu"
    meta = {
        "fictief": False,
        "soort": "lesmateriaal",
        "niveau": niveau,
        "bronnen": bronnen(*bron_keys),
        "feitencheck": "2026-11-02",
    }
    if les is not None:
        meta["lesnummer"] = les
    if verhaal is not None:
        meta["verhaal_id"] = V[verhaal][0]
    if typ == "educational_workbook":
        meta["vragen"] = vragen_uit(body)
        assert meta["vragen"], f"werkblad {slug} heeft geen vragen"
    items.append(
        {
            "slug": slug,
            "type": typ,
            "title_nl": titel,
            "title_en": titel_en,
            "description_nl": beschrijving,
            "description_en": beschrijving_en,
            "body_nl": body.strip(),
            "creator_name": "Het Levend Monument (redactie)",
            "is_anonymous": False,
            "language": "nl",
            "category": "educatie",
            "license": "CC-BY-4.0",
            "rights_confirmed": True,
            "privacy": "public",
            "visibility": zichtbaar,
            "status": "approved",
            "target_age_group": niveau,
            "metadata": meta,
        }
    )


# =====================================================================
# GROEP 7-8
# =====================================================================

item(
    "docent-po",
    "teacher_guide",
    "groep-7-8",
    "Docentenhandleiding groep 7-8: Vijf verhalen over vrijheid",
    "Teacher guide grades 5-6 (Dutch groep 7-8): Five stories about freedom",
    "Een lesreeks van vijf lessen over het slavernijverleden, met vijf korte verhalen en werkbladen. Voor groep 7 en 8.",
    "A series of five lessons on the history of slavery, with five short stories and worksheets.",
    f"""
## Waar gaat deze lesreeks over?
In vijf lessen ontdekken leerlingen het slavernijverleden van Nederland. Elke les begint met een kort verhaal van Het Levend Monument. Daarna werken de leerlingen met een werkblad.

De verhalen lopen van 1602 tot 1975. Ze spelen in Schiedam, op Cura\u00e7ao, in Paramaribo, in Commewijne en in Vlaardingen. Zo zien leerlingen dat dit verleden ook over hun eigen omgeving gaat, en dat het doorwerkt tot vandaag.

## Voor wie en hoe lang?
- Groep 7 en 8.
- Vijf lessen van ongeveer 45 minuten.
- U kunt ook een of twee lessen kiezen. Les 3 (Keti Koti, 1863) past goed rond 1 juli.

## Verhaal en feit
De vijf verhalen zijn verzonnen. De personen hebben niet echt bestaan. De gebeurtenissen op de achtergrond zijn wel echt gebeurd. Op elk werkblad staat een blok \u201cWat echt gebeurde\u201d met gecontroleerde feiten.

Bespreek dit verschil met de klas. Een goede vraag is: \u201cWat in dit verhaal is verzonnen, en wat is echt?\u201d

## Hoe komen leerlingen bij de werkbladen?
De verhalen staan openbaar op {SITE}. De werkbladen zijn alleen te zien met een klascode van 8 tekens. Leerlingen vullen die in op {SITE}/educatie. Een klascode vraagt u aan via {SITE}/docenten.

## Woorden die we gebruiken
In deze lessen zeggen we \u201ctot slaaf gemaakte\u201d en niet \u201cslaaf\u201d. Niemand is van nature slaaf. Mensen werden tot slaaf gemaakt, door anderen, met geweld. Musea zoals het Rijksmuseum gebruiken deze woorden ook.

Andere woorden:
- plantage-eigenaar: iemand die een plantage bezat, en ook de tot slaaf gemaakte mensen die daar moesten werken. Zij werden behandeld als bezit;
- slavenhandel: het kopen, vervoeren en verkopen van mensen;
- vrijheid, verzet, herdenken.

## Veilig in de klas
Dit onderwerp kan dichtbij komen. Sommige leerlingen hebben voorouders die tot slaaf zijn gemaakt. Andere leerlingen horen er voor het eerst over.
- Vraag geen leerling om namens een groep te spreken.
- Laat leerlingen zelf kiezen of ze iets over hun familie vertellen.
- Speel slavernij niet na in een rollenspel. Werk met verhalen, vragen en gesprek.
- Geef ruimte voor gevoelens. Boosheid en verdriet horen erbij.
- In les 2 lezen leerlingen dat Tula werd gemarteld en gedood. Kondig dat vooraf aan en neem tijd voor reacties.
- Oudere bronnen, zoals het CBS-artikel uit 2013, gebruiken nog het woord \u201cslaven\u201d. Leg uit dat dit het oudere woord is.

## De vijf lessen
1. Schiedam, 1602: wie zie je, en wie zie je niet? (zwarte mensen in de Republiek, de VOC)
2. Cura\u00e7ao, 1795: verzet (de opstand van Tula)
3. Paramaribo, 1863: Keti Koti (het einde van de slavernij)
4. Commewijne, 1873: na het staatstoezicht (contractarbeiders uit India)
5. Vlaardingen, 1975: een nieuw begin (Suriname wordt onafhankelijk)

Elke les heeft dezelfde opbouw:
1. Voorlezen of samen lezen van het verhaal (10 minuten).
2. Het blok \u201cWat echt gebeurde\u201d bespreken (10 minuten).
3. Vragen en opdracht in tweetallen (20 minuten).
4. Kort nagesprek (5 minuten).

## Aansluiting bij het onderwijs
- Canon van Nederland: de vensters \u201cSlavernij\u201d, \u201cVOC en WIC\u201d en \u201cHet Caribisch gebied\u201d.
- De conceptkerndoelen Mens en maatschappij van SLO (november 2024) noemen voor het primair onderwijs: \u201cbenoemen hoe slavernijverleden, koloniale verhoudingen, Tweede Wereldoorlog, Holocaust en migratie doorwerken in het heden\u201d. Let op: dit zijn conceptkerndoelen.

## Achtergrond voor de docent
- De WIC werd opgericht in 1621. Daarmee begon de Nederlandse slavenhandel over de Atlantische Oceaan op grote schaal. (Canon)
- Op Nederlandse schepen werden ongeveer 550.000 tot 600.000 mensen uit Afrika vervoerd. Velen overleefden de reis niet. (Afrika-Studiecentrum Leiden; Canon)
- Op 1 juli 1863 werd de slavernij afgeschaft in Suriname en op de Antillen. Het ging om ongeveer 47.000 mensen. (CBS)
- De eigenaren kregen geld: 300 gulden per persoon in Suriname, 200 gulden op de eilanden. De vrijgemaakte mensen kregen niets. (CBS)
- In Suriname moesten vrijgemaakten van 15 tot 60 jaar nog tien jaar werken onder staatstoezicht, tot 1873. Op de eilanden gold dat niet. (CBS)
- \u201cKeti Koti\u201d is Sranantongo en betekent \u201cde ketenen zijn verbroken\u201d. (Erasmus Universiteit Rotterdam)
- Op 19 december 2022 bood premier Rutte namens de regering excuses aan. Op 1 juli 2023 deed koning Willem-Alexander dat ook. (Rijksoverheid; Koninklijk Huis)

## Goed om te gebruiken
- Schooltv: \u201cWaarom wordt Keti Koti groot gevierd in 2023?\u201d
- ProDemos: tijdlijnkaartjes Slavernijverleden.
- Canon van Nederland: venster Slavernij, met lesmateriaal.

## Bronnen
{bronnenlijst("canon_slavernij", "canon_voc", "canon_carib", "asc", "cbs1863", "eur_keti", "rijk_excuses", "koning", "words_matter", "slo", "schooltv", "prodemos")}
""",
    [
        "canon_slavernij",
        "canon_voc",
        "canon_carib",
        "asc",
        "cbs1863",
        "eur_keti",
        "rijk_excuses",
        "koning",
        "words_matter",
        "slo",
        "schooltv",
        "prodemos",
    ],
)

item(
    "po-les1-schiedam",
    "educational_workbook",
    "groep-7-8",
    "Werkblad groep 7-8, les 1: Schiedam, 1602",
    "Worksheet grades 5-6, lesson 1: Schiedam, 1602",
    "Wie zie je op het uithangbord, en wie zie je niet? Over zwarte mensen in Nederland rond 1600.",
    "Who do you see on the sign, and who don't you see?",
    f"""
## Lees eerst het verhaal
{verhaal_link("schiedam")}

{FICTIE_PO}

## Wat echt gebeurde
- In 1602 werd de VOC opgericht. Dat was een grote handelscompagnie. Schepen voeren naar Azi\u00eb, voor onder meer specerijen.
- Rond 1600 konden veel mensen niet lezen. Daarom hingen er borden met plaatjes aan herbergen en winkels. Soms was dat een \u201cmoriaan\u201d: een oud woord voor een zwart persoon. Nu vinden veel mensen dat woord kwetsend. We gebruiken het hier alleen om uit te leggen wat er vroeger hing.
- In de Republiek (zo heette Nederland toen) mocht slavernij officieel niet. Toch woonden er mensen die niet vrij waren. Later, in de 17e en 18e eeuw, namen rijke families soms tot slaaf gemaakte mensen mee uit de kolonie\u00ebn.
- De Nederlandse slavenhandel over de Atlantische Oceaan kwam pas na 1621 echt op gang, met de WIC.
- Rond 1630 tot 1660 woonde er in Amsterdam een kleine groep vrije zwarte mensen. De schilder Rembrandt schilderde en tekende hen.

## Vragen bij het verhaal
1. Hoe noemen de waard en de gasten Kwaku? Wat is zijn echte naam?
2. Waarom hangt er een bord met een gezicht boven de deur?
3. Kwaku krijgt eten en een slaapplek. Is hij vrij? Leg uit.
4. Waar praten de gasten over? Waarom zijn ze blij?

## Denk mee
\u201cIedereen in de stad kent dat gezicht. Niemand kent het zijne.\u201d Wat bedoelt de schrijver hiermee?

## Opdracht
Zoek in je eigen stad of dorp naar oude gevelstenen, straatnamen of namen van gebouwen. Zie je iets wat met dit verleden te maken heeft? Maak een foto of een tekening en vertel er in de klas over.

## Moeilijke woorden
- herberg: een soort caf\u00e9 met slaapplaatsen;
- waard: de baas van een herberg;
- compagnie: een groot bedrijf;
- tot slaaf gemaakt: iemand is met geweld eigendom van een ander gemaakt.
""",
    ["canon_voc", "maassluis", "vanpolanen", "rembrandthuis"],
    les=1,
    verhaal="schiedam",
)

item(
    "po-les2-curacao",
    "educational_workbook",
    "groep-7-8",
    "Werkblad groep 7-8, les 2: Cura\u00e7ao, 1795",
    "Worksheet grades 5-6, lesson 2: Curacao, 1795",
    "Tot slaaf gemaakte mensen kwamen in verzet. Over Tula en de opstand van 1795.",
    "Enslaved people resisted. About Tula and the revolt of 1795.",
    f"""
## Lees eerst het verhaal
{verhaal_link("curacao")}

{FICTIE_PO}

## Wat echt gebeurde
- Op 17 augustus 1795 legden tot slaaf gemaakte mensen op plantage Knip het werk neer. Hun leider was Tula. Op Cura\u00e7ao heet de plantage Kenepa.
- Ze eisten vrijheid. Ze hadden genoeg van het zware werk, de lange dagen in de hitte en het weinige eten.
- Het begon met ongeveer 50 mensen. Later deden bijna 2.000 mensen mee.
- Het leger sloeg de opstand neer. Op 3 oktober 1795 werd Tula gemarteld en gedood.
- Op Cura\u00e7ao is Tula een held. Op 17 augustus herdenken mensen daar de strijd voor vrijheid. In 2023 heeft de Nederlandse regering Tula in ere hersteld.

## Vragen bij het verhaal
1. Wat doet Maria als de anderen hun gereedschap neerleggen?
2. Waarom gaat Maria na een tijdje terug?
3. Hoe weten de kinderen en kleinkinderen van Maria wat er gebeurd is?

## Denk mee
Maria twijfelt en is bang. Waarom is meedoen met een opstand zo moeilijk? Wat stond er op het spel?

## Opdracht
Tula is nu een held. Vroeger noemden de machthebbers hem een misdadiger. Maak twee kolommen: \u201cHoe zagen de plantage-eigenaren Tula?\u201d en \u201cHoe zien mensen op Cura\u00e7ao Tula nu?\u201d Schrijf in elke kolom twee zinnen.

## Moeilijke woorden
- opstand: een groep mensen komt samen in verzet tegen de macht;
- verzet: in actie komen tegen onrecht, of tegen wie de macht heeft;
- in ere herstellen: officieel zeggen dat iemand onterecht als misdadiger is gezien.
""",
    ["rijk_tula", "npo_tula"],
    les=2,
    verhaal="curacao",
)

item(
    "po-les3-paramaribo",
    "educational_workbook",
    "groep-7-8",
    "Werkblad groep 7-8, les 3: Paramaribo, 1863",
    "Worksheet grades 5-6, lesson 3: Paramaribo, 1863",
    "Op 1 juli 1863 kwam er een einde aan de slavernij. Waarom vieren en herdenken we Keti Koti?",
    "On 1 July 1863 slavery was abolished. Why do we commemorate and celebrate Keti Koti?",
    f"""
## Lees eerst het verhaal
{verhaal_link("paramaribo")}

{FICTIE_PO}

## Wat echt gebeurde
- Op 1 juli 1863 werd de slavernij afgeschaft in Suriname en op de eilanden in het Caribisch gebied. Ongeveer 47.000 mensen werden vrij.
- In Suriname moesten vrijgemaakte mensen van 15 tot 60 jaar nog tien jaar werken met een contract, tot 1873. De staat hield toezicht. Dat heette staatstoezicht.
- De eigenaren kregen geld van de Nederlandse regering: 300 gulden per persoon in Suriname. De mensen die vrij werden, kregen niets.
- \u201cKeti Koti\u201d betekent: de ketenen zijn verbroken. Elk jaar op 1 juli herdenken en vieren mensen het einde van de slavernij.
- In 2022 bood de Nederlandse regering excuses aan voor het slavernijverleden. In 2023 deed de koning dat ook.

## Vragen bij het verhaal
1. Waarom laat Afi haar wasmand staan?
2. Welk nieuws maakt Afi minder blij?
3. Wie krijgt er geld, en wie niet?
4. Waarom zegt Afi: \u201cNog niet helemaal\u201d?

## Denk mee
De eigenaren kregen geld, de vrijgemaakte mensen niet. Wat vind jij daarvan? Waarom zou de regering dat zo gedaan hebben?

## Opdracht
Keti Koti is een herdenking en een feest tegelijk. Maak een poster voor Keti Koti op jouw school. Zet erop: wat we herdenken, wat we vieren, en de datum.

## Moeilijke woorden
- afschaffen: officieel stoppen met iets;
- staatstoezicht: de regering bleef bepalen waar en voor wie mensen moesten werken;
- herdenken: samen stilstaan bij iets uit het verleden;
- excuses aanbieden: zeggen dat iets fout was en dat het je spijt.
""",
    ["cbs1863", "eur_keti", "rijk_excuses", "koning", "schooltv"],
    les=3,
    verhaal="paramaribo",
)

item(
    "po-les4-commewijne",
    "educational_workbook",
    "groep-7-8",
    "Werkblad groep 7-8, les 4: Commewijne, 1873",
    "Worksheet grades 5-6, lesson 4: Commewijne, 1873",
    "In 1873 mochten mensen de plantages verlaten. Op hetzelfde moment kwamen er nieuwe arbeiders uit India.",
    "In 1873 people could leave the plantations. At the same time, new workers arrived from India.",
    f"""
## Lees eerst het verhaal
{verhaal_link("commewijne")}

{FICTIE_PO}

## Wat echt gebeurde
- In 1873 eindigde het staatstoezicht. Mensen mochten nu zelf kiezen waar ze gingen wonen en werken.
- De plantage-eigenaren zochten nieuwe arbeiders. Op 5 juni 1873 kwam het schip de Lalla Rookh aan in Suriname. Aan boord waren mensen uit India.
- Tussen 1873 en 1916 kwamen ruim 34.000 mensen uit India naar Suriname. Ze werkten met een contract, meestal voor vijf jaar.
- Ze kregen loon, maar weinig. Ze woonden in barakken en kregen soms lijfstraffen.
- Vanaf 1890 kwamen er ook arbeiders uit Java (toen Nederlands-Indi\u00eb, nu Indonesi\u00eb), in totaal meer dan 30.000.

## Vragen bij het verhaal
1. Wat neemt Kofi mee als hij weggaat?
2. Waarom is de eigenaar boos?
3. Sita heeft een contract getekend. Wat is het probleem met dat contract?
4. Waar gaat Sita slapen?

## Denk mee
Kofi denkt: \u201cSoms smeden mensen een nieuwe keten.\u201d Wat bedoelt hij? Is het leven van Sita hetzelfde als dat van Kofi vroeger? Wat is anders?

## Opdracht
Veel Surinaamse families hebben voorouders uit Afrika, India of Java. Bekijk samen een kaart van de wereld. Trek lijnen van Afrika, India en Java naar Suriname. Bedenk bij elke lijn: in welk jaar ongeveer, en waarom?

## Moeilijke woorden
- contract: een afspraak op papier;
- contractarbeider: iemand die voor een vaste tijd moet werken volgens een contract;
- barak: een eenvoudig gebouw waar veel mensen samen slapen;
- lijfstraf: een straf waarbij iemand pijn wordt gedaan.
""",
    ["cbs1863", "nos_lalla", "dijkgraaf", "hr_hind", "nos_java", "radboud"],
    les=4,
    verhaal="commewijne",
)

item(
    "po-les5-vlaardingen",
    "educational_workbook",
    "groep-7-8",
    "Werkblad groep 7-8, les 5: Vlaardingen, 1975",
    "Worksheet grades 5-6, lesson 5: Vlaardingen, 1975",
    "Suriname werd in 1975 onafhankelijk. Veel mensen kwamen naar Nederland, ook naar Vlaardingen.",
    "Suriname became independent in 1975. Many people moved to the Netherlands.",
    f"""
## Lees eerst het verhaal
{verhaal_link("vlaardingen")}

{FICTIE_PO}

## Wat echt gebeurde
- Op 25 november 1975 werd Suriname een onafhankelijk land. Daarvoor was het een kolonie. Vanaf 1954 was het een deel van het Koninkrijk der Nederlanden.
- In 1975 kwamen bijna 40.000 mensen uit Suriname naar Nederland. Het jaar ervoor waren het er bijna 18.000.
- Mensen kwamen om verschillende redenen. Er was meer werk in Nederland. Familie woonde er al. En wie in Nederland woonde, kon de Nederlandse nationaliteit houden.
- Nu wonen er in Nederland veel mensen met Surinaamse ouders of grootouders.
- In Vlaardingen organiseert Stichting Ketikotivlaardingen.NL de jaarlijkse herdenking en viering van Keti Koti. In 2025 was die op het Ketikotiplein.

## Vragen bij het verhaal
1. Waarom huilt oom Harry als Suriname onafhankelijk wordt?
2. Wat vindt Ravi vreemd in Vlaardingen?
3. Wie was Sita, en hoe is zij familie van Ravi?
4. Ravi zegt: \u201cHonderd jaar verschil.\u201d Welke twee reizen vergelijkt hij?

## Denk mee
Oom Harry huilt. Ravi denkt: van blijdschap en van verdriet tegelijk. Ken jij dat gevoel, blij en verdrietig tegelijk? Wanneer had jij dat?

## Opdracht
Schrijf een brief terug aan Ravi, alsof je zijn oma Nani bent. Vertel hem iets over Commewijne. Of: vraag thuis of op straat iemand naar een verhuizing of een reis die belangrijk was. Schrijf het verhaal in vijf zinnen op.

## Moeilijke woorden
- onafhankelijk: een land bestuurt zichzelf;
- kolonie: een gebied dat bestuurd wordt door een ander land ver weg;
- migratie: verhuizen naar een ander land.
""",
    ["cbs1975", "cbs_tijdlijn", "canon_carib", "kvk_stichting", "gemeenteblad_vld"],
    les=5,
    verhaal="vlaardingen",
)

# =====================================================================
# ONDERBOUW VO
# =====================================================================

item(
    "docent-vo",
    "teacher_guide",
    "onderbouw-vo",
    "Docentenhandleiding onderbouw vo: Vijf verhalen over vrijheid",
    "Teacher guide lower secondary: Five stories about freedom",
    "Een lesreeks van vijf lessen over het slavernijverleden voor de onderbouw van het voortgezet onderwijs, met bronnenwerk en perspectieven.",
    "A five-lesson series on the history of slavery for lower secondary school, with source work and perspectives.",
    f"""
## Waar gaat deze lesreeks over?
In vijf lessen onderzoeken leerlingen het Nederlandse slavernijverleden en hoe het doorwerkt in het heden. Elke les start met een kort, fictief verhaal van Het Levend Monument. Daarna toetsen de leerlingen het verhaal aan feiten en bronnen.

Centrale vraag van de reeks: \u201cHoe weten we wat er gebeurd is, en wie vertelt het verhaal?\u201d

## Voor wie en hoe lang?
- Onderbouw vo (klas 1 tot en met 3), alle niveaus. Voor vmbo kunt u de bronopdrachten inkorten.
- Vijf lessen van ongeveer 50 minuten. Losse lessen kan ook.

## Historisch denken
De werkbladen oefenen vier vaardigheden:
- feit en fictie onderscheiden: wat is verzonnen, wat is gebeurd, en hoe controleer je dat?
- perspectief: hoe zagen verschillende mensen dezelfde gebeurtenis?
- oorzaak en gevolg: waarom gebeurde iets, en wat waren de gevolgen?
- doorwerking: wat heeft dit verleden met nu te maken?

## Verhaal en feit
De personen in de verhalen zijn verzonnen. De gebeurtenissen op de achtergrond zijn echt. Elk werkblad heeft een blok \u201cWat echt gebeurde\u201d met feiten en de bron waar ze vandaan komen. Laat leerlingen minstens een bron zelf openen.

Ook bronnen zijn het niet altijd eens. Een voorbeeld: de Canon van Nederland noemt 600.000 mensen die op Nederlandse schepen werden vervoerd. Het Afrika-Studiecentrum Leiden noemt 550.000 tot 600.000. Dat verschil is een goed gesprek over hoe historici tellen en schatten.

## Woorden die we gebruiken
We gebruiken \u201ctot slaaf gemaakte\u201d in plaats van \u201cslaaf\u201d. Het woord \u201cslaaf\u201d maakt van iemand alleen eigendom. \u201cTot slaaf gemaakt\u201d laat zien dat anderen dit met geweld deden. Het Nationaal Museum van Wereldculturen en het Rijksmuseum gebruiken deze term. Er is ook discussie over: sommige mensen vinden de term omslachtig. Dat mag u met de klas bespreken. Oudere bronnen, zoals het CBS-artikel uit 2013, gebruiken nog \u201cslaven\u201d; dat is een goed startpunt voor dat gesprek.

## Veilig in de klas
- Sommige leerlingen hebben voorouders die tot slaaf zijn gemaakt, of voorouders die eraan verdienden. Maak niemand woordvoerder van een groep.
- Geen rollenspellen waarin slavernij wordt nagespeeld.
- Spreek vooraf af hoe de klas met elkaar praat: luisteren, vragen stellen, geen grappen over het onderwerp.
- Ruimte voor verschil van mening, bijvoorbeeld over excuses of herstelbetalingen. Feiten zijn niet onderhandelbaar, meningen wel.

## De vijf lessen
1. Schiedam, 1602: beeldvorming. Wie wordt afgebeeld, en wie niet? Was slavernij verboden in de Republiek?
2. Cura\u00e7ao, 1795: verzet. Hoe veranderde het beeld van Tula van \u201crebel\u201d naar verzetsheld?
3. Paramaribo, 1863: afschaffing. Wie betaalde wie? Rekenen met de cijfers van het CBS.
4. Commewijne, 1873: na de slavernij. Was contractarbeid een nieuwe vorm van onvrijheid?
5. Vlaardingen, 1975: dekolonisatie en migratie. Waarom kwamen er in 1975 zoveel Surinamers naar Nederland?

## Aansluiting bij het onderwijs
- Canon van Nederland: \u201cVOC en WIC\u201d, \u201cSlavernij\u201d, \u201cAnton de Kom\u201d en \u201cHet Caribisch gebied\u201d.
- SLO-conceptkerndoelen Mens en maatschappij (november 2024), onderbouw vo: leerlingen beschrijven hoe slavernijverleden en koloniale verhoudingen doorwerken. Ook \u201cmensenhandel tussen werelddelen\u201d staat erin. Let op: dit zijn conceptkerndoelen.

## Achtergrond voor de docent
- 1602: oprichting van de VOC. 1621: oprichting van de WIC; daarmee begon de Nederlandse trans-Atlantische slavenhandel op grote schaal. (Canon) In 1637 veroverde de WIC Fort Elmina op de Portugezen, in het huidige Ghana. (Atlas of Mutual Heritage; ProDemos)
- Ongeveer 550.000 tot 600.000 Afrikanen werden op Nederlandse schepen vervoerd, zo'n 5 tot 7 procent van de hele Atlantische slavenhandel. Velen overleefden de overtocht niet. (Afrika-Studiecentrum Leiden; Canon)
- Rond 1770 waren slavernijgerelateerde activiteiten goed voor ruim 5 procent van de Nederlandse economie. (Canon)
- In de Republiek zelf gold het vrije-bodemprincipe: wie als tot slaaf gemaakte voet aan wal zette, kon vrij worden. In 1776 werd dat beperkt: alleen wie langer dan zes maanden bleef, werd nog automatisch vrij. Toch woonden er tot slaaf gemaakten bij hun eigenaren. (Van Polanen, BMGN 2021)
- 1 juli 1863: afschaffing in Suriname en op de Antillen, ongeveer 47.000 mensen. Eigenaren kregen 300 gulden per persoon (Suriname) of 200 gulden (eilanden), samen bijna 12 miljoen gulden, ongeveer 10 procent van de rijksuitgaven in 1863. Alleen in Suriname gold tien jaar staatstoezicht. (CBS)
- 1873 tot 1916: ruim 34.000 contractarbeiders uit Brits-Indi\u00eb naar Suriname; vanaf 1890 ook zo'n 32.000 tot 33.000 uit Java. (NOS; Rijksoverheid; Radboud Universiteit)
- 25 november 1975: Suriname onafhankelijk. In 1975 kwamen 39.700 Surinamers naar Nederland. (CBS)
- In de regio: de Schiedamse regentenfamilie Pichot had banden met de Surinaamse plantageslavernij, en Schiedamse notabelen investeerden in 1773 in een plantagefonds (Gemeentearchief Schiedam, 2025). Rotterdam liet het eigen slavernijverleden onderzoeken (2020) en bood op 10 december 2021 excuses aan. (NOS)
- Excuses: kabinet op 19 december 2022 (premier Rutte), koning Willem-Alexander op 1 juli 2023. (Rijksoverheid; Koninklijk Huis)

## Bronnen
{bronnenlijst("canon_slavernij", "canon_voc", "canon_carib", "asc", "vanpolanen", "cbs1863", "eur_keti", "nos_lalla", "dijkgraaf", "nos_java", "radboud", "cbs1975", "schiedam_pichot", "nos_rotterdam", "atlas_elmina", "rijk_tula", "rijk_excuses", "koning", "words_matter", "slo", "prodemos")}
""",
    [
        "canon_slavernij",
        "canon_voc",
        "canon_carib",
        "asc",
        "vanpolanen",
        "cbs1863",
        "eur_keti",
        "nos_lalla",
        "dijkgraaf",
        "nos_java",
        "radboud",
        "cbs1975",
        "schiedam_pichot",
        "nos_rotterdam",
        "atlas_elmina",
        "rijk_tula",
        "rijk_excuses",
        "koning",
        "words_matter",
        "slo",
        "prodemos",
    ],
)

item(
    "vo-les1-schiedam",
    "educational_workbook",
    "onderbouw-vo",
    "Werkblad onderbouw vo, les 1: Schiedam, 1602",
    "Worksheet lower secondary, lesson 1: Schiedam, 1602",
    "Beeldvorming en onzichtbaarheid. Was slavernij echt verboden in de Republiek?",
    "Representation and invisibility. Was slavery really forbidden in the Dutch Republic?",
    f"""
## Lees eerst het verhaal
{verhaal_link("schiedam")}

{FICTIE_VO}

## Wat echt gebeurde
- 1602: oprichting van de VOC, op initiatief van Johan van Oldenbarnevelt. [Canon, venster VOC en WIC]
- 1621: oprichting van de WIC. Daarmee begon de Nederlandse trans-Atlantische slavenhandel op grote schaal. [Canon, venster Slavernij]
- Huizen hadden vroeger nog geen huisnummers, en veel mensen konden niet lezen. Daarom werkten gevels en uithangtekens met beelden. Een voorbeeld uit de buurt: herberg De Moriaan aan de haven van Maassluis had een moriaan als beeld op de gevel. [Historische Vereniging Maassluis]
- In de Republiek gold het vrije-bodemprincipe: een tot slaaf gemaakte die voet op Nederlandse bodem zette, kon vrij worden. In 1776 werd dat beperkt: alleen wie langer dan zes maanden met de eigenaar in de Republiek bleef, werd nog automatisch vrij. Toch woonden er tot slaaf gemaakten bij hun eigenaren in de Republiek. [Van Polanen, BMGN 2021]
- Rond 1630 tot 1660 woonde er een kleine gemeenschap van vrije zwarte mensen in Amsterdam. Rembrandt beeldde zwarte mensen af op minstens tien schilderijen. [Museum Het Rembrandthuis]
- In de 18e eeuw had de Schiedamse regentenfamilie Pichot banden met de Surinaamse plantageslavernij. [Gemeentearchief Schiedam, 2025]

## Onderzoeksvragen
1. Feit of fictie: het verhaal speelt in 1602. Wanneer begon de Nederlandse trans-Atlantische slavenhandel? Wat betekent dat voor het verhaal van Kwaku: moet hij door een Nederlander verkocht zijn, of kan het ook anders gegaan zijn?
2. In Holland \u201cis niemand een slaaf\u201d, zeggen de mensen in het verhaal. Klopt dat? Gebruik het vrije-bodemprincipe en de situatie van Kwaku in je antwoord.
3. Het uithangbord toont \u201ceen mens van ver\u201d. Wie bepaalde hoe dat beeld eruitzag? Wat zegt dat over wie er macht had?

## Perspectief
Beschrijf de herberg in drie zinnen vanuit de waard, en daarna in drie zinnen vanuit Kwaku. Wat ziet de een wel en de ander niet?

## Doorwerking
In veel Nederlandse steden zie je nog gevelstenen, uithangborden of namen met een moriaan. Wat zou je ermee doen: weghalen, laten hangen of uitleg erbij zetten? Geef twee argumenten voor je keuze en een tegenargument.

## Bronnen
{bronnenlijst("canon_voc", "canon_slavernij", "maassluis", "vanpolanen", "rembrandthuis", "schiedam_pichot")}
""",
    ["canon_voc", "canon_slavernij", "maassluis", "vanpolanen", "rembrandthuis", "schiedam_pichot"],
    les=1,
    verhaal="schiedam",
)

item(
    "vo-les2-curacao",
    "educational_workbook",
    "onderbouw-vo",
    "Werkblad onderbouw vo, les 2: Cura\u00e7ao, 1795",
    "Worksheet lower secondary, lesson 2: Curacao, 1795",
    "Van rebel tot verzetsheld: hoe het beeld van Tula veranderde.",
    "From rebel to resistance hero: how the image of Tula changed.",
    f"""
## Lees eerst het verhaal
{verhaal_link("curacao")}

{FICTIE_VO}

## Wat echt gebeurde
- Op 17 augustus 1795 legden de tot slaaf gemaakten van plantage Knip (Kenepa) onder leiding van Tula het werk neer. Het werd de grootste opstand van tot slaaf gemaakten op Cura\u00e7ao. [Rijksoverheid]
- Samen met Bazjan Karpata, Pedro Wacao en Louis Mercier bracht Tula bijna 2.000 mensen op de been. [Rijksoverheid]
- Ze eisten vrijheid en verzetten zich tegen zwaar werk, lange werkdagen in de hitte en te weinig voedsel. Tula liet zich inspireren door Toussaint Louverture, de leider van de opstand op Ha\u00efti. [NPO Kennis]
- Het koloniale bestuur stuurde eerst een bemiddelaar en daarna het leger. Tula werd verraden. Op 3 oktober 1795 werd hij gemarteld en gedood. [NPO Kennis; Rijksoverheid]
- Sinds 2010 is Tula op Cura\u00e7ao een nationale held. In oktober 2023 heeft de Nederlandse regering hem gerehabiliteerd. Premier Rutte kondigde dat aan op 19 december 2022. [Rijksoverheid]

## Onderzoeksvragen
1. Oorzaak: noem twee oorzaken van de opstand. Welke oorzaak ligt op Cura\u00e7ao zelf, en welke komt van buiten het eiland?
2. Gevolg: het bestuur liet de straf van Tula bewust aan iedereen zien. Wat wilde het daarmee bereiken?
3. Bron: open de bron van de Rijksoverheid. Waarom vond de regering het in 2023 nodig om Tula te rehabiliteren?

## Perspectief
Maak een tabel met drie kolommen: plantage-eigenaar in 1795, Maria in 1795, een inwoner van Cura\u00e7ao nu. Hoe noemt elk van hen Tula, en waarom?

## Doorwerking
Maria vertelt het verhaal door aan haar kinderen. Waarom is mondelinge overlevering belangrijk als de geschreven bronnen vooral door de machthebbers zijn gemaakt?

## Bronnen
{bronnenlijst("rijk_tula", "npo_tula", "rijk_excuses")}
""",
    ["rijk_tula", "npo_tula", "rijk_excuses"],
    les=2,
    verhaal="curacao",
)

item(
    "vo-les3-paramaribo",
    "educational_workbook",
    "onderbouw-vo",
    "Werkblad onderbouw vo, les 3: Paramaribo, 1863",
    "Worksheet lower secondary, lesson 3: Paramaribo, 1863",
    "De afschaffing van de slavernij in cijfers: wie betaalde wie, en wie kreeg niets?",
    "The abolition of slavery in numbers: who paid whom, and who received nothing?",
    f"""
## Lees eerst het verhaal
{verhaal_link("paramaribo")}

{FICTIE_VO}

## Wat echt gebeurde
- Op 1 juli 1863 werd de slavernij afgeschaft in Suriname en op de Antillen. Volgens het CBS ging het om ongeveer 47.000 mensen: 34.800 in Suriname en 11.800 op de eilanden. [CBS]
- Eigenaren kregen een vergoeding: 300 gulden per persoon in Suriname en 200 gulden op de eilanden. Samen bijna 12 miljoen gulden, ongeveer 10 procent van de rijksuitgaven in 1863. De vrijgemaakten kregen niets. [CBS]
- Alleen in Suriname gold staatstoezicht: vrijgemaakten van 15 tot 60 jaar moesten nog tien jaar contractarbeid doen, tot 1873. [CBS]
- \u201cKeti Koti\u201d is Sranantongo en betekent \u201cde ketenen zijn verbroken\u201d. In Nederland sprak men vroeger van \u201cde afschaffing\u201d, in Suriname en op de Antillen van \u201cde emancipatie\u201d. [Erasmus Universiteit Rotterdam]
- Op 19 december 2022 bood premier Rutte namens de regering excuses aan. Op 1 juli 2023 deed koning Willem-Alexander dat ook. [Rijksoverheid; Koninklijk Huis]

## Onderzoeksvragen
1. Rekenen: het CBS noemt in de tabel 32.900 mensen in Suriname waarvoor een vergoeding werd betaald. Hoeveel gulden is dat bij 300 gulden per persoon?
2. Bron: de CBS-tekst noemt ongeveer 47.000 mensen. Tel je de tabel op, dan kom je op 43.850. Bedenk twee mogelijke verklaringen voor dat verschil. Hoe zou je kunnen controleren welke klopt?
3. \u201cAfschaffing\u201d of \u201cemancipatie\u201d: welk woord legt de nadruk op wie? Welk woord zou jij gebruiken, en waarom?

## Perspectief
Schrijf twee korte krantenkoppen over 1 juli 1863: een voor een krant in Amsterdam, en een voor een krant die Afi zou lezen. Wat is het verschil?

## Doorwerking
Bekijk de toespraak van de koning (1 juli 2023). Waarom bood hij \u201czelf\u201d excuses aan? Zijn excuses genoeg, of moet er meer gebeuren? Geef je mening met een argument.

## Bronnen
{bronnenlijst("cbs1863", "eur_keti", "rijk_excuses", "koning")}
""",
    ["cbs1863", "eur_keti", "rijk_excuses", "koning"],
    les=3,
    verhaal="paramaribo",
)

item(
    "vo-les4-commewijne",
    "educational_workbook",
    "onderbouw-vo",
    "Werkblad onderbouw vo, les 4: Commewijne, 1873",
    "Worksheet lower secondary, lesson 4: Commewijne, 1873",
    "Na de slavernij kwam de contractarbeid. Een nieuwe keten, of iets anders?",
    "After slavery came indentured labour. A new chain, or something else?",
    f"""
## Lees eerst het verhaal
{verhaal_link("commewijne")}

{FICTIE_VO}

## Wat echt gebeurde
- In 1873 eindigde in Suriname het staatstoezicht. [CBS]
- Op 5 juni 1873 kwam de Lalla Rookh aan in Suriname, het eerste schip met contractarbeiders uit India. [NOS; Rijksoverheid]
- Tussen 1873 en 1916 kwamen ruim 34.000 mensen uit Brits-Indi\u00eb naar Suriname, met 64 transporten. Contracten duurden meestal vijf jaar. [NOS; Hogeschool Rotterdam]
- De regeling was een verdrag tussen Nederland en Groot-Brittanni\u00eb, als oplossing voor het tekort aan arbeid na de afschaffing van de slavernij. De arbeiders kregen weinig loon, er waren lijfstraffen en ze woonden in barakken. [Rijksoverheid, toespraak minister Dijkgraaf 2023]
- Vanaf 9 augustus 1890 kwamen ook contractarbeiders uit Java, toen Nederlands-Indi\u00eb. Tot 1939 waren het er zo'n 32.000 tot 33.000. [NOS; Radboud Universiteit]

## Onderzoeksvragen
1. Oorzaak en gevolg: leg uit hoe de afschaffing van de slavernij leidde tot de komst van contractarbeiders.
2. Vergelijk: maak een tabel met slavernij en contractarbeid. Vergelijk loon, vrijheid om weg te gaan, duur, straffen. Wat is gelijk, wat verschilt?
3. Sita tekent een contract in een taal die ze niet kan lezen. Is een contract dan eerlijk? Leg uit.

## Perspectief
Kofi zegt: \u201cSoms smeden mensen er een nieuwe.\u201d Ben je het met hem eens? Schrijf een korte reactie vanuit Sita.

## Doorwerking
Suriname is een land met veel verschillende achtergronden: Afrikaans, Indiaas, Javaans, Chinees, inheems en Europees. Zoek uit welke herdenkingsdagen er in Suriname of Nederland zijn voor de Hindostaanse en de Javaanse immigratie.

## Bronnen
{bronnenlijst("cbs1863", "nos_lalla", "dijkgraaf", "hr_hind", "nos_java", "radboud")}
""",
    ["cbs1863", "nos_lalla", "dijkgraaf", "hr_hind", "nos_java", "radboud"],
    les=4,
    verhaal="commewijne",
)

item(
    "vo-les5-vlaardingen",
    "educational_workbook",
    "onderbouw-vo",
    "Werkblad onderbouw vo, les 5: Vlaardingen, 1975",
    "Worksheet lower secondary, lesson 5: Vlaardingen, 1975",
    "Dekolonisatie en migratie: waarom kwamen er in 1975 zoveel Surinamers naar Nederland?",
    "Decolonisation and migration: why did so many Surinamese people move to the Netherlands in 1975?",
    f"""
## Lees eerst het verhaal
{verhaal_link("vlaardingen")}

{FICTIE_VO}

## Wat echt gebeurde
- Op 25 november 1975 werd Suriname een onafhankelijke republiek. Premier Den Uyl vond dat Nederland geen kolonie\u00ebn meer hoorde te hebben. Een groot deel van de bevolking van Suriname steunde de onafhankelijkheid niet. [Canon, venster Het Caribisch gebied; CBS]
- In 1974 kwamen 17.900 Surinamers naar Nederland, in 1975 39.700: een piek. Een tweede piek volgde in 1979 en 1980. [CBS]
- Redenen: de economie van Suriname ging achteruit terwijl Nederland groeide, gezinshereniging, en het behouden van de Nederlandse nationaliteit. Tot november 1980 konden Surinamers in Nederland kiezen voor de Nederlandse nationaliteit. [CBS]
- Van 1975 tot en met 2024 verhuisden 256.000 mensen van Suriname naar Nederland. [CBS]
- In Vlaardingen organiseert Stichting Ketikotivlaardingen.NL de jaarlijkse herdenking en viering van Keti Koti; dat is het doel van de stichting volgens de KvK. In 2025 was die op het Ketikotiplein. [KvK; Gemeenteblad Vlaardingen 2025]

## Onderzoeksvragen
1. Push en pull: verdeel de redenen hierboven in redenen om weg te gaan uit Suriname (push) en redenen om naar Nederland te komen (pull).
2. Grafiek: maak een staafdiagram van de immigratie in 1974, 1975, 1979 en 1980 (gebruik de CBS-bron voor 1979 en 1980). Verklaar de twee pieken.
3. Feit of fictie: Ravi schrijft dat er in 1975 \u201cbijna veertigduizend\u201d mensen uit Suriname kwamen. Controleer dat in de CBS-bron. Waarom is het belangrijk dat schrijvers van historische verhalen hun cijfers controleren?

## Perspectief
Oom Harry huilt bij de onafhankelijkheid, \u201cvan blijdschap of van verdriet, allebei\u201d. Waarom kan een gebeurtenis voor dezelfde persoon tegelijk goed en moeilijk zijn?

## Doorwerking
Ravi verbindt zijn reis met die van Sita in 1873, de grootmoeder van zijn oma. Maak een tijdlijn van 1602 tot nu met de vijf verhalen uit deze lesreeks. Zet bij elk jaar een gebeurtenis die echt gebeurde, en schrijf onder de tijdlijn: wat heeft dit verleden met Nederland nu te maken?

## Bronnen
{bronnenlijst("canon_carib", "cbs1975", "cbs_tijdlijn", "kvk_stichting", "gemeenteblad_vld")}
""",
    ["canon_carib", "cbs1975", "cbs_tijdlijn", "kvk_stichting", "gemeenteblad_vld"],
    les=5,
    verhaal="vlaardingen",
)

data = {
    "toelichting": "Gegenereerd door scripts/seed/bouw_lesmateriaal.py (niet met de hand bewerken). Lesmateriaal bij de vijf demoverhalen. Docentenhandleidingen zijn openbaar (visibility public); werkbladen alleen met een klascode (visibility edu). Feitencheck 2026-11-02.",
    "items": items,
}
out = "scripts/seed/levend_monument_lesmateriaal.json"
with open(out, "w", encoding="ascii", newline="\n") as f:
    json.dump(data, f, ensure_ascii=True, indent=2)
    f.write("\n")
print(len(items), "items ->", out)

# Runbook: Notice and Takedown (NTD)

**Doel**: NTD-verzoeken verwerken conform `art. 6:196c BW` (NL host-aansprakelijkheid).
**SLA**: 5 werkdagen reactie-tijd op alle verzoeken.
**Eigenaar**: Curator + bestuur (escalatie).

## Wettelijk kader

`Art. 6:196c lid 4 BW`: een hosting-dienst is niet aansprakelijk voor onrechtmatige content **mits** zij prompt actie onderneemt na kennisgeving. NTD-procedure beschermt dus zowel de uploader als het platform.

## Wanneer is NTD van toepassing

| Type claim | Voorbeeld |
| --- | --- |
| Auteursrecht | Foto van professionele fotograaf zonder toestemming geupload |
| Portretrecht | Persoon op foto wil verwijdering |
| AVG-recht | Persoonsgegevens van derde in verhaal genoemd |
| Smaad / laster | Onjuiste beschuldiging in tekst |
| Auteursrecht erfgenamen | Familie van overleden kunstenaar |
| Onrechtmatige inhoud | Haatdragend, discriminerend |

## Flow

```
Verzoek binnen via /takedown formulier (of e-mail)
    |
    v
1. Triage (binnen 1 werkdag)
   - hCaptcha + IP rate-limit voorkomt spam
   - Auto-mail ontvangstbevestiging met ticketnummer
   - Notificatie naar curator (#takedowns Slack-channel)
    |
    v
2. Beoordeling (binnen 4 werkdagen)
   - Curator opent TakedownRequest
   - Verzoek + content + uploader-info bekijken
   - Bij twijfel: escaleren naar bestuur
    |
    v
3. Beslissing
    |
    v
   APPROVE                                REJECT
       |                                     |
       v                                     v
   Content REMOVED                      Beargumenteerde afwijzing
   Uploader notify (e-mail)             Naar verzoeker (e-mail)
   Verzoeker notify                     Naar audit-log
   Audit-log entry
```

## Stappen

### 1. Triage

- Open `/admin/foundation/takedowns`
- Filter: `status = pending`
- Lees `legal_basis` veld
- Bepaal categorie (auteursrecht / portretrecht / AVG / etc.)

Vereisten geldig verzoek:
- Naam + e-mail verzoeker (geverifieerd via hCaptcha)
- Specifiek `content_id`
- Juridische grondslag (art. 6:196c BW vereist redelijk gemotiveerd)
- (Indien auteursrecht) bewijs van rechten

Onvolledig verzoek → e-mail naar verzoeker met aanvulvragen, status `pending`.

### 2. Beoordeling

| Vraag | Bron |
| --- | --- |
| Is grondslag plausibel? | `legal_basis` veld |
| Is content al APPROVED of nog PENDING? | `FoundationContent.status` |
| Heeft uploader verklaard dat hij rechten had? | `rights_confirmed = True` (verplicht bij upload) |
| Is uploader bereikbaar voor reactie? | `PortalUser.email` |
| Is er een eerder takedown-verzoek geweest? | filter op `content_id` in oude requests |

### 3a. APPROVE (verzoek gegrond)

```bash
# Via admin dashboard
PATCH /api/v1/admin/foundation/takedowns/{id}
{
  "status": "approved",
  "resolution_note": "Auteursrecht bewezen via {bron}. Content verwijderd."
}
```

Effect (in transactie):
- `FoundationContent.status = REMOVED`
- `FoundationContent.takedown_at = now()`
- `FoundationContent.takedown_reason = resolution_note`
- Audit-log entry met hash chain (ADR-019)
- ISR revalidate trigger naar Next.js (`POST /api/revalidate` met paths)

Notificaties:
- **Verzoeker**: e-mail "Uw verzoek is ingewilligd. Content is verwijderd op {datum}."
- **Uploader (PortalUser)**: e-mail "Uw bijdrage `{titel}` is verwijderd. Reden: {reden}. Bezwaar mogelijk binnen 14 dagen via {contact}."

### 3b. REJECT (verzoek ongegrond)

```bash
PATCH /api/v1/admin/foundation/takedowns/{id}
{
  "status": "rejected",
  "resolution_note": "Verzoek afgewezen omdat... {motivatie}"
}
```

Notificatie verzoeker:
```
Beste {naam},

Uw verzoek tot verwijdering van {content_id} is na zorgvuldige
afweging afgewezen omdat:

{motivatie}

Indien u het niet eens bent kunt u zich wenden tot de civiele rechter.

Met vriendelijke groet,
{platform_naam}
```

### 3c. ESCALATE (twijfel)

```bash
PATCH /api/v1/admin/foundation/takedowns/{id}
{
  "status": "escalated",
  "resolution_note": "Bestuur beoordeelt vanwege juridische complexiteit."
}
```

- Slack-notificatie naar bestuur-channel
- Verzoeker krijgt bericht "Uw verzoek wordt beoordeeld door bestuur. Reactie binnen 10 werkdagen."
- Bestuur beslist binnen 10 werkdagen
- Bij blijvende twijfel: extern juridisch advies inwinnen (€ 200-500 / advies)

## SLA-monitoring

| Metric | Doel | Alert |
| --- | --- | --- |
| Triage tijd (binnen werkdag) | 100% | > 1 werkdag = Slack alert |
| Beslissing binnen 5 werkdagen | 95% | > 5 werkdagen = bestuur-alert |
| Escalaties opgelost binnen 10 wd | 95% | > 10 werkdagen = juridische escalatie |

## Bezwaarprocedure (uploader)

Bij APPROVE:
1. Uploader heeft 14 dagen bezwaartermijn
2. Bezwaar via `/contact` met motivatie
3. Bestuur beoordeelt binnen 10 werkdagen
4. Bij gegrond bezwaar: content terugplaatsen, verzoeker informeren
5. Bij ongegrond bezwaar: definitief verwijderen

## Statistieken (kwartaal-rapport)

In `/admin/foundation/takedowns/stats`:
- Aantal verzoeken / kwartaal
- % approve / reject / escalate
- Gemiddelde resolutie-tijd
- Meest voorkomende grondslagen

Opgenomen in jaarverslag stichting + UVB-rapportage.

## Audit
Elke status-wijziging is een hash-chain audit-log entry (ADR-019). Verzoeker kan via reference-nummer status opvragen op `/takedown/status/{ref}`.

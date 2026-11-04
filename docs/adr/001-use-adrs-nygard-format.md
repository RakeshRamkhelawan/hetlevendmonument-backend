# ADR-001: Gebruik van ADR's (Nygard format)

## Status
Accepted

## Context
Bij de ontwikkeling van een complex multi-tenant AI-platform zoals SanskritiSetu worden dagelijks fundamentele beslissingen genomen over security boundaries, datamodellen en infrastructurele patronen. Zonder een formele structuur voor het vastleggen van deze beslissingen gaat de achterliggende rationale verloren. Dit leidt tot:
- **Technisch verval**: Nieuwe teamleden begrijpen niet waarom bepaalde guards of patronen aanwezig zijn en omzeilen deze onbewust.
- **Review-moeheid**: Dezelfde discussies worden tijdens code reviews herhaald omdat de eerdere besluitvorming niet gedocumenteerd is.
- **Audit-problemen**: Bij security audits is het lastig om aan te tonen dat isolatie-keuzes weloverwogen zijn gemaakt.

Huidige situatie:
- Beslissingen staan verspreid in Slack-logs, Jira-tickets of blijven "tribal knowledge".
- Geen centrale bron voor architecturale waarheid.

## Decision
We adopteren de **Architecture Decision Record (ADR)** methodiek volgens het Nygard-format. Elke beslissing die de architectuur, veiligheidsgrenzen of kritieke infra-patronen van het systeem raakt, wordt vastgelegd in een individueel markdown-bestand in `docs/adr/`.

### ADR Workflow & Lifecycle
1. **Proposed**: Een nieuw ADR wordt aangemaakt als PR. Discussie vindt plaats in de PR-comments.
2. **Accepted**: Zodra de PR is gemerged, krijgt het ADR de status `Accepted`.
3. **Superseded**: Als een besluit verouderd is, wordt een nieuw ADR aangemaakt dat het oude herroept. Het oude bestand krijgt de status `Superseded by ADR-XXX`.

### Kwaliteitsstandaarden (Definition of Ready)
Een ADR is pas "klaar voor review" als het de volgende onderdelen bevat:
| Deel | Vereiste Inhoud |
| :--- | :--- |
| **Context** | Beschrijving van het probleem, technische constraints en de business impact van de keuze. |
| **Decision** | De gekozen oplossing incl. **code snippets** of conceptuele diagrammen. |
| **Alternatives** | Minimaal één serieus overwogen alternatief en waarom dit is afgewezen. |
| **Consequences** | Analyse van technische schuld, monitoring-eisen en security impact. |

### Voorbeeld Implementatie (Template)
```markdown
# ADR-NNN: Titel
## Status
Accepted
## Context
...
## Decision
...
## Consequences
...
```

## Consequences
- **Positive**:
    - Volledige traceerbaarheid van de evolutie van het platform.
    - Versnelling van de onboarding van nieuwe ontwikkelaars.
    - Een levend archief dat dient als input voor security compliance (soc2/ISO).
- **Negative**:
    - Vereist discipline: Architecturale wijzigingen zonder bijbehorend ADR worden in PR-reviews afgewezen.
- **Notes**:
    - We gebruiken een sequentiële nummering (`NNN-*.md`) om een chronologische tijdlijn te behouden.

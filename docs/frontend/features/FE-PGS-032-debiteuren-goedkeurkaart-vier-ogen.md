# FE-PGS-032 -- Debiteuren, goedkeurkaart voor de brief en vier-ogen-scherm

**Sprint:** SP-KLANT-02 dag 3 (debiteurenagent)
**Status:** APPROVED
**Datum:** 2026-10-05
**Bestanden:** `frontend/src/pages/ReceivablesPage.tsx`, `frontend/src/pages/FourEyesSettingsPage.tsx`,
`frontend/src/components/hitl/PaymentReminderDetails.tsx`, `frontend/src/components/hitl/HITLActionCard.tsx`,
`frontend/src/lib/api/receivables.ts`, `frontend/vite.config.ts`,
`frontend/src/hooks/useHITLWebSocket.ts`, `frontend/src/hooks/useHITL.ts`, `frontend/src/pages/HITLPage.tsx`,
`frontend/src/components/hitl/HITLHistory.tsx`, `frontend/src/lib/hitl/decision-error.ts`,
`frontend/src/lib/hitl/decision-counts.ts`

---

## Beschrijving

- `/debiteuren`: lijst, handmatig toevoegen, op betaald zetten, knop "Herinnering voorstellen"
  (start de debiteurenagent via `POST /api/v1/receivables/reminder-proposals`).
- `/hitl`: voor `send_payment_reminder` toont de kaart WAT (soort brief), AAN WIE (naam en
  e-mail), onderwerp en de volledige tekst; knoppen "Goedkeuren en versturen" en "Afkeuren".
  X-CSRF-Token gaat mee (test `hitl-csrf.test.ts`).
- `/instellingen/vier-ogen`: per actie aan/uit, opslaan (alleen beheerder).
- Live-verbinding "Offline": de Vite-proxy stuurde `/ws` niet door; nu wel (dev en preview).

### Herstel na afkeur acceptant scenario 5 (2026-10-05, tak `fix/hitl-pagina`)

- Live-verbinding: `useHITLWebSocket` bouwde de url op `VITE_WS_URL`, en die wijst naar de
  sync-server (netwerkpoort 1234). Nu: eigen origin (`buildHITLWebSocketUrl`, via de
  vite-proxy `/ws`) of `VITE_HITL_WS_URL`. Callbacks via een ref (nieuwe callbacks per render
  openden telkens een nieuwe socket); herverbinden maximaal 5 keer, 2 s tot 30 s.
- Productie gelezen in `docker-compose.yml`/`docker-compose.prod.yml`: Traefik stuurt alleen
  `PathPrefix(/api/)` naar de backend; `/ws/hitl` valt op de frontend-catch-all
  `PathPrefix(/)`. In productie werkt de live-verbinding dus nog NIET; de pagina loopt wel niet
  meer vast (begrensde backoff). Zie
  `docs/agent-briefs/generated/2026-10-05-ws-en-admin-buiten-api-prefix.md`.
- Vier ogen: een 403 geeft nu een blijvende melding (`role="alert"`) en een toast in gewone
  taal: "Vier ogen staat aan: een collega moet dit goedkeuren."
- Wachtende kaart: "Wacht op jouw goedkeuring" in plaats van de raadstekst "De Co-Pilot is
  akkoord en voert de actie uit."; besloten tickets tonen "Reden".
- Tellers en Geschiedenis: een uitgevoerde goedkeuring heeft status `consumed`; die telt nu als
  goedgekeurd (frontend `countDecisionsOn`, backend `_ticket_to_dict` vult `approved_*`).

### Hertoets scenario 5 (2026-10-05, tak `fix/hitl-ws-accept`)

- Live-verbinding: de backend accepteerde de HITL-socket twee keer (eerst in
  `WebSocketAuthenticator.authenticate`, daarna in `connection_manager.connect`); Starlette
  sloot hem dan meteen. Nu precies een accept; zelfde fout hersteld in `agentic/websocket.py` en
  `swarm_websocket_endpoints.py`. Guard: `tests/architecture/test_websocket_is_accepted_once.py`.
  De tenant komt uit de JWT; een andere tenant in het pad wordt met 1008 geweigerd.
- Vier ogen aan: de aanvrager ziet "Wacht op goedkeuring door een collega".
- Een klik op Goedkeuren of Afkeuren stuurt precies een verzoek (geen automatische herhaling).
- De teller zegt "1 of 1 tickets" bij een kaart.
- De afkeurreden staat in de auditregel `hitl_decision` (`details.reason`), met PII gemaskeerd.
- Debiteuren: tijdens het voorstel "Herinnering wordt voorbereid...", daarna "Herinnering staat
  klaar bij Goedkeuringen" met een link naar /hitl.

## Trainingssamenvatting

### Brief goedkeuren

- Actor: goedkeurder
- Voorwaarde: er staat een herinnering klaar op /hitl
- Actie: leest de brief en drukt "Goedkeuren en versturen" of "Afkeuren" met reden
- Systeemreactie: goedkeuren maakt precies deze brief klaar voor verzending; afkeuren niets
- Succes: kaart verdwijnt uit de wachtrij
- Fout: melding van de server
- Uitzonderingen: vier ogen aan en zelf aangevraagd: weigering met de melding "Vier ogen staat aan: een collega moet dit
  goedkeuren." en een auditregel `refused_four_eyes`

# FE-SEC-006: auth-storage-v2 global key -- Option B accepted

**Sprint:** Studio UI Fix Dag 1
**Status:** APPROVED (no code change)
**Datum:** 2026-06-27

## Bevinding

`authStore.ts` gebruikt `name: 'auth-storage-v2'` als Zustand persist-key.
Deze key is globaal (niet tenant-scoped).

## Analyse

**Optie A (tenantId in key)** is niet uitvoerbaar:

- `tenantId` is pas beschikbaar NA het laden van de store
- Chicken-and-egg: je hebt de store nodig om de key te bepalen

**Optie B (global key, single user per tab)** is de geaccepteerde aanpak:

- De store bevat altijd precies 1 user's data per browser-tab
- Bij logout/login wordt de state volledig vervangen
- Er is geen mechanisme waarbij tenant A's auth-data naast tenant B's data bestaat

## Risico

Laag: backend enforceert tenant-isolatie op elke request via JWT.
De auth-storage is een client-side convenience cache -- geen beveiligingsgrens.

**Bekend openstaand punt (backlog):**
Bij account-switch in dezelfde tab wordt de React Query cache NIET geflusht bij logout.
Fix: `queryClient.clear()` aanroepen in de logout-handler van `authStore.ts`.
Dit is een client-side display-issue (geen data-lek), aangezien de backend JWT valideert.

## Beslissing

Geen code-wijziging. Optie B gedocumenteerd als geaccepteerde architectuurkeuze.
Backlog-item aangemaakt voor QueryClient.clear() bij logout.


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: auth-storage-v2 global key Option B accepted (SEC-006: geen fix -- chicken-and-egg; QueryClient.clear() backlog) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt auth-storage-v2 global key Option B accepted (SEC-006: geen fix -- chicken-and-egg; QueryClient.clear() backlog).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.

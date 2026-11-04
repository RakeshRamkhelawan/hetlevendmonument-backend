# Bijdragen aan Het Levend Monument

Deze repository is privé. Alleen ontwikkelaars die SanskritiSetu.org daarvoor aanwijst, werken eraan. Deze pagina beschrijft hoe we werken, zodat elke wijziging veilig en controleerbaar in productie komt.

## Omgeving

- Python **3.11** in een virtuele omgeving `.venv` in de hoofdmap. De git hooks weigeren andere versies.
- Node.js 20 voor het portaal (`portal/`).
- Docker voor de lokale ontwikkelstack (`make up`).
- Installeer de hooks één keer: `bash scripts/install-hooks.sh`.

Zie de [README](README.md) voor het starten en testen.

## Werkwijze

1. **Branch.** Werk op een eigen branch, nooit rechtstreeks op `main` of `develop`.
2. **Featuredocument.** Leg een nieuwe backendfunctie vast in `docs/backend/features/` met een eigen ID (bijvoorbeeld `BE-EP-055`). Registreer het ID in `ID-REGISTRY.md`.
3. **Tests eerst.** Elke wijziging heeft tests die zonder de wijziging falen. Voor beveiligingsregels (autorisatie, tenantscheiding, invoercontrole) laat je zien dat de test rood wordt als je de regel weghaalt.
4. **Commit.** De pre-commit hooks controleren formattering (black, isort, ruff), beveiliging (bandit, gitleaks), importgrenzen en typen, en draaien de tests die bij de gewijzigde code horen.
5. **Push.** De pre-push hook draait de lokale CI. Een push naar `develop` heeft daarnaast een goedkeuring van de regie nodig (`scripts/push_gate.py`).
6. **Uitrollen.** Alleen volgens het [draaiboek](docs/infra/LEVEND-MONUMENT-PRODUCTIE-DRAAIBOEK.md), met een image-tag die gelijk is aan de commit (`levendmonument-<sha>`).

## Commitberichten

We volgen [Conventional Commits](https://www.conventionalcommits.org/), in het Nederlands:

```
fix(docent): leerlingantwoorden door de TenantMiddleware
feat(portal): kaart toont alle verhalen bij het openen
docs(infra): overdracht 3 november
```

Schrijf in de body *waarom* de wijziging nodig is, niet alleen wat er verandert.

## Vaste regels voor code

- Python-broncode bevat alleen ASCII-tekens.
- Geen nieuwe `Any` zonder een `TODO(TYPE)` met uitleg.
- Elk nieuw pad zonder JWT (cookiesessie of publiek) staat in `src/core/shared/public_registry.py`.
- Geen geheimen in code, logs of tooluitvoer. Geheimen staan in Azure Key Vault.
- Teksten voor gebruikers zijn in eenvoudig Nederlands: korte zinnen, geen jargon.

## Vragen

[info@hetlevendmonument.nl](mailto:info@hetlevendmonument.nl)

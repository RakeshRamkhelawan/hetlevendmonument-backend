# BE-UTL-003: AP MCP Registry

## Overview
Registers ActivePieces npm pieces as MCP servers for agent business tools.

## Trainingssamenvatting
| Actor | Voorwaarde | Actie | Systeemreactie | Succesrespons | Foutrespons |
|-------|-----------|-------|---------------|--------------|------------|
| Systeem | Node.js beschikbaar | register_ap_piece() | MCP server gestart | Tool zichtbaar in allowlist | Error: node niet gevonden |

## Deliverables
- `src/core/tool_broker/ap_mcp_registry.py`
- `scripts/install_ap_pieces.sh`

## Test Status
- 5/5 unit tests PASS

import pytest

from src.core.activepieces.verbinding_beheer import ApVerbindingBeheer, OngeldigeApGegevens


class _Opslag:
    async def get(self, tenant_id: int) -> None:
        return None

    async def upsert(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("er mag niets worden opgeslagen")


class _Encryptie:
    def encrypt(self, tenant_id: int, plaintext: str) -> str:
        raise AssertionError("er mag niets worden versleuteld")


# TDD Phase 1.1: Secrets Validation
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "wachtwoord", "project"),
    [("", "geheim", "p1"), ("ap@example.test", "", "p1"), ("ap@example.test", "geheim", "  ")],
)
async def test_verbinding_without_credentials_is_refused_before_anything_is_stored(
    email: str, wachtwoord: str, project: str
) -> None:
    """
    Een verbinding zonder e-mail, wachtwoord of project MOET geweigerd worden, VOOR er iets
    versleuteld of opgeslagen wordt. De eis stond eerst op `ActivePiecesClient.__init__`
    (ValueError bij lege inloggegevens); de client krijgt sinds 2026-10-20 een kant-en-klare
    `ApVerbinding`, en de controle zit waar de verbinding ontstaat: `ApVerbindingBeheer`.
    """
    beheer = ApVerbindingBeheer(opslag=_Opslag(), encryptie=_Encryptie())

    with pytest.raises(OngeldigeApGegevens):
        await beheer.leg_vast(
            7,
            base_url="http://localhost:8080/api/v1",
            email=email,
            wachtwoord=wachtwoord,
            project_id=project,
        )

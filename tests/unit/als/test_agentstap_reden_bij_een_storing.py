"""De reden die een medewerker leest als de agent door een storing mislukt (agentstap dag 2, acceptatie ronde 3).

De acceptant zag bij elke mislukking "de agent kon de opdracht niet uitvoeren door een storing", ook als het taalmodel
alleen "te veel verzoeken" (429) meldde: dan helpt wachten, en een medewerker kan dat niet van een echte storing
onderscheiden. De reden blijft Nederlands en bevat nooit de tekst van de fout zelf.

Mutatiebewijs (2026-10-26): zie de eindmelding van de sessie.
"""

from __future__ import annotations

import httpx

from src.core.als.agents.workflow_stap import REDEN_STORING, REDEN_TE_DRUK, reden_bij_storing


def _http_fout(status: int) -> httpx.HTTPStatusError:
    verzoek = httpx.Request("POST", "https://api.example/v1/chat")
    return httpx.HTTPStatusError("fout", request=verzoek, response=httpx.Response(status, request=verzoek))


def test_een_429_van_het_taalmodel_zegt_dat_het_te_druk_is() -> None:
    assert reden_bij_storing(_http_fout(429)) == REDEN_TE_DRUK


def test_een_500_van_het_taalmodel_blijft_een_storing() -> None:
    assert reden_bij_storing(_http_fout(500)) == REDEN_STORING


def test_een_gewone_fout_blijft_een_storing() -> None:
    assert reden_bij_storing(RuntimeError("password=geheim")) == REDEN_STORING


def test_een_429_die_in_een_andere_fout_is_verpakt_wordt_herkend() -> None:
    try:
        try:
            raise _http_fout(429)
        except httpx.HTTPStatusError as oorzaak:
            raise RuntimeError("LLM aanroep mislukt") from oorzaak
    except RuntimeError as verpakt:
        assert reden_bij_storing(verpakt) == REDEN_TE_DRUK


def test_de_tekst_van_de_fout_komt_niet_in_de_reden() -> None:
    fout = RuntimeError("Client error 429 password=geheim host=intern.example")

    assert "geheim" not in reden_bij_storing(fout)


def test_de_getypte_te_druk_fout_van_de_aanbieder_telt() -> None:
    from src.core.services.llm.base import LLMRateLimitError

    assert reden_bij_storing(LLMRateLimitError("mistral: te veel verzoeken (429)")) == REDEN_TE_DRUK


def test_een_fout_met_alleen_de_tekst_te_veel_verzoeken_telt_niet() -> None:
    """Tekst van een medewerker kan in een foutmelding terugkomen; die mag de reden niet bepalen (Gate 2 security)."""
    assert reden_bij_storing(RuntimeError("de stap 'Te veel verzoeken' is stuk")) == REDEN_STORING


def test_de_te_drukke_reden_is_nederlands_en_zegt_wat_te_doen() -> None:
    assert "te veel verzoeken" in REDEN_TE_DRUK and "later" in REDEN_TE_DRUK

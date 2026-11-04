"""Tekst die een medewerker in een workflowstap schrijft wordt veilig ingevuld, nooit met `str.format` (agentstap nazorg).

Drie plekken vullen die tekst in met de context van de uitvoering: de prompt van een taalmodelstap, de tekstparameters van
een toolstap en de opdracht van een agentstap. `str.format` laat attributen en indexen lezen (`{input_json.__class__}`) en
faalt op accolades in gewone tekst (een JSON-voorbeeld). De veilige invuller kent alleen `{naam}` en `{naam.veld}`, alleen
dict-sleutels, en laat al het andere letterlijk staan.

Mutatiebewijs (2026-10-25): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.tekst_invullen import INGEKORT, MAX_LENGTE_WAARDE, vul_in

CONTEXT: dict[str, object] = {
    "input_json": {"klantnaam": "Jansen BV", "bedrag": 12},
    "task_1": {"result": {"aantal": 3}},
    "tenant_id": 5,
}


class TestDeInvuller:
    def test_een_json_voorbeeld_blijft_gewone_tekst(self) -> None:
        assert vul_in('Geef {"a": 1} terug', CONTEXT) == 'Geef {"a": 1} terug'

    def test_een_naam_met_een_veld_wordt_ingevuld(self) -> None:
        assert vul_in("Hallo {input_json.klantnaam}", CONTEXT) == "Hallo Jansen BV"

    def test_een_dieper_veld_wordt_ingevuld(self) -> None:
        assert vul_in("{task_1.result.aantal} facturen", CONTEXT) == "3 facturen"

    def test_een_getal_wordt_als_tekst_ingevuld(self) -> None:
        assert vul_in("{input_json.bedrag} euro", CONTEXT) == "12 euro"

    def test_attribuuttoegang_wordt_niet_ingevuld(self) -> None:
        assert vul_in("{input_json.__class__}", CONTEXT) == "{input_json.__class__}"

    def test_een_diepe_attribuutketen_wordt_niet_ingevuld(self) -> None:
        tekst = "{input_json.__init__.__globals__}"

        assert vul_in(tekst, CONTEXT) == tekst

    def test_indexering_wordt_niet_ingevuld(self) -> None:
        assert vul_in("{input_json[klantnaam]}", CONTEXT) == "{input_json[klantnaam]}"

    def test_een_opmaakspecificatie_wordt_niet_ingevuld(self) -> None:
        assert vul_in("{input_json.bedrag:>10}", CONTEXT) == "{input_json.bedrag:>10}"

    def test_een_onbekende_naam_blijft_staan(self) -> None:
        assert vul_in("{bestaat_niet}", CONTEXT) == "{bestaat_niet}"

    def test_een_onbekend_veld_blijft_staan(self) -> None:
        assert vul_in("{input_json.bestaat_niet}", CONTEXT) == "{input_json.bestaat_niet}"

    def test_de_klant_van_de_uitvoering_is_geen_invulwaarde(self) -> None:
        assert vul_in("{tenant_id}", CONTEXT) == "{tenant_id}"

    def test_een_veld_op_een_tekst_blijft_staan(self) -> None:
        assert vul_in("{input_json.klantnaam.upper}", CONTEXT) == "{input_json.klantnaam.upper}"

    def test_een_dubbele_accolade_blijft_zoals_getypt(self) -> None:
        assert vul_in("{{input_json.klantnaam}}", CONTEXT) == "{{input_json.klantnaam}}"

    def test_een_dubbele_openende_accolade_alleen_blijft_zoals_getypt(self) -> None:
        assert vul_in("{{input_json.klantnaam}", CONTEXT) == "{{input_json.klantnaam}"

    def test_een_dubbele_sluitende_accolade_alleen_blijft_zoals_getypt(self) -> None:
        assert vul_in("{input_json.klantnaam}}", CONTEXT) == "{input_json.klantnaam}}"

    def test_een_woordenboek_wordt_als_json_ingevuld(self) -> None:
        assert vul_in("{task_1.result}", CONTEXT) == '{"aantal": 3}'

    def test_een_lijst_wordt_als_json_ingevuld(self) -> None:
        context = {"stap": {"namen": ["Jan", "Piet"]}}

        assert vul_in("{stap.namen}", context) == '["Jan", "Piet"]'

    def test_een_accent_blijft_staan_in_de_json(self) -> None:
        context = {"stap": {"naam": "Café"}}

        assert vul_in("{stap}", context) == '{"naam": "Café"}'

    def test_een_te_lange_waarde_wordt_ingekort(self) -> None:
        context = {"stap": {"tekst": "x" * (MAX_LENGTE_WAARDE + 500)}}

        assert len(vul_in("{stap.tekst}", context)) <= MAX_LENGTE_WAARDE + len(INGEKORT)

    def test_een_ingekorte_waarde_zegt_dat_hij_is_ingekort(self) -> None:
        context = {"stap": {"tekst": "x" * (MAX_LENGTE_WAARDE + 500)}}

        assert vul_in("{stap.tekst}", context).endswith(INGEKORT)

    def test_een_waarde_op_de_grens_blijft_heel(self) -> None:
        context = {"stap": {"tekst": "x" * MAX_LENGTE_WAARDE}}

        assert vul_in("{stap.tekst}", context) == "x" * MAX_LENGTE_WAARDE

    def test_een_verwijzing_die_vaak_herhaald_wordt_blijft_begrensd(self) -> None:
        context = {"stap": {"tekst": "x" * MAX_LENGTE_WAARDE}}
        tekst = "{stap.tekst}" * 1000

        # Vast getal, niet de constante: anders vergelijkt de test de grens met zichzelf.
        assert len(vul_in(tekst, context)) <= 200_000 + len(INGEKORT)

    def test_het_geheugen_blijft_begrensd_bij_een_zeer_vaak_herhaalde_verwijzing(self) -> None:
        """Gemeten in Gate 2 security: 20000 verwijzingen naar een waarde van 20000 tekens gaf een piek van circa 800 MB."""
        import tracemalloc

        context = {"a": "x" * 100_000}
        tekst = "{a}" * 20_000

        tracemalloc.start()
        try:
            vul_in(tekst, context)
            _, piek = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert piek < 50 * 1024 * 1024

    def test_een_vaak_herhaalde_verwijzing_eindigt_ingekort(self) -> None:
        context = {"a": "x" * 100_000}

        assert vul_in("{a}" * 20_000, context).endswith(INGEKORT)

    def test_een_zeer_diep_woordenboek_geeft_geen_fout(self) -> None:
        diep: dict[str, object] = {}
        huidig = diep
        for _ in range(5000):
            nieuw: dict[str, object] = {}
            huidig["k"] = nieuw
            huidig = nieuw

        assert isinstance(vul_in("{stap}", {"stap": diep}), str)

    def test_tenant_id_in_een_later_padsegment_wordt_niet_ingevuld(self) -> None:
        context = {"b": {"tenant_id": 5}}

        assert vul_in("{b.tenant_id}", context) == "{b.tenant_id}"

    def test_een_lange_staart_na_de_laatste_verwijzing_blijft_begrensd(self) -> None:
        context = {"a": "x" * 19_000}
        tekst = "{a}" * 9 + "y" * 150_000

        assert len(vul_in(tekst, context)) <= 200_000 + len(INGEKORT)

    def test_dezelfde_verwijzing_wordt_binnen_een_aanroep_maar_een_keer_omgezet(self) -> None:
        from unittest.mock import patch

        import src.core.workflow.tekst_invullen as module

        with patch.object(module, "_zoek", wraps=module._zoek) as spion:
            vul_in("{input_json.klantnaam} en {input_json.klantnaam} en {input_json.klantnaam}", CONTEXT)

        assert spion.call_count == 1

    def test_miljoenen_lege_verwijzingen_kosten_geen_seconden_cpu(self) -> None:
        """Gemeten in Gate 2 security (hertoets): 3 miljoen verwijzingen die leeg oplossen kostten 8,5 s CPU."""
        import time

        begin = time.perf_counter()
        vul_in("{a}" * 3_000_000, {"a": ""})

        assert time.perf_counter() - begin < 2.0

    def test_een_open_accolade_met_een_zeer_lange_padstaart_blijft_in_het_geheugen_begrensd(self) -> None:
        """Gemeten: `{` gevolgd door 5 miljoen keer `a.` zonder sluitende accolade gaf 730 MB piek in de regex."""
        import tracemalloc

        tracemalloc.start()
        try:
            vul_in("{" + "a." * 5_000_000, {"a": "x"})
            _, piek = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert piek < 100 * 1024 * 1024

    def test_miljoenen_lege_verwijzingen_worden_als_te_lange_invoer_ingekort(self) -> None:
        # Deterministisch: de tijdgrens hierboven hangt van de machine af, de inkorting niet.
        assert vul_in("{a}" * 3_000_000, {"a": ""}).endswith(INGEKORT)

    def test_de_aanduiding_staat_niet_twee_keer_achter_elkaar(self) -> None:
        """Hertoets Gate 2: een te lange invoer die daarna ook het uitvoerbudget haalt gaf `[ingekort] [ingekort]`."""
        context = {"a": "x" * 19_000}
        tekst = "{a}" * 12 + "y" * 200_000

        assert not vul_in(tekst, context).endswith(INGEKORT + INGEKORT)

    def test_een_verwijzing_die_precies_op_de_invoergrens_wordt_afgekapt_is_een_bekende_afwijking(self) -> None:
        """Bewust vastgelegd (Laag): `{b}}` blijft letterlijk, maar na een afkap op de grens blijft alleen `{b}` over en dat
        wordt ingevuld. Er komt geen toegang bij: alleen een waarde die de medewerker toch al mocht invullen."""
        tekst = "a" * (200_000 - 3) + "{b}}"

        assert vul_in(tekst, {"b": "X"}).startswith("a" * (200_000 - 3) + "X")

    def test_een_te_lange_invoer_wordt_ingekort_en_gemarkeerd(self) -> None:
        # Vaste getallen, niet de constante: anders vergelijkt de test de grens met zichzelf.
        assert vul_in("y" * 200_001, {}).endswith(INGEKORT)

    def test_een_invoer_op_de_grens_blijft_heel(self) -> None:
        assert vul_in("y" * 200_000, {}) == "y" * 200_000

    def test_een_enorm_geheel_getal_geeft_geen_fout(self) -> None:
        """Python weigert str() van een geheel getal met meer dan 4300 cijfers met een ValueError."""
        assert isinstance(vul_in("{n}", {"n": 10**5000}), str)

    def test_een_lege_tekst_blijft_leeg(self) -> None:
        assert vul_in("", CONTEXT) == ""


def _engine() -> ProductionWorkflowEngine:
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=MagicMock(content="ok", usage={}, model="m", error=None))
    broker = MagicMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})
    runtime = MagicMock()
    runtime.run_agentstap = AsyncMock(return_value={"success": True, "output": {}})
    return ProductionWorkflowEngine(llm_provider=llm, tool_broker=broker, agent_runtime=runtime)


@pytest.mark.asyncio
class TestDeDrieEnginePlekken:
    async def test_een_opdracht_met_een_json_voorbeeld_wordt_uitgevoerd(self) -> None:
        engine = _engine()

        await engine._execute_agent_task(
            {"agent_id": "dunning", "instruction": 'Geef {"a": 1} terug'},
            dict(CONTEXT),
            tenant_id=5,
            starter="7",
        )

        assert engine.agent_runtime.run_agentstap.await_args.kwargs["instruction"] == 'Geef {"a": 1} terug'  # type: ignore[attr-defined]

    async def test_een_opdracht_vult_een_invoerveld_in(self) -> None:
        engine = _engine()

        await engine._execute_agent_task(
            {"agent_id": "dunning", "instruction": "Volg {input_json.klantnaam} op"},
            dict(CONTEXT),
            tenant_id=5,
            starter="7",
        )

        assert engine.agent_runtime.run_agentstap.await_args.kwargs["instruction"] == "Volg Jansen BV op"  # type: ignore[attr-defined]

    async def test_een_opdracht_geeft_geen_klassegegevens_prijs(self) -> None:
        engine = _engine()

        await engine._execute_agent_task(
            {"agent_id": "dunning", "instruction": "{input_json.__class__}"},
            dict(CONTEXT),
            tenant_id=5,
            starter="7",
        )

        assert engine.agent_runtime.run_agentstap.await_args.kwargs["instruction"] == "{input_json.__class__}"  # type: ignore[attr-defined]

    async def test_een_prompt_met_een_json_voorbeeld_wordt_uitgevoerd(self) -> None:
        engine = _engine()

        await engine._execute_llm_task({"prompt": 'Antwoord als {"a": 1}'}, dict(CONTEXT), tenant_id=5)

        assert engine.llm_provider.generate.await_args.kwargs["prompt"] == 'Antwoord als {"a": 1}'  # type: ignore[attr-defined]

    async def test_een_prompt_geeft_geen_klassegegevens_prijs(self) -> None:
        engine = _engine()

        await engine._execute_llm_task(
            {"prompt": "{input_json.__init__.__globals__}"}, dict(CONTEXT), tenant_id=5
        )

        assert (
            engine.llm_provider.generate.await_args.kwargs["prompt"]  # type: ignore[attr-defined]
            == "{input_json.__init__.__globals__}"
        )

    async def test_een_toolparameter_vult_een_invoerveld_in(self) -> None:
        engine = _engine()

        await engine._execute_tool_task(
            {"tool_name": "t", "parameters": {"onderwerp": "Aan {input_json.klantnaam}", "n": 3}},
            dict(CONTEXT),
            tenant_id=5,
            starter="7",
        )

        assert engine.tool_broker.execute_tool.await_args.kwargs["parameters"] == {  # type: ignore[attr-defined]
            "onderwerp": "Aan Jansen BV",
            "n": 3,
        }

    async def test_een_toolparameter_met_accolades_wordt_uitgevoerd(self) -> None:
        engine = _engine()

        await engine._execute_tool_task(
            {"tool_name": "t", "parameters": {"body": '{"a": 1}'}},
            dict(CONTEXT),
            tenant_id=5,
            starter="7",
        )

        assert engine.tool_broker.execute_tool.await_args.kwargs["parameters"] == {"body": '{"a": 1}'}  # type: ignore[attr-defined]

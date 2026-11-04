"""Per stap van een uitvoering ziet de medewerker wat er gebeurde, in het Nederlands (agentstap dag 2, Keten G).

De uitvoeringsstatus kreeg een lijst `stappen`; `stap_overzicht` maakt er een regel van uit een taakrij. Een geweigerde of
mislukte agentstap toont de Nederlandse reden die de engine bewaarde, nooit een Engelse statuscode of een stacktrace.

Mutatiebewijs (2026-10-25): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.core.workflow.stap_overzicht import stap_overzicht


def _taak(**velden: object) -> SimpleNamespace:
    basis: dict[str, object] = {
        "task_ref": "n1",
        "task_type": "agent",
        "status": SimpleNamespace(value="succeeded"),
        "result_json": None,
        "error_json": None,
    }
    basis.update(velden)
    return SimpleNamespace(**basis)


def test_een_geslaagde_agentstap_heet_uitgevoerd() -> None:
    regel = stap_overzicht(_taak(result_json={"success": True, "agent_id": "dunning", "output": {}}))

    assert regel["status"] == "Uitgevoerd"


def test_een_stap_noemt_de_agent_met_de_nederlandse_naam() -> None:
    regel = stap_overzicht(_taak(result_json={"success": True, "agent_id": "dunning", "output": {}}))

    assert regel["naam"] == "Debiteurenagent"


def test_een_mislukte_stap_toont_de_nederlandse_reden_uit_de_foutkolom() -> None:
    regel = stap_overzicht(
        _taak(
            status=SimpleNamespace(value="failed"),
            error_json={"type": "StapMislukt", "message": "u mag deze agent niet starten"},
        )
    )

    assert (regel["status"], regel["reden"]) == ("Mislukt", "u mag deze agent niet starten")


def test_een_resultaattekst_van_een_mislukte_stap_wordt_niet_getoond() -> None:
    regel = stap_overzicht(
        _taak(
            status=SimpleNamespace(value="failed"),
            result_json={"success": False, "agent_id": "dunning", "error": "SELECT * FROM geheim"},
        )
    )

    assert regel["reden"] == "de stap is mislukt; vraag uw beheerder om het na te kijken"


def test_een_geslaagde_stap_heeft_geen_reden() -> None:
    regel = stap_overzicht(_taak(result_json={"success": True, "agent_id": "dunning", "output": {}}))

    assert regel["reden"] is None


def test_een_onbekende_status_krijgt_geen_engels_woord() -> None:
    regel = stap_overzicht(_taak(status=SimpleNamespace(value="retrying")))

    assert regel["status"] == "Wordt opnieuw geprobeerd"


def test_een_samenvatting_van_de_agent_wordt_getoond() -> None:
    regel = stap_overzicht(
        _taak(
            result_json={
                "success": True,
                "agent_id": "dunning",
                "output": {"summary": "3 herinneringen klaargezet"},
            }
        )
    )

    assert regel["uitkomst"] == "3 herinneringen klaargezet"


def test_een_onverwachte_fout_toont_geen_ruwe_fouttekst() -> None:
    regel = stap_overzicht(
        _taak(
            status=SimpleNamespace(value="failed"),
            error_json={"type": "RuntimeError", "message": "postgresql://gebruiker:wachtwoord@host/db"},
        )
    )

    assert "postgresql" not in str(regel["reden"])


def test_een_onverwachte_fout_krijgt_een_vaste_nederlandse_reden() -> None:
    regel = stap_overzicht(
        _taak(
            status=SimpleNamespace(value="failed"),
            error_json={"type": "RuntimeError", "message": "boom"},
        )
    )

    assert regel["reden"] == "de stap is mislukt; vraag uw beheerder om het na te kijken"


def test_een_mislukte_toolstap_toont_de_ruwe_tekst_niet() -> None:
    regel = stap_overzicht(
        _taak(
            task_type="tool",
            status=SimpleNamespace(value="failed"),
            error_json={"type": "StapMislukt", "message": "SELECT * FROM geheim WHERE sleutel='x'"},
        )
    )

    assert "SELECT" not in str(regel["reden"])


KNOOP = {"id": "node_1", "name": "Klantvraag samenvatten", "agent_id": "dunning"}


def test_een_mislukte_stap_noemt_de_naam_die_de_medewerker_gaf_en_de_agent() -> None:
    regel = stap_overzicht(
        _taak(task_ref="node_1", status=SimpleNamespace(value="failed")), {"node_1": KNOOP}
    )

    assert regel["naam"] == "Klantvraag samenvatten (Debiteurenagent)"


def test_een_stap_zonder_bekende_agent_noemt_alleen_de_gegeven_naam() -> None:
    knoop = {"id": "node_1", "name": "Klantvraag samenvatten"}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Klantvraag samenvatten"


def test_de_agent_staat_ook_in_data_van_de_knoop() -> None:
    knoop = {"id": "node_1", "name": "Vraag", "data": {"agent_id": "dunning"}}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Vraag (Debiteurenagent)"


def test_een_onbekende_agent_in_de_knoop_wordt_niet_als_naam_getoond() -> None:
    knoop = {"id": "node_1", "name": "Vraag", "agent_id": "email_agent"}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Vraag"


def test_een_stap_zonder_knoop_toont_de_technische_sleutel_als_laatste_redmiddel() -> None:
    regel = stap_overzicht(_taak(task_ref="node_9"), {})

    assert regel["naam"] == "node_9"


def test_een_lege_naam_in_de_knoop_telt_niet() -> None:
    knoop = {"id": "node_1", "name": "   ", "agent_id": "dunning"}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Debiteurenagent"


def test_de_naam_staat_bij_een_door_de_bouwer_opgeslagen_knoop_in_title() -> None:
    """De builderstore bewaart de knoop als `{id, title, data}`; `name` bestaat daar niet (acceptant, workflowscherm nazorg)."""
    knoop = {"id": "node_1", "title": "Klantvraag samenvatten", "data": {"agent_id": "dunning"}}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Klantvraag samenvatten (Debiteurenagent)"


def test_de_naam_valt_terug_op_het_label_in_data() -> None:
    knoop = {"id": "node_1", "data": {"label": "Herinnering sturen", "agent_id": "dunning"}}

    regel = stap_overzicht(_taak(task_ref="node_1"), {"node_1": knoop})

    assert regel["naam"] == "Herinnering sturen (Debiteurenagent)"


def test_name_gaat_voor_title_en_label() -> None:
    knoop = {"id": "n", "name": "Eerste", "title": "Tweede", "data": {"label": "Derde"}}

    regel = stap_overzicht(_taak(task_ref="n"), {"n": knoop})

    assert regel["naam"] == "Eerste"


def test_title_gaat_voor_label() -> None:
    knoop = {"id": "n", "title": "Tweede", "data": {"label": "Derde"}}

    regel = stap_overzicht(_taak(task_ref="n"), {"n": knoop})

    assert regel["naam"] == "Tweede"

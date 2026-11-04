"""Een workflowtaak landt op de ECHTE wachtrij, nooit op een stub die niemand leest (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was (gemeten op 8fdb38cb).** `src/workers/workflow_worker.py` zette bij het importeren een
`StubBroker` als procesbrede broker en wisselde hem pas om in `get_redis_broker()`. Actors die met `@dramatiq.actor`
waren gedecoreerd bonden aan die stub. Een `.send()` in een proces dat `get_redis_broker()` niet aanriep (elk
API-proces) belandde in een geheugenwachtrij: geen fout, geen uitvoering.

**Wat hier bewezen wordt.**
1. Elke actor die `src.workers.actors` laadt, hangt aan een echte `RedisBroker`; geen enkele aan een `StubBroker`.
2. Dat is ook zo zonder dat iemand `get_redis_broker()` aanriep (de situatie van de API).
3. Is Redis onbereikbaar, dan geeft `.send()` een fout in plaats van een stil succes.
4. In tests komt een bericht via de fixture op een StubBroker, niet op Redis: de fixture werkt en zegt wat hij doet.

**Mutatiebewijs (2026-10-21), per element en in beide richtingen:**
- `workflow_actor` laat `broker=` vallen                  -> de binding-tests en de guard ROOD, de rest groen
- de fixture `taken_naar_een_stubbroker` uitgezet          -> `test_de_fixture_vangt_send_op_zonder_redis` ROOD
- een actor niet aan de workflowbroker hangen              -> `test_elke_actor_buiten_de_twee_eigen_werkers...` ROOD
- ongewijzigd                                             -> GROEN
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

import dramatiq
import pytest
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from src.core.tasks.dramatiq_broker import bouw_broker, workflow_actor, workflow_broker

#: De modules waarvan het importeren actors registreert; `src.workers.actors` haalt de meeste binnen.
_ACTORMODULES = (
    "src.workers.workflow_worker",
    "src.workers.actors",
    "src.workers.calendar_sync_worker",
)


def _alle_actors() -> dict[str, Any]:
    """Elke dramatiq-actor die in een geimporteerde `src`-module als attribuut staat, per `module.naam`."""
    for naam in _ACTORMODULES:
        importlib.import_module(naam)
    gevonden: dict[str, Any] = {}
    for modulenaam, module in list(sys.modules.items()):
        if not modulenaam.startswith("src.") or module is None:
            continue
        for attribuut, waarde in list(vars(module).items()):
            if isinstance(waarde, dramatiq.Actor):
                gevonden[f"{modulenaam}.{attribuut}"] = waarde
    return gevonden


class TestElkeActorHangtAanEenEchteBroker:
    def test_er_zijn_actors_gevonden(self) -> None:
        """Controlegroep: de meting ziet de actors, anders zegt een lege uitslag niets."""
        assert len(_alle_actors()) >= 20

    def test_geen_enkele_actor_hangt_aan_een_stubbroker(self) -> None:
        aan_een_stub = sorted(
            naam for naam, actor in _alle_actors().items() if isinstance(actor.broker, StubBroker)
        )

        assert aan_een_stub == []

    def test_elke_actor_buiten_de_twee_eigen_werkers_hangt_aan_de_workflowbroker(self) -> None:
        """Niet alleen "geen stub": ook niet aan de procesbrede standaardbroker die dramatiq zelf maakt.

        De leerwerker en de bonlezer hebben bewust hun EIGEN broker (eigen proces, eigen wachtrij).
        """
        eigen = ("src.core.learning.worker", "src.core.als.bonlezer.worker")
        # Op de module waar de FUNCTIE is gedefinieerd, niet waar het actor-object als attribuut staat: de
        # upload-route importeert `lees_bon` van de bonlezer en is daarmee zelf geen workflowactor.
        elders = sorted(
            naam
            for naam, actor in _alle_actors().items()
            if not actor.fn.__module__.startswith(eigen) and actor.broker is not workflow_broker
        )

        assert elders == []

    def test_de_workflowactors_hangen_aan_de_workflowbroker(self) -> None:
        from src.workers import workflow_worker

        actors = {
            "execute_workflow_task": workflow_worker.execute_workflow_task,
            "execute_task_task": workflow_worker.execute_task_task,
        }

        assert {naam: actor.broker is workflow_broker for naam, actor in actors.items()} == {
            "execute_workflow_task": True,
            "execute_task_task": True,
        }

    def test_de_workflowbroker_is_een_echte_redisbroker(self) -> None:
        assert isinstance(workflow_broker, RedisBroker)

    def test_zonder_get_redis_broker_aan_te_roepen_is_de_broker_al_de_echte(self) -> None:
        """De API-situatie: niemand riep `get_redis_broker()` aan, en toch is er geen stub."""
        from src.workers import workflow_worker

        assert not isinstance(workflow_worker.execute_workflow_task.broker, StubBroker)

    def test_de_werkeropdracht_redis_broker_levert_dezelfde_broker(self) -> None:
        """`dramatiq src.workers.workflow_worker:redis_broker` (compose, Dockerfile, CD) blijft werken."""
        from src.workers import workflow_worker

        assert workflow_worker.redis_broker is workflow_broker

    def test_get_redis_broker_geeft_dezelfde_broker_terug(self) -> None:
        """ActivePieces dag 1 (`workflow_verzending.py`) roept dit aan; het blijft een ongevaarlijke aanroep."""
        from src.workers import workflow_worker

        assert workflow_worker.get_redis_broker() is workflow_broker


class TestRedisOnbereikbaarIsEenFout:
    @pytest.mark.echte_netwerkverbinding_toegestaan
    def test_send_naar_een_onbereikbare_redis_geeft_een_fout_geen_stil_succes(self) -> None:
        """Verbindt BEWUST echt: naar poort 1 op localhost, waar niets luistert, zodat de weigering direct komt.

        Dit is precies het gedrag dat de stub verborg: `.send()` moet falen als Redis weg is.
        """
        dode_broker = bouw_broker("redis://127.0.0.1:1/0?socket_connect_timeout=1")

        @dramatiq.actor(broker=dode_broker)
        def _taak() -> None: ...

        with pytest.raises(Exception) as fout:  # noqa: B017 -- het type is van redis-py, de eis is "niet stil"
            _taak.send()

        assert "onnect" in type(fout.value).__name__ or "onnect" in str(fout.value)

    def test_workflow_actor_bindt_aan_de_workflowbroker_en_niet_aan_een_procesbrede(self) -> None:
        @workflow_actor(queue_name="zonder_globale_staat")
        def _taak() -> None: ...

        assert _taak.broker is workflow_broker


class TestInTestsKomtEenBerichtOpEenStub:
    def test_de_fixture_vangt_send_op_zonder_redis(self) -> None:
        from src.workers import workflow_worker

        bericht = workflow_worker.execute_workflow_task.send("exec_fixture", 1)

        assert (bericht.queue_name, workflow_broker.enqueue.__name__) == ("default", "_enqueue")

    @pytest.mark.echte_broker
    def test_met_de_markering_echte_broker_is_de_fixture_uit(self) -> None:
        assert "enqueue" not in vars(workflow_broker)

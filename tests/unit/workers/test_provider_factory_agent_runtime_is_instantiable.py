"""ProviderFactory moet werkende providers opleveren, niet alleen de agent-runtime (P0).

**De bevinding (2026-08-27, gevonden tijdens OP-13-impactanalyse, niet vermoed maar
gereproduceerd).** `src/workers/workflow_worker.py`'s eigen `ProductionAgentRuntime`
implementeerde alleen `__init__` en een ongebruikte `invoke_agent()` -- niet de vier
abstracte methodes die `IAgentRuntime` vereist (`load_agent`, `execute_agent`, `run_agent`,
`get_available_agents`). `ProviderFactory.create_agent_runtime()` instantieert deze klasse
zonder override (`ProviderFactory.set_providers()` wordt nergens in `src/` aangeroepen), dus
elke ECHTE aanroep van `create_workflow_engine()` -- "the main factory function used by
workers", aangeroepen vanuit `execute_workflow_task`'s hot path -- gaf gegarandeerd:

    TypeError: Can't instantiate abstract class ProductionAgentRuntime without an
    implementation for abstract methods 'execute_agent', 'get_available_agents',
    'load_agent', 'run_agent'

**Dezelfde bug bleek NOG TWEE KEER te zitten, ontdekt bij het repareren van de eerste.**
`ProductionLLMProvider` implementeerde `complete`/`embed` in plaats van de huidige
`ILLMProvider`-interface (`generate`/`moderate`), en `ProductionToolBroker` implementeerde
`list_tools` in plaats van `list_available_tools`. Beide dus ook een gegarandeerde
`TypeError` bij elke echte aanroep -- alle drie lokale klassen waren blijkbaar geschreven
tegen een OUDERE versie van `interfaces.py` en nooit meegegroeid met een latere
interface-hernoeming. `create_workflow_engine()` faalde daardoor zelfs AL bij
`create_llm_provider()`, voordat de agent-runtime-crash uberhaupt bereikt werd.

De `workflow-worker`-service in `docker-compose.prod.yml` is een echte, gedeployde service
(`restart: always`, verplichte env-vars, CD-workflows wiren hem expliciet voor staging).
Met Dramatiq's retry-dan-dead-letter-gedrag faalde elke workflow-uitvoering stil, zonder
foutmelding die iemand zou opmerken -- exact het patroon dat OP-158/OP-35/OP-06 elders in
ADR-036 al blootlegden.

**De fix.** `src/core/workflow/providers.py` heeft alle drie de volledige, actueel-interface-
conforme implementaties (`ProductionLLMProvider`, `ProductionToolBroker`,
`ProductionAgentRuntime`), inclusief `agent_router`-injectie op de laatste (dezelfde
SP-AGT-003-functionaliteit die voorheen alleen in de dode `core/workflow/worker.py`-module
zat). `workers/workflow_worker.py` importeert nu alle drie die werkende klassen in plaats
van zijn eigen kapotte kopieen te definieren.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestTheDefaultAgentRuntimeIsInstantiable:
    def test_create_agent_runtime_does_not_raise(self) -> None:
        """De kern van de P0-bevinding: dit riep altijd een TypeError op."""
        from src.workers.workflow_worker import ProviderFactory

        runtime = ProviderFactory.create_agent_runtime()

        assert runtime is not None

    def test_the_runtime_implements_every_abstract_method(self) -> None:
        """Expliciet de vier methodes die IAgentRuntime vereist -- niet alleen "geen crash",
        want een subklasse die toevallig WEL instantieert door een andere reden (bv. een
        ander abstract-methode-gat) zou de eerste test ook laten slagen.
        """
        from src.workers.workflow_worker import ProviderFactory

        runtime = ProviderFactory.create_agent_runtime()

        for method_name in ("load_agent", "execute_agent", "run_agent", "get_available_agents"):
            assert hasattr(runtime, method_name) and callable(getattr(runtime, method_name)), (
                f"ProductionAgentRuntime mist {method_name}"
            )


@pytest.mark.unit
class TestTheDefaultLLMProviderIsInstantiable:
    def test_create_llm_provider_does_not_raise(self) -> None:
        from src.workers.workflow_worker import ProviderFactory

        provider = ProviderFactory.create_llm_provider()

        assert provider is not None

    def test_the_provider_implements_every_abstract_method(self) -> None:
        from src.workers.workflow_worker import ProviderFactory

        provider = ProviderFactory.create_llm_provider()

        for method_name in ("generate", "moderate", "embed"):
            assert hasattr(provider, method_name) and callable(getattr(provider, method_name)), (
                f"ProductionLLMProvider mist {method_name}"
            )


@pytest.mark.unit
class TestTheDefaultToolBrokerIsInstantiable:
    def test_create_tool_broker_does_not_raise(self) -> None:
        from src.workers.workflow_worker import ProviderFactory

        broker = ProviderFactory.create_tool_broker()

        assert broker is not None

    def test_the_broker_implements_every_abstract_method(self) -> None:
        from src.workers.workflow_worker import ProviderFactory

        broker = ProviderFactory.create_tool_broker()

        for method_name in ("execute_tool", "list_available_tools"):
            assert hasattr(broker, method_name) and callable(getattr(broker, method_name)), (
                f"ProductionToolBroker mist {method_name}"
            )


@pytest.mark.unit
class TestTheAgentRouterIsInjectable:
    def test_create_agent_runtime_accepts_an_agent_router(self) -> None:
        """SP-AGT-003: agent_router-injectie moet ook op het LEVENDE pad werken, niet alleen
        in de dode core/workflow/worker.py-module waar dit voorheen uitsluitend zat.
        """
        from src.workers.workflow_worker import ProviderFactory

        sentinel = object()
        runtime = ProviderFactory.create_agent_runtime(agent_router=sentinel)

        assert getattr(runtime, "_agent_router", None) is sentinel

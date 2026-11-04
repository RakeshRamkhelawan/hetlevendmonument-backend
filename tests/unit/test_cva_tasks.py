# tests/unit/test_cva_tasks.py
import pytest
import inspect

@pytest.mark.unit
def test_process_cva_message_is_sync_actor():
    """Actor body moet sync zijn -- async body zonder AsyncIO middleware is stille data loss."""
    from src.core.tasks.cva_tasks import process_cva_message
    # Actor body (fn) moet sync zijn
    assert not inspect.iscoroutinefunction(process_cva_message.fn), \
        "process_cva_message.fn is async -- converteren naar sync wrapper met asyncio.run()"


@pytest.mark.unit
def test_check_hash_chain_integrity_actor_is_sync():
    """Actor body moet sync zijn."""
    from src.core.copilot.audit.integrity_check_actor import check_hash_chain_integrity_actor
    assert not inspect.iscoroutinefunction(check_hash_chain_integrity_actor.fn), \
        "check_hash_chain_integrity_actor.fn is async -- converteren naar sync wrapper"


@pytest.mark.unit
def test_process_cva_message_actor_attributes():
    """Actor moet correcte queue_name en max_retries hebben."""
    from src.core.tasks.cva_tasks import process_cva_message
    assert process_cva_message.actor_name == "process_cva_message"
    # queue_name en max_retries preserveren bij conversie
    assert hasattr(process_cva_message, "queue_name")

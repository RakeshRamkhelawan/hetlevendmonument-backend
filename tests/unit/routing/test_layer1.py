import pytest

from src.core.routing.layer1_keyword import KeywordRouter
from src.core.shared.interfaces import TaskData


def test_layer1_match_finance():
    router = KeywordRouter()
    task = TaskData(title="Payment", description="Pay this invoice", metadata={"text": "invoice"})
    target = router.route(task)
    assert target == "finance_supervisor"


def test_layer1_match_hr():
    router = KeywordRouter()
    task = TaskData(title="Hire", description="New candidate", metadata={"text": "hiring"})
    target = router.route(task)
    assert target == "hr_supervisor"


def test_layer1_no_match():
    router = KeywordRouter()
    task = TaskData(
        title="Unknown", description="Vague request", metadata={"text": "something else"}
    )
    target = router.route(task)
    assert target is None

"""Test that deliberately triggers container.wire() to reproduce pollution."""


def test_trigger_container_wire():
    """Import src.main which triggers container.wire() at module level."""
    from src.main import app

    assert app is not None

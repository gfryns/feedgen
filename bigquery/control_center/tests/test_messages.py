import pytest
from messages import StateUpdateMessage, StatusUpdateMessage

def test_state_update_message():
    msg = StateUpdateMessage("key", "value")
    assert msg.key == "key"
    assert msg.value == "value"

def test_status_update_message():
    msg = StatusUpdateMessage("step", "status")
    assert msg.step == "step"
    assert msg.status == "status"

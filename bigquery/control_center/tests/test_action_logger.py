import os
import pytest
from action_logger import log_action

def test_log_action(tmp_path, monkeypatch):
    log_file = tmp_path / "test_log.txt"
    monkeypatch.setattr("action_logger.DEBUG_LOG_FILE", str(log_file))
    
    log_action("Test Action", "Test Details")
    
    assert os.path.exists(str(log_file))
    content = log_file.read_text()
    assert "ACTION: Test Action" in content
    assert "DETAILS: Test Details" in content

import json
import os
import pytest
from state_manager import ControlCenterStateManager

def test_init_loads_state(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"project": "test"}')
    
    sm = ControlCenterStateManager(filename=str(state_file))
    assert sm.get('project') == "test"

def test_init_empty_file(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('') # Invalid JSON
    
    sm = ControlCenterStateManager(filename=str(state_file))
    assert sm.data == {}

def test_set_and_get(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    
    sm.set('key', 'value')
    assert sm.get('key') == 'value'
    
    # Verify file was saved
    content = json.loads(state_file.read_text())
    assert content['key'] == 'value'

def test_update_data(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    
    sm.update_data({'key1': 'value1', 'key2': 'value2'})
    assert sm.get('key1') == 'value1'
    assert sm.get('key2') == 'value2'

def test_get_step_status_default(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    assert sm.get_step_status('infra') == 'Pending'

def test_set_step_status(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    
    sm.set_step_status('infra', 'Completed')
    assert sm.get_step_status('infra') == 'Completed'

def test_check_dependency(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    
    # 'source' depends on 'infra'
    allowed, msg = sm.check_dependency('source')
    assert allowed == False
    assert "infra" in msg
    
    sm.set_step_status('infra', 'Completed')
    allowed, msg = sm.check_dependency('source')
    assert allowed == True
    assert msg == ""

def test_invalidate_descendants(tmp_path):
    state_file = tmp_path / "state.json"
    sm = ControlCenterStateManager(filename=str(state_file))
    
    sm.set_step_status('infra', 'Completed')
    sm.set_step_status('source', 'Completed')
    
    # Invalidate 'infra' should invalidate 'source'
    sm.invalidate_descendants('infra')
    
    assert sm.get_step_status('infra') == 'Completed' # Not invalidated itself
    assert sm.get_step_status('source') == 'Pending'

import pytest
from unittest.mock import patch, MagicMock
from services.examples_service import get_examples_preview, load_examples_from_sheet, load_examples_by_ids, clear_examples

class TestExamplesService:
    
    @patch('services.examples_service.get_bq_client')
    def test_get_examples_preview(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_count_res = MagicMock()
        mock_count_res.__getitem__.return_value = 10
        mock_bq.query.return_value.result.side_effect = [[mock_count_res], [{'id': '1', 'title': 'T1', 'description': 'D1'}]]
        
        # Act
        count, preview = get_examples_preview("test-proj", "test_ds")
        
        # Assert
        assert count == 10
        assert len(preview) == 1
        assert preview[0] == ("1", "T1", "D1")

    @patch('services.examples_service.get_bq_client')
    @patch('google.auth.default')
    @patch('gspread.authorize')
    def test_load_examples_from_sheet(self, mock_authorize, mock_auth_default, mock_get_bq_client):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), None)
        mock_gc = MagicMock()
        mock_authorize.return_value = mock_gc
        mock_sh = MagicMock()
        mock_gc.open_by_url.return_value = mock_sh
        mock_ws = MagicMock()
        mock_sh.worksheet.return_value = mock_ws
        
        mock_ws.get_all_values.return_value = [
            ['properties', 'title', 'description'],
            ['{"color": "red"}', 'Red Title', 'Red Desc']
        ]
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_job = MagicMock()
        mock_bq.load_table_from_json.return_value = mock_job
        
        # Act
        count = load_examples_from_sheet("test-proj", "test_ds", "https://docs.google.com/...", "Sheet1", "", True)
        
        # Assert
        assert count == 1
        mock_bq.load_table_from_json.assert_called_once()

    @patch('services.examples_service.get_bq_client')
    def test_load_examples_by_ids(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = {'id': '1'}
        mock_bq.query.return_value.result.return_value = [mock_row]
        
        # Act
        count, missing = load_examples_by_ids("test-proj", "test_ds", "SourceTable", "1,2")
        
        # Assert
        assert count == 1
        assert '2' in missing
        assert mock_bq.query.call_count == 2 # One for verify, one for create

    @patch('services.examples_service.get_bq_client')
    def test_clear_examples(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        # Act
        clear_examples("test-proj", "test_ds")
        
        # Assert
        mock_bq.delete_table.assert_called_once()

    @patch('services.examples_service.get_bq_client')
    def test_get_examples_preview_exception(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_bq.query.side_effect = Exception("BQ Error")
        
        # Act
        count, preview = get_examples_preview("test-proj", "test_ds")
        
        # Assert
        assert count == 0
        assert preview == []

    @patch('services.examples_service.get_bq_client')
    @patch('google.auth.default')
    @patch('gspread.authorize')
    def test_load_examples_from_sheet_no_header(self, mock_authorize, mock_auth_default, mock_get_bq_client):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), None)
        mock_gc = MagicMock()
        mock_authorize.return_value = mock_gc
        mock_sh = MagicMock()
        mock_gc.open_by_url.return_value = mock_sh
        mock_ws = MagicMock()
        mock_sh.worksheet.return_value = mock_ws
        
        mock_ws.get_all_values.return_value = [
            ['{"color": "red"}', 'Red Title', 'Red Desc']
        ]
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_job = MagicMock()
        mock_bq.load_table_from_json.return_value = mock_job
        
        # Act
        count = load_examples_from_sheet("test-proj", "test_ds", "https://docs.google.com/...", "Sheet1", "", False)
        
        # Assert
        assert count == 1
        mock_bq.load_table_from_json.assert_called_once()

    @patch('services.examples_service.get_bq_client')
    @patch('google.auth.default')
    @patch('gspread.authorize')
    def test_load_examples_from_sheet_invalid_json(self, mock_authorize, mock_auth_default, mock_get_bq_client):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), None)
        mock_gc = MagicMock()
        mock_authorize.return_value = mock_gc
        mock_sh = MagicMock()
        mock_gc.open_by_url.return_value = mock_sh
        mock_ws = MagicMock()
        mock_sh.worksheet.return_value = mock_ws
        
        mock_ws.get_all_values.return_value = [
            ['properties', 'title', 'description'],
            ['invalid json', 'Title', 'Desc'],
            ['{"color": "red"}', 'Red Title', 'Red Desc']
        ]
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_job = MagicMock()
        mock_bq.load_table_from_json.return_value = mock_job
        
        # Act
        count = load_examples_from_sheet("test-proj", "test_ds", "https://docs.google.com/...", "Sheet1", "", True)
        
        # Assert
        assert count == 1
        mock_bq.load_table_from_json.assert_called_once()

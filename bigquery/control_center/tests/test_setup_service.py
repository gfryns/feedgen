import pytest
from unittest.mock import patch, MagicMock
from services.setup_service import create_dataset

class TestSetupService:
    
    @patch('services.setup_service.get_bq_client')
    @patch('services.setup_service.bigquery.Dataset')
    def test_deploy_dataset(self, mock_dataset_class, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
            
        # Act
        create_dataset(
            project_val="test-proj",
            dataset_val="test_ds",
            region_val="EU",
            log_cb=mock_log
        )
        
        # Assert
        mock_dataset_class.assert_called_with("test-proj.test_ds")
        mock_bq.create_dataset.assert_called_once()
        assert any("Dataset created" in msg for msg in log_msgs)

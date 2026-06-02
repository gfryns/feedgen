import pytest
from unittest.mock import patch, MagicMock
from services.setup_service import create_dataset, create_bucket

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

    @patch('services.setup_service.storage.Client')
    def test_create_bucket(self, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        
        # Mock bucket does not exist initially
        mock_client.get_bucket.side_effect = Exception("Not found")
        
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
            
        # Act
        create_bucket("test-proj", "test-bucket", "EU", log_cb=mock_log)
        
        # Assert
        mock_bucket.add_lifecycle_delete_rule.assert_called_once_with(age=15)
        mock_client.create_bucket.assert_called_once_with(mock_bucket, location="EU")
        assert any("Bucket created" in msg for msg in log_msgs)

    @patch('services.setup_service.storage.Client')
    def test_create_bucket_already_exists(self, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
            
        # Act
        create_bucket("test-proj", "test-bucket", "EU", log_cb=mock_log)
        
        # Assert
        mock_bucket.add_lifecycle_delete_rule.assert_not_called()
        mock_client.create_bucket.assert_not_called()
        assert any("already exists" in msg for msg in log_msgs)

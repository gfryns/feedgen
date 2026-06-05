import pytest
from unittest.mock import patch, MagicMock
from services.setup_service import create_dataset, create_bucket, create_connection

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

    @patch('services.setup_service.google.auth.default')
    @patch('google.cloud.bigquery_connection_v1.ConnectionServiceClient')
    @patch('google.cloud.resourcemanager_v3.ProjectsClient')
    @patch('google.cloud.storage.Client')
    def test_create_connection(self, mock_storage_client, mock_rm_client, mock_conn_client, mock_auth_default):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), "test-proj")
        
        # Connection Client Mocks
        mock_conn = MagicMock()
        mock_conn_client.return_value = mock_conn
        mock_conn.get_connection.side_effect = Exception("Not found") # simulate connection doesn't exist
        
        created_conn = MagicMock()
        created_conn.cloud_resource.service_account_id = "sa-123@gcp-sa.com"
        mock_conn.create_connection.return_value = created_conn
        
        # Resource Manager Mocks
        mock_rm = MagicMock()
        mock_rm_client.return_value = mock_rm
        
        from google.iam.v1.policy_pb2 import Policy
        mock_policy = Policy()
        mock_rm.get_iam_policy.return_value = mock_policy
        
        # Storage Client Mocks
        mock_store = MagicMock()
        mock_storage_client.return_value = mock_store
        mock_bucket = MagicMock()
        mock_store.bucket.return_value = mock_bucket
        
        mock_bucket_policy = MagicMock()
        mock_bucket_policy.bindings = []
        mock_bucket.get_iam_policy.return_value = mock_bucket_policy
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
            
        # Act
        create_connection(
            project_val="test-proj",
            connection_id="test-connection",
            region_val="US",
            bucket_name="test-bucket",
            log_cb=mock_log
        )
        
        # Assert
        mock_conn.create_connection.assert_called_once()
        mock_rm.get_iam_policy.assert_called_once_with(resource="projects/test-proj")
        mock_rm.set_iam_policy.assert_called_once()
        
        mock_store.bucket.assert_called_once_with("test-bucket")
        mock_bucket.get_iam_policy.assert_called_once()
        mock_bucket.set_iam_policy.assert_called_once_with(mock_bucket_policy)
        
        assert any("Connection created successfully" in msg for msg in log_msgs)
        assert any("Project IAM policy updated" in msg for msg in log_msgs)
        assert any("Bucket IAM policy updated" in msg for msg in log_msgs)


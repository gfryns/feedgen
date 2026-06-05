import pytest
from unittest.mock import patch, MagicMock
from services.project_service import enable_apis

class TestProjectService:
    @patch('services.project_service.google.auth.default')
    @patch('services.project_service.service_usage_v1.ServiceUsageClient')
    def test_enable_apis(self, mock_client_class, mock_auth_default):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), "test-project-123")
        
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_operation = MagicMock()
        mock_client.batch_enable_services.return_value = mock_operation
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        enable_apis("test-project-123", log_cb=mock_log)

        # Assert
        mock_client_class.assert_called_once()
        mock_client.batch_enable_services.assert_called_once()
        
        call_args = mock_client.batch_enable_services.call_args[1]['request']
        assert call_args.parent == "projects/test-project-123"
        assert set(call_args.service_ids) == {
            "serviceusage.googleapis.com",
            "aiplatform.googleapis.com",
            "bigquery.googleapis.com",
            "bigqueryconnection.googleapis.com",
            "cloudresourcemanager.googleapis.com"
        }
        
        mock_operation.result.assert_called_once()
            
        # Check logging
        assert any("test-project-123" in msg for msg in log_msgs)
        assert any("Done" in msg for msg in log_msgs)

    @patch('services.project_service.google.auth.default')
    @patch('services.project_service.service_usage_v1.ServiceUsageClient')
    def test_enable_apis_failure(self, mock_client_class, mock_auth_default):
        # Arrange
        mock_auth_default.return_value = (MagicMock(), "test-project-123")
        
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.batch_enable_services.side_effect = Exception("API Error")

        # Act & Assert
        with pytest.raises(Exception, match="Failed to enable APIs: API Error"):
            enable_apis("test-project-123")

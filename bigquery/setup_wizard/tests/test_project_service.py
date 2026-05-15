import pytest
from unittest.mock import patch, MagicMock
from services.project_service import enable_vertex_ai

class TestProjectService:
    @patch('services.project_service.service_usage_v1.ServiceUsageClient')
    def test_enable_vertex_ai(self, mock_client_class):
        # Arrange
        mock_client = MagicMock()
        mock_operation = MagicMock()
        mock_client.enable_service.return_value = mock_operation
        mock_client_class.return_value = mock_client
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        enable_vertex_ai("test-project-123", log_cb=mock_log)

        # Assert
        mock_client_class.assert_called_once()
        mock_client.enable_service.assert_called_once()
        
        # Check args passed to enable_service
        call_args = mock_client.enable_service.call_args[1]
        request = call_args['request']
        assert request.name == "projects/test-project-123/services/aiplatform.googleapis.com"
        
        # Ensure it waited for completion
        mock_operation.result.assert_called_once()
        
        # Check logging
        assert any("test-project-123" in msg for msg in log_msgs)
        assert any("Done" in msg for msg in log_msgs)

    @patch('services.project_service.service_usage_v1.ServiceUsageClient', autospec=True)
    def test_enable_vertex_ai_failure(self, mock_client_class):
        # Arrange
        mock_client = MagicMock()
        mock_client.enable_service.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        # Act & Assert
        with pytest.raises(Exception, match="API Error"):
            enable_vertex_ai("test-project-123")

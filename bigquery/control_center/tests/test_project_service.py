import pytest
from unittest.mock import patch, MagicMock
from services.project_service import enable_apis
import subprocess

class TestProjectService:
    @patch('services.project_service.subprocess.run')
    def test_enable_apis(self, mock_run):
        # Arrange
        mock_response = MagicMock()
        mock_response.stdout = "Success"
        mock_response.stderr = ""
        mock_run.return_value = mock_response
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        enable_apis("test-project-123", log_cb=mock_log)

        # Assert
        assert mock_run.call_count == 4
        
        # Check that all APIs were called
        calls = mock_run.call_args_list
        expected_apis = [
            "serviceusage.googleapis.com",
            "aiplatform.googleapis.com",
            "bigquery.googleapis.com",
            "bigqueryconnection.googleapis.com"
        ]
        
        for i, api in enumerate(expected_apis):
            args = calls[i][0][0]
            assert args[3] == api
            assert args[5] == "test-project-123"
            
        # Check logging
        assert any("test-project-123" in msg for msg in log_msgs)
        assert any("Done" in msg for msg in log_msgs)

    @patch('services.project_service.subprocess.run')
    def test_enable_apis_failure(self, mock_run):
        # Arrange
        mock_run.side_effect = subprocess.CalledProcessError(1, "gcloud", stderr="API Error")

        # Act & Assert
        with pytest.raises(Exception, match="Failed to enable"):
            enable_apis("test-project-123")

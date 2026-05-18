import pytest
from unittest.mock import patch, MagicMock, mock_open
from services.dataset_service import deploy_dataset_and_model

class TestDatasetService:
    @patch('services.dataset_service.bq_connection.CreateConnectionRequest', autospec=True)
    @patch('services.dataset_service.get_bq_client', autospec=True)
    @patch('services.dataset_service.bigquery.Dataset', autospec=True)
    @patch('services.dataset_service.bq_connection.ConnectionServiceClient', autospec=True)
    @patch('services.dataset_service.resourcemanager_v3.ProjectsClient', autospec=True)
    @patch('google.iam.v1.iam_policy_pb2.SetIamPolicyRequest', autospec=True)
    @patch('builtins.open', new_callable=mock_open, read_data="mocked content")
    def test_deploy_dataset_and_model(self, mock_file, mock_set_iam_req, mock_rm_client_class, mock_conn_client_class, mock_dataset_class, mock_get_bq_client, mock_create_request):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_conn_client = MagicMock()
        mock_conn_client_class.return_value = mock_conn_client
        mock_conn_client.common_location_path.return_value = "projects/test-proj/locations/EU"
        
        mock_connection = MagicMock()
        mock_connection.cloud_resource.service_account_id = "test@gcp-sa.iam.gserviceaccount.com"
        mock_conn_client.create_connection.return_value = mock_connection
        
        mock_rm_client = MagicMock()
        mock_rm_client_class.return_value = mock_rm_client
        mock_policy = MagicMock()
        mock_policy.bindings = []
        mock_rm_client.get_iam_policy.return_value = mock_policy
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)
            
        # Act
        deploy_dataset_and_model(
            project_val="test-proj",
            dataset_val="test_ds",
            region_val="EU",
            connection_val="test_conn",
            model_val="gemini-test",
            log_cb=mock_log
        )
        
        # Assert Dataset Creation
        mock_dataset_class.assert_called_with("test-proj.test_ds")
        mock_bq.create_dataset.assert_called_once()
        
        # Assert Connection Creation
        mock_conn_client.create_connection.assert_called_once()
        
        # Assert IAM Binding
        mock_rm_client.get_iam_policy.assert_called_with(resource="projects/test-proj")
        assert len(mock_policy.bindings) == 1
        assert mock_policy.bindings[0].role == "roles/aiplatform.user"
        assert "serviceAccount:test@gcp-sa.iam.gserviceaccount.com" in mock_policy.bindings[0].members
        
        # Verify request construction and call
        mock_set_iam_req.assert_called_once_with(resource="projects/test-proj", policy=mock_policy)
        mock_rm_client.set_iam_policy.assert_called_once_with(request=mock_set_iam_req.return_value)
        
        # Assert Model & Procedures Creation
        assert mock_bq.query.call_count == 2 # One for model, one for procedures
        model_query = mock_bq.query.call_args_list[0][0][0]
        assert "CREATE OR REPLACE MODEL `test-proj.test_ds.GeminiModel`" in model_query
        assert "endpoint = 'gemini-test'" in model_query
        
        # Verify files were opened
        assert mock_file.call_count == 3 # generation.sql, titles.txt, descriptions.txt

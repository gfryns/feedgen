import pytest
from unittest.mock import patch, MagicMock, mock_open
from services.generation_service import run_generation_process
import json

class TestGenerationService:
    
    @patch('services.generation_service.update_ongoing_state')
    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data='{"instance": {"id": "123"}, "prediction": {"candidates": [{"content": {"parts": [{"text": "mock title"}]}}]}}')
    @patch('services.generation_service.aiplatform.BatchPredictionJob')
    @patch('services.generation_service.storage.Client')
    @patch('services.generation_service.time.sleep')
    def test_run_generation_process(self, mock_sleep, mock_storage_client_class, mock_batch_prediction_job_class, mock_file_open, mock_get_bq_client, mock_update_state):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_bq.get_table.return_value.schema = [MagicMock(name='id'), MagicMock(name='title')]
        mock_bq.get_table.return_value.schema[0].name = 'id'
        mock_bq.get_table.return_value.schema[1].name = 'title'

        # Mock BQ results for input data
        mock_row = MagicMock()
        mock_row.id = "123"
        mock_row.image_url = "gs://bucket/image.jpg"
        mock_row.webpage_content = "content"
        mock_bq.query.return_value.result.side_effect = [
            MagicMock(), # create InputProcessing table
            MagicMock(), # ensure Output table exists
            MagicMock(), # truncate Output table
            [mock_row], # fetch data for prompt construction
            [], # fetch examples
            MagicMock(), # merge results
            MagicMock() # drop temp table
        ]

        # Mock Storage
        mock_storage_client = MagicMock()
        mock_storage_client_class.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_storage_client.get_bucket.return_value = mock_bucket
        
        # Mock list_blobs
        mock_blob = MagicMock()
        mock_blob.name = "output/part-00000.jsonl"
        mock_blob.download_as_text.return_value = '{"id": "123", "prediction": "{\\"candidates\\": [{\\"content\\": {\\"parts\\": [{\\"text\\": \\"mock title\\"}]}}]}"}'
        mock_bucket.list_blobs.return_value = [mock_blob]

        # Mock BatchPredictionJob
        mock_job = MagicMock()
        mock_job.has_ended = True
        from google.cloud.aiplatform.gapic import JobState
        mock_job.state = JobState.JOB_STATE_SUCCEEDED
        mock_job.to_dict.return_value = {
            'completionStats': {
                'successfulCount': '1',
                'failedCount': '0'
            }
        }
        mock_batch_prediction_job_class.create.return_value = mock_job
        mock_batch_prediction_job_class.return_value = mock_job

        # Mock BQ load job
        mock_load_job = MagicMock()
        mock_bq.load_table_from_json.return_value = mock_load_job

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", "OutputTable",
            True, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True
        assert result['total_rows'] == 1
        mock_batch_prediction_job_class.create.assert_called_once()
        mock_bq.load_table_from_json.assert_called_once()
        mock_blob.download_as_text.assert_called_once()

    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data="mock content")
    def test_run_generation_no_targets(self, mock_file_open, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_bq.get_table.return_value.schema = []

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", "OutputTable",
            False, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True
        assert 'message' in result


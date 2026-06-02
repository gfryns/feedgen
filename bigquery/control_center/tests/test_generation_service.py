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
    def test_run_generation_process(self, mock_sleep, mock_storage_client_class, mock_batch_prediction_job_class, mock_file_open, mock_get_bq_client, mock_update_state, tmp_path):
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
            "id", "title", "description", "image_url",
            state_path=str(tmp_path / "state.json")
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

    def test_update_ongoing_state(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text('{"project": "test"}')
        
        from services.generation_service import update_ongoing_state
        
        # Test update
        update_ongoing_state(job_ids={"Titles": "job1"}, state_path=str(state_file))
        
        import json
        content = json.loads(state_file.read_text())
        assert content['ongoing_generation']['job_ids']['Titles'] == "job1"
        
        # Test clear
        update_ongoing_state(clear=True, state_path=str(state_file))
        content = json.loads(state_file.read_text())
        assert 'ongoing_generation' not in content

    @patch('services.generation_service.aiplatform.BatchPredictionJob')
    def test_wait_for_jobs_and_get_prefixes(self, mock_job_class):
        from services.generation_service import wait_for_jobs_and_get_prefixes
        from unittest.mock import MagicMock
        
        from google.cloud.aiplatform.gapic import JobState
        mock_job = MagicMock()
        mock_job_class.return_value = mock_job
        mock_job.resource_name = "projects/test/locations/us/batchPredictionJobs/123"
        mock_job.state = JobState.JOB_STATE_SUCCEEDED
        mock_job.to_dict.return_value = {'outputInfo': {'gcsOutputDirectory': 'gs://bucket/output/path'}}
        
        jobs = {"Titles": mock_job}
        
        result = wait_for_jobs_and_get_prefixes(jobs, "bucket", print, None, lambda: False, 10)
        
        assert result['Titles'] == "output/path/"

    @patch('services.generation_service.wait_for_jobs_and_get_prefixes')
    @patch('services.generation_service.load_and_merge_results')
    @patch('services.generation_service.aiplatform.init')
    @patch('services.generation_service.aiplatform.BatchPredictionJob')
    def test_resume_generation_process(self, mock_job_class, mock_init, mock_merge, mock_wait, tmp_path):
        from services.generation_service import resume_generation_process
        from unittest.mock import MagicMock
        
        mock_job = MagicMock()
        mock_job_class.return_value = mock_job
        
        mock_wait.return_value = {"Titles": "output/path/"}
        
        job_ids = {"Titles": "projects/test/locations/global/batchPredictionJobs/123"}
        
        state_file = tmp_path / "state.json"
        state_file.write_text('{"project": "test", "ongoing_generation": {"total_rows": 5}}')
        
        result = resume_generation_process(
            "test-proj", "test_ds", "test-bucket", "OutputTable",
            job_ids, print, None, lambda: False,
            state_path=str(state_file)
        )
        
        assert result['success'] == True
        assert result['total_rows'] == 5

    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.storage.Client')
    @patch('services.generation_service.aiplatform.init')
    @patch('services.generation_service.aiplatform.BatchPredictionJob')
    def test_run_generation_claude(self, mock_job_class, mock_init, mock_storage_client_class, mock_get_bq_client, tmp_path):
        from services.generation_service import run_generation_process
        from unittest.mock import MagicMock
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        # Mock rows
        mock_row = MagicMock()
        mock_row.id = "123"
        mock_row.properties = "{}"
        mock_bq.query.return_value.result.side_effect = [
            MagicMock(), # create InputProcessing table
            MagicMock(), # ensure Output table exists
            MagicMock(), # truncate Output table
            [mock_row], # fetch data for prompt construction
            [], # fetch examples
            MagicMock(), # merge results
            MagicMock() # drop temp table
        ]
        
        # Mock storage
        mock_storage = MagicMock()
        mock_storage_client_class.return_value = mock_storage
        mock_bucket = MagicMock()
        mock_storage.get_bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        
        # Mock job
        from google.cloud.aiplatform.gapic import JobState
        mock_job = MagicMock()
        mock_job.state = JobState.JOB_STATE_SUCCEEDED
        mock_job_class.create.return_value = mock_job
        mock_job_class.return_value = mock_job
        
        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", "OutputTable",
            True, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url",
            model_val="claude-3-5-haiku", # Trigger Claude branch!
            state_path=str(tmp_path / "state.json")
        )
        
        # Assert
        assert result['success'] == True
        
        # Verify upload_from_string was called with Claude format!
        mock_blob.upload_from_string.assert_called_once()
        call_args = mock_blob.upload_from_string.call_args[0][0]
        assert '"custom_id": "123"' in call_args
        assert '"messages":' in call_args

    @patch('services.generation_service.aiplatform.BatchPredictionJob')
    def test_wait_for_jobs_and_get_prefixes_failed(self, mock_job_class):
        from services.generation_service import wait_for_jobs_and_get_prefixes
        from unittest.mock import MagicMock
        
        from google.cloud.aiplatform.gapic import JobState
        mock_job = MagicMock()
        mock_job_class.return_value = mock_job
        mock_job.resource_name = "projects/test/locations/us/batchPredictionJobs/123"
        mock_job.state = JobState.JOB_STATE_FAILED
        mock_job.to_dict.return_value = {'error': {'message': 'Job failed'}}
        
        jobs = {"Titles": mock_job}
        
        result = wait_for_jobs_and_get_prefixes(jobs, "bucket", print, None, lambda: False, 10)
        
        assert result['Titles'] == "output/output_titles/"


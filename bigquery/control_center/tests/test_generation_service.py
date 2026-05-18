import pytest
from unittest.mock import patch, MagicMock, mock_open
from services.generation_service import run_generation_process

class TestGenerationService:
    
    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data="mock content")
    @patch('services.generation_service.time.sleep')
    def test_run_generation_process(self, mock_sleep, mock_file_open, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_bq.get_table.return_value.schema = [MagicMock(name='id'), MagicMock(name='title')]
        mock_bq.get_table.return_value.schema[0].name = 'id'
        mock_bq.get_table.return_value.schema[1].name = 'title'

        # Mock job
        mock_job = MagicMock()
        mock_job.done.return_value = True
        mock_job.exception.return_value = None
        mock_bq.query.return_value = mock_job

        # Mock results for result() calls
        mock_count_res = MagicMock()
        mock_count_res.total = 10

        mock_processed_res = MagicMock()
        mock_processed_res.processed = 10

        mock_job.result.side_effect = [
            MagicMock(), # create table
            MagicMock(), # deploy procedures
            MagicMock(), # init output table
            [mock_count_res], # count query
            [mock_processed_res] # processed query
        ]

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", 1, "OutputTable",
            True, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True
        assert result['total_rows'] == 10
        mock_bq.query.assert_called()

    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data="mock content")
    def test_run_generation_no_targets(self, mock_file_open, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_bq.get_table.return_value.schema = []

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", 1, "OutputTable",
            False, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True
        assert 'message' in result

    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data="mock content")
    @patch('services.generation_service.time.sleep')
    def test_run_generation_web_not_done(self, mock_sleep, mock_file_open, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_job = MagicMock()
        mock_job.done.return_value = True
        mock_job.exception.return_value = None
        mock_bq.query.return_value = mock_job
        
        mock_count_res = MagicMock()
        mock_count_res.total = 10
        mock_job.result.return_value = [mock_count_res]
        
        mock_bq.get_table.return_value.schema = []

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", 1, "OutputTable",
            True, False, False, "test-bucket", False, False, # web_done = False
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True

    @patch('services.generation_service.get_bq_client')
    @patch('services.generation_service.open', new_callable=mock_open, read_data="mock content")
    @patch('services.generation_service.time.sleep')
    def test_run_generation_rate_limit_retry(self, mock_sleep, mock_file_open, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_job1 = MagicMock()
        mock_job1.done.return_value = True
        mock_job1.exception.return_value = Exception("too many concurrent queries")
        
        mock_job2 = MagicMock()
        mock_job2.done.return_value = True
        mock_job2.exception.return_value = None
        
        mock_count_res = MagicMock()
        mock_count_res.total = 10
        
        mock_processed_res = MagicMock()
        mock_processed_res.processed = 10
        
        # Mock sequence of queries
        mock_bq.query.side_effect = [
            MagicMock(), # create table
            MagicMock(), # deploy procedures
            MagicMock(), # init output table
            MagicMock(result=MagicMock(return_value=[mock_count_res])), # count query
            mock_job1, # first procedure call (fails)
            mock_job2, # second procedure call (retry)
            MagicMock(result=MagicMock(return_value=[mock_processed_res])) # processed query
        ]
        
        mock_bq.get_table.return_value.schema = []

        # Act
        result = run_generation_process(
            "test-proj", "test_ds", "en", 1, "OutputTable",
            True, False, False, "test-bucket", False, True,
            "id", "title", "description", "image_url"
        )        
        # Assert
        assert result['success'] == True

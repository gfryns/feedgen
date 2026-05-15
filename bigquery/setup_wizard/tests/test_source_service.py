import pytest
from unittest.mock import patch, MagicMock
from services.source_service import get_table_info

class TestSourceService:
    @patch('services.source_service.get_bq_client', autospec=True)
    def test_get_table_info_full_ref(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_table = MagicMock()
        mock_table.location = "EU"
        mock_table.num_rows = 100
        
        # Mock Schema
        mock_field_id = MagicMock(); mock_field_id.name = "product_id"
        mock_field_title = MagicMock(); mock_field_title.name = "product_title"
        mock_field_desc = MagicMock(); mock_field_desc.name = "product_desc"
        mock_table.schema = [mock_field_id, mock_field_title, mock_field_desc]
        
        mock_bq.get_table.return_value = mock_table
        
        # Mock Query Result
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [
            {"product_id": "1", "product_title": "T1", "product_desc": "D1"}
        ]
        mock_bq.query.return_value = mock_query_job
        
        # Act
        result = get_table_info(
            project_val="test-proj",
            dataset_val="test_ds",
            raw_table="other-proj.other_ds.MyTable", # Full ref provided
            target_region="EU",
            insecure=False
        )
        
        # Assert
        mock_bq.get_table.assert_called_with("other-proj.other_ds.MyTable")
        
        assert "product_id" in result['cols']
        assert len(result['warnings']) == 0
        assert len(result['preview']) == 1
        assert result['preview'][0] == ("1", "T1", "D1")

    @patch('services.source_service.get_bq_client')
    def test_get_table_info_warning(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_table = MagicMock()
        mock_table.location = "US" # Mismatched region
        mock_table.num_rows = 0
        mock_table.schema = []
        mock_bq.get_table.return_value = mock_table
        
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_bq.query.return_value = mock_query_job

        # Act
        result = get_table_info(
            project_val="test-proj",
            dataset_val="test_ds",
            raw_table="MyTable", # Short name
            target_region="EU",
            insecure=False
        )
        
        # Assert
        mock_bq.get_table.assert_called_with("test-proj.test_ds.MyTable")
        assert len(result['warnings']) == 1
        assert "US" in result['warnings'][0]

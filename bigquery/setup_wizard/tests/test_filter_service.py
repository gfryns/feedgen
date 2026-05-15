import pytest
from unittest.mock import patch, MagicMock
from services.filter_service import create_filtered_table

class TestFilterService:
    @patch('services.filter_service.get_bq_client', autospec=True)
    def test_create_filtered_table_all_cols(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        create_filtered_table(
            project_val="p",
            dataset_val="d",
            raw_table="Raw",
            id_col="c1",
            title_col="c2",
            desc_col="c3",
            url_col="c4",
            image_col="c5",
            include_cols="*",
            filters="WHERE x=1",
            insecure=False,
            log_cb=mock_log
        )
        
        # Assert
        mock_bq.query.assert_called_once()
        sql = mock_bq.query.call_args[0][0]
        
        assert "CREATE OR REPLACE TABLE `p.d.InputFiltered`" in sql
        assert "SELECT *" in sql
        assert "FROM `p.d.Raw`" in sql
        assert "WHERE x=1" in sql

    @patch('services.filter_service.get_bq_client')
    def test_create_filtered_table_specific_cols(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq

        # Act
        create_filtered_table(
            project_val="p",
            dataset_val="d",
            raw_table="other.dataset.Raw",
            id_col="c1",
            title_col="c2",
            desc_col="c3",
            url_col="skip", # skipped
            image_col="c5",
            include_cols="brand, price",
            filters="",
            insecure=False
        )
        
        # Assert
        sql = mock_bq.query.call_args[0][0]
        
        assert "CREATE OR REPLACE TABLE `p.d.InputFiltered`" in sql
        assert "c1 as id" in sql
        assert "c2 as title" in sql
        assert "c3 as description" in sql
        assert "c4 as url" not in sql # Because skip
        assert "c5 as image_url" in sql
        assert "brand" in sql
        assert "price" in sql
        assert "FROM `other`.`dataset`.`Raw`" in sql

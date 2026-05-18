import pytest
from unittest.mock import patch, MagicMock
from services.export_service import export_to_gmc

class TestExportService:
    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_supplemental(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        export_to_gmc(
            project_val="p",
            dataset_val="d",
            raw_table="Raw",
            output_table="Out",
            export_table="Exp",
            feed_type="supplemental",
            log_cb=mock_log
        )
        
        # Assert
        assert mock_bq.query.call_count == 2
        
        # Check UDF creation
        udf_sql = mock_bq.query.call_args_list[0][0][0]
        assert "CREATE OR REPLACE FUNCTION `p.d.EmbedForMerchantFeed`" in udf_sql
        
        # Check Supplemental SQL
        export_sql = mock_bq.query.call_args_list[1][0][0]
        assert "CREATE OR REPLACE TABLE `p.d.Exp`" in export_sql
        assert "`p.d.EmbedForMerchantFeed`(title, TRUE) AS structured_title" in export_sql
        assert "FROM `p.d.Out`" in export_sql
        assert "WHERE title IS NOT NULL OR description IS NOT NULL" in export_sql

    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_full(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        log_msgs = []
        def mock_log(msg):
            log_msgs.append(msg)

        # Act
        export_to_gmc(
            project_val="p",
            dataset_val="d",
            raw_table="other.ds.Raw",
            output_table="Out",
            export_table="Exp",
            feed_type="full",
            log_cb=mock_log
        )
        
        # Assert
        assert mock_bq.query.call_count == 2
        
        # Check Full Feed SQL
        export_sql = mock_bq.query.call_args_list[1][0][0]
        assert "CREATE OR REPLACE TABLE `p.d.Exp`" in export_sql
        assert "I.* EXCEPT (title, description)" in export_sql
        assert "`p.d.EmbedForMerchantFeed`(COALESCE(O.title, I.title), O.title IS NOT NULL) AS structured_title" in export_sql
        assert "FROM `other`.`ds`.`Raw` AS I" in export_sql
        assert "LEFT JOIN `p.d.Out` AS O USING (id)" in export_sql

    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_full_with_short_raw_table(self, mock_get_bq_client):
        mock_get_bq_client.return_value = MagicMock()
        export_to_gmc(
            project_val="p",
            dataset_val="d",
            raw_table="RawShort", # Hits the 'else' branch for raw_table
            output_table="Out",
            export_table="Exp",
            feed_type="full",
            log_cb=lambda msg: None
        )
        # Verify the raw_table reference was constructed properly
        export_sql = mock_get_bq_client.return_value.query.call_args_list[1][0][0]
        assert "FROM `p.d.RawShort` AS I" in export_sql

    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_invalid_feed_type(self, mock_get_bq_client):
        mock_get_bq_client.return_value = MagicMock()
        with pytest.raises(ValueError, match="Unknown feed type: invalid_type"):
            export_to_gmc(
                project_val="p",
                dataset_val="d",
                raw_table="Raw",
                output_table="Out",
                export_table="Exp",
                feed_type="invalid_type", # Hits the exception branch
                log_cb=lambda msg: None
            )

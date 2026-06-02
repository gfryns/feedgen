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
        assert "SELECT" in export_sql
        assert "`p.d.EmbedForMerchantFeed`(title, TRUE) AS structured_title" in export_sql
        assert "FROM `p.d.Raw`" in export_sql
        assert "WHERE title IS NOT NULL OR description IS NOT NULL OR highlights IS NOT NULL" in export_sql

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
        assert "SELECT" in export_sql
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
    @patch('services.export_service.storage.Client')
    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_to_gcs(self, mock_get_bq_client, mock_storage_client):
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = MagicMock()
        mock_row.values.return_value = ["1", "Title"]
        mock_field = MagicMock()
        mock_field.name = "id"
        
        mock_rows = MagicMock()
        mock_rows.schema = [mock_field]
        mock_rows.__iter__.return_value = [mock_row]
        mock_bq.query.return_value.result.return_value = mock_rows
        
        mock_storage = MagicMock()
        mock_storage_client.return_value = mock_storage
        mock_bucket = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        
        export_to_gmc("p", "d", "Raw", "Out", "Exp", "supplemental", "gcs", "my-bucket", "test.csv", log_cb=lambda msg: None)
        
        mock_storage.bucket.assert_called_once_with("my-bucket")
        mock_bucket.blob.assert_called_once_with("test.csv")
        mock_blob.upload_from_string.assert_called_once()

    @patch('services.export_service.gspread.oauth')
    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_to_sheets(self, mock_get_bq_client, mock_gspread_oauth):
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = MagicMock()
        mock_row.values.return_value = ["1", "Title"]
        mock_field = MagicMock()
        mock_field.name = "id"
        
        mock_rows = MagicMock()
        mock_rows.schema = [mock_field]
        mock_rows.__iter__.return_value = [mock_row]
        mock_bq.query.return_value.result.return_value = mock_rows
        
        mock_gc = MagicMock()
        mock_gspread_oauth.return_value = mock_gc
        mock_sh = MagicMock()
        mock_gc.open_by_key.return_value = mock_sh
        mock_ws = MagicMock()
        mock_sh.worksheets.return_value = [mock_ws]
        mock_ws.title = "Sheet1"
        mock_sh.worksheet.return_value = mock_ws
        
        export_to_gmc("p", "d", "Raw", "Out", "Exp", "supplemental", "sheets", "sheet_id", "test.csv", "Sheet1", log_cb=lambda msg: None)
        
        mock_gc.open_by_key.assert_called_once_with("sheet_id")
        mock_ws.clear.assert_called_once()
        mock_ws.update.assert_called_once()

    @patch('services.export_service.get_bq_client', autospec=True)
    def test_export_selective_columns(self, mock_get_bq_client):
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        export_to_gmc("p", "d", "Raw", "Out", "Exp", "supplemental", log_cb=lambda msg: None, export_title=False, export_desc=True, export_highlights=False)
        
        export_sql = mock_bq.query.call_args_list[1][0][0]
        assert "structured_title" not in export_sql
        assert "structured_description" in export_sql
        assert "product_highlight" not in export_sql

import pytest
from unittest.mock import patch, MagicMock
from services.images_service import get_bucket_stats, create_bucket, delete_images, run_image_processing

class TestImagesService:
    
    @patch('services.images_service.storage.Client')
    def test_get_bucket_stats(self, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        mock_blob1 = MagicMock(); mock_blob1.size = 100
        mock_blob2 = MagicMock(); mock_blob2.size = 200
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        
        # Act
        count, size = get_bucket_stats("test-proj", "test-bucket")
        
        # Assert
        assert count == 2
        assert size == 300
        mock_client.get_bucket.assert_called_once_with("test-bucket")

    @patch('services.images_service.storage.Client')
    def test_create_bucket(self, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        
        # Act
        create_bucket("test-proj", "test-bucket", "EU")
        
        # Assert
        mock_client.create_bucket.assert_called_once_with("test-bucket", location="EU")

    @patch('services.images_service.storage.Client')
    @patch('services.images_service.get_bq_client')
    def test_delete_images(self, mock_get_bq_client, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        mock_blob = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        # Act
        count = delete_images("test-proj", "test_ds", "test-bucket")
        
        # Assert
        assert count == 1
        mock_blob.delete.assert_called_once()
        mock_bq.query.assert_called_once() # Drops table

    @patch('services.images_service.storage.Client')
    @patch('services.images_service.get_bq_client')
    @patch('services.images_service.requests.get')
    @patch('services.images_service.certifi.where')
    def test_run_image_processing(self, mock_certifi, mock_get, mock_get_bq_client, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        mock_bucket.list_blobs.return_value = [] # No existing blobs
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = {'image_url': 'https://example.com/img1.jpg'}
        mock_bq.query.return_value.result.return_value = [mock_row]
        mock_bq.get_table.return_value.schema = []
        
        # Mock requests
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'image/jpeg'}
        mock_resp.raw = MagicMock()
        mock_get.return_value = mock_resp
        
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        
        # Act
        result = run_image_processing("test-proj", "test_ds", "test-bucket", "conn", "EU", "image_url")
        
        # Assert
        assert result['total'] == 1
        assert result['success'] == 1
        mock_blob.upload_from_file.assert_called_once()
        assert mock_bq.query.call_count == 2 # One for fetch, one for create external table

    @patch('services.images_service.storage.Client')
    def test_get_bucket_stats_exception(self, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_client.get_bucket.side_effect = Exception("GCS Error")
        
        # Act
        count, size = get_bucket_stats("test-proj", "test-bucket")
        
        # Assert
        assert count is None
        assert size is None

    @patch('services.images_service.storage.Client')
    @patch('services.images_service.get_bq_client')
    def test_delete_images_cancelled(self, mock_get_bq_client, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        mock_blob = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        
        # Act
        count = delete_images("test-proj", "test_ds", "test-bucket", is_cancelled=lambda: True)
        
        # Assert
        assert count == 0
        mock_blob.delete.assert_not_called()

    @patch('services.images_service.storage.Client')
    @patch('services.images_service.get_bq_client')
    def test_delete_images_not_found(self, mock_get_bq_client, mock_storage_client):
        # Arrange
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        
        mock_blob = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        
        from google.api_core.exceptions import NotFound
        mock_blob.delete.side_effect = NotFound("Not found")
        
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        # Act
        count = delete_images("test-proj", "test_ds", "test-bucket")
        
        # Assert
        assert count == 0

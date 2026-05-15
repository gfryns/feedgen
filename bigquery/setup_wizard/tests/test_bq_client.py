import pytest
from unittest.mock import patch, MagicMock

from services.bq_client import get_bq_client

class TestBQClient:
    @patch('services.bq_client.bigquery.Client', autospec=True)
    @patch('services.bq_client.os.environ', autospec=True)
    @patch('services.bq_client.ssl._create_unverified_context', autospec=True)
    def test_get_bq_client_secure(self, mock_unverified, mock_environ, mock_bq_client):
        # Act
        client = get_bq_client('test-project')

        # Assert
        mock_bq_client.assert_called_once_with(project='test-project')
        mock_environ.__setitem__.assert_not_called()
        mock_unverified.assert_not_called()

    @patch('services.bq_client.bigquery.Client', autospec=True)
    @patch('services.bq_client.os.environ', new_callable=dict)
    @patch('services.bq_client.ssl', autospec=True)
    def test_get_bq_client_insecure(self, mock_ssl, mock_environ, mock_bq_client):
        # Arrange
        mock_unverified_context = MagicMock()
        mock_ssl._create_unverified_context.return_value = mock_unverified_context
        
        # Act
        client = get_bq_client('test-project', insecure=True)

        # Assert
        assert mock_environ['PYTHONHTTPSVERIFY'] == '0'
        assert mock_ssl._create_default_https_context == mock_ssl._create_unverified_context
        mock_bq_client.assert_called_once_with(project='test-project')

import pytest
from unittest.mock import patch

from services.bq_client import get_bq_client

class TestBQClient:
    @patch('services.bq_client.bigquery.Client', autospec=True)
    def test_get_bq_client(self, mock_bq_client):
        # Act
        get_bq_client('test-project')

        # Assert
        mock_bq_client.assert_called_once_with(project='test-project')


import pytest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from services.scraping_service import detect_css_selector, run_web_scraping

class TestScrapingService:
    
    @pytest.mark.asyncio
    @patch('services.scraping_service.get_bq_client')
    @patch('services.scraping_service.aiplatform.init')
    @patch('services.scraping_service.GenerativeModel')
    @patch('aiohttp.ClientSession.get')
    async def test_detect_css_selector(self, mock_get, mock_gen_model, mock_ai_init, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = MagicMock()
        mock_row.__getitem__.return_value = "https://example.com/p1"
        mock_bq.query.return_value.result.return_value = [mock_row]
        
        # Mock aiohttp response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text.return_value = "<html><body><div class='desc'>Product Description</div></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        # Mock Gemini
        mock_model = MagicMock()
        mock_gen_model.return_value = mock_model
        mock_model.generate_content.return_value.text = ".desc"
        
        # Act
        selector = await detect_css_selector("test-proj", "test_ds", "url", 1)
        
        # Assert
        assert selector == ".desc"
        mock_bq.query.assert_called_once()
        mock_gen_model.assert_called_once_with("gemini-1.5-flash")
        mock_model.generate_content.assert_called_once()

    @pytest.mark.asyncio
    @patch('services.scraping_service.get_bq_client')
    @patch('aiohttp.ClientSession.get')
    @patch('services.scraping_service.bigquery.LoadJobConfig')
    @patch('services.scraping_service.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_run_web_scraping(self, mock_remove, mock_exists, mock_file_open, mock_load_config, mock_get, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = {'id': '1', 'url': 'https://example.com/p1'}
        mock_bq.query.return_value.result.return_value = [mock_row]
        mock_bq.get_table.return_value.schema = []
        
        # Mock aiohttp response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text.return_value = "<html><body><div class='desc'>Product Description</div></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        # Mock BQ Load
        mock_load_job = MagicMock()
        mock_bq.load_table_from_file.return_value = mock_load_job
        
        mock_exists.return_value = True
        
        # Act
        result = await run_web_scraping("test-proj", "test_ds", ".desc", "url")
        
        # Assert
        assert result['total'] == 1
        assert result['success'] == 1
        assert result['extracted'] == 1
        mock_bq.load_table_from_file.assert_called_once()
        mock_remove.assert_called_once()

    @pytest.mark.asyncio
    @patch('services.scraping_service.get_bq_client')
    async def test_detect_css_selector_no_urls(self, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        mock_bq.query.return_value.result.return_value = []
        mock_bq.get_table.return_value.schema = []
        
        # Act & Assert
        with pytest.raises(ValueError, match="No URLs found in the url column!"):
            await detect_css_selector("test-proj", "test_ds", "url", 1)

    @pytest.mark.asyncio
    @patch('services.scraping_service.get_bq_client')
    @patch('services.scraping_service.aiplatform.init')
    @patch('services.scraping_service.GenerativeModel')
    @patch('aiohttp.ClientSession.get')
    async def test_detect_css_selector_fetch_error(self, mock_get, mock_gen_model, mock_ai_init, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = MagicMock()
        mock_row.__getitem__.return_value = "https://example.com/p1"
        mock_bq.query.return_value.result.return_value = [mock_row]
        
        # Mock aiohttp response to raise error
        mock_get.side_effect = Exception("Network error")
        
        # Act & Assert
        with pytest.raises(ValueError, match="Failed to fetch any sample pages!"):
            await detect_css_selector("test-proj", "test_ds", "url", 1)

    @pytest.mark.asyncio
    @patch('services.scraping_service.get_bq_client')
    @patch('aiohttp.ClientSession.get')
    async def test_run_web_scraping_cancelled(self, mock_get, mock_get_bq_client):
        # Arrange
        mock_bq = MagicMock()
        mock_get_bq_client.return_value = mock_bq
        
        mock_row = {'id': '1', 'url': 'https://example.com/p1'}
        mock_bq.query.return_value.result.return_value = [mock_row]
        mock_bq.get_table.return_value.schema = []
        
        # Act
        result = await run_web_scraping("test-proj", "test_ds", ".desc", "url", is_cancelled=lambda: True)
        
        # Assert
        assert result.get('cancelled') == True


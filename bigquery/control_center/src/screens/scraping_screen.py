from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar
from textual.containers import Vertical, Horizontal, Container
from textual import on
from services.bq_client import get_bq_client
import asyncio
import csv
import os
import time
import requests
from bs4 import BeautifulSoup

class ScrapingScreen(ControlCenterBaseScreen):
    """Screen for Step 3c: Web Scraping."""
    
    def __init__(self, state):
        super().__init__(state)
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3c: Retrieve Product Page Info", id="title")
            
            url_col = self.state.get('url_col')
            
            if url_col == 'skip' or not url_col:
                yield Static(
                    "There is no product page URL configured in the filtered table.\n"
                    "If you want to enrich data with web scraping, please go back to Step 3b and map the URL column.",
                    id="msg"
                )
                with Horizontal():
                    yield Button("Back to Menu", id="back-btn")
            else:
                with Container(classes="card"):
                    yield Label("Scraping Configuration", id="scraping-title")
                    yield Label(f"Product Page URL Column: {url_col}")
                    
                    yield Label("CSS Selector for description:")
                    with Horizontal(id="selector-row"):
                        yield Input(value=self.state.get('selector', 'div[data-testid^="item-description"]'), id="selector")
                        yield Button("Auto-detect", id="detect-selector-btn")
                
                with Horizontal():
                    yield Button("Run Scraping", variant="success", id="run-btn")
                    yield Button("Back to Menu", id="back-btn")
                    
                yield ProgressBar(id="progress-bar")
                
                with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                    yield Log(id="process-logs")
                    yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
                    
                yield Label("", id="status-label")
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            selector = self.query_one("#selector").value
            self.state.set('selector', selector)
            self.query_one("#logs-collapsible").collapsed = False
            self.query_one("#progress-bar").styles.display = "block"
            self.run_worker(self.run_scraping(selector))
        elif event.button.id == "detect-selector-btn":
            self.run_worker(self.detect_selector)
            

            
    async def detect_selector(self) -> None:
        self.notify("Auto-detecting selector...")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        url_col = self.state.get('url_col')
        
        sample_count = 5 # Default value
        
        if sample_count < 1 or sample_count > 15:
            self.notify("Sample size must be between 1 and 15. Using default of 5.", severity="warning")
            sample_count = 5
            
        if not url_col or url_col == 'skip':
            self.notify("No URL column mapped!", severity="error")
            return
            
        try:
            from services.bq_client import get_bq_client
            client = get_bq_client(project)
            source_table = "InputFiltered"
            
            # Fetch sample URLs
            query = f"SELECT url FROM `{project}.{dataset}.{source_table}` WHERE url IS NOT NULL ORDER BY RAND() LIMIT {sample_count}"
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
            
            if not results:
                self.notify("No URLs found in the table!", severity="error")
                return
                
            if len(results) < sample_count:
                self.notify(f"Requested {sample_count} samples, but only found {len(results)} rows. Using all available.", severity="warning")
                
            urls = [row['url'] for row in results]
            self.notify(f"Fetching {len(urls)} sample pages...")
            
            import aiohttp
            from bs4 import BeautifulSoup
            
            cleaned_htmls = []
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    try:
                        async with session.get(url, headers=headers, timeout=15) as response:
                            response.raise_for_status()
                            html = await response.text()
                            
                            # Clean HTML
                            soup = BeautifulSoup(html, 'html.parser')
                            for script in soup(["script", "style"]):
                                script.decompose()
                            cleaned_htmls.append(str(soup))
                    except Exception as e:
                        self.notify(f"Error fetching {url}: {e}", severity="warning")
                        
            if not cleaned_htmls:
                self.notify("Failed to fetch any sample pages!", severity="error")
                return
                
            self.notify("Calling Gemini to analyze HTML...")
            
            # Call Gemini
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel
            
            aiplatform.init(project=project)
            model = GenerativeModel("gemini-1.5-flash")
            
            # Construct prompt with all HTMLs
            prompt = "You are an expert web scraper. Analyze the following HTML contents of product pages.\n"
            prompt += f"Identify the CSS selector that consistently contains the product description across ALL {len(cleaned_htmls)} pages.\n"
            prompt += "Return ONLY the CSS selector string (e.g., `.product-description` or `#desc`).\n"
            prompt += "Do not include any other text, markdown, or explanation.\n\n"
            
            for i, html_content in enumerate(cleaned_htmls):
                prompt += f"--- Page {i+1} ---\n{html_content[:30000]}\n\n"
                
            def call_gemini():
                response = model.generate_content(prompt)
                return response.text.strip()
                
            selector = await loop.run_in_executor(None, call_gemini)
            
            # Clean up response
            selector = selector.replace('`', '').replace('"', '').replace("'", "").strip()
            
            self.query_one("#selector", Input).value = selector
            self.notify(f"Suggested selector: {selector}", severity="information")
            
        except Exception as e:
            self.notify(f"Error detecting selector: {e}", severity="error")
            
    async def run_scraping(self, selector: str) -> None:
        logs = self.query_one("#process-logs", Log)
        
        def write_log(text):
            logs.write(text)
            self.log_content += text
            
        self.log_content = ""
        write_log("Starting web scraping...\n")
        self.query_one("#status-label", Label).update("[bold]Scraping webpages...[/]")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        url_col = self.state.get('url_col')
        id_col = self.state.get('id_col', 'id')
        
        try:
            client = get_bq_client(self.state.get('project'))
            
            source_table = "InputFiltered"
            dest_table = "InputFilteredWeb"
            
            query = f"SELECT id, url FROM `{project}.{dataset}.{source_table}`"
            self.write_log(f"Fetching URLs with query: {query}\n")
            
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
            
            csv_filename = "ids_contents.csv"
            self.write_log(f"Found {len(results)} rows. Scraping pages...\n")
            
            self.query_one("#progress-bar", ProgressBar).update(total=len(results), progress=0)
            
            import aiohttp
            import csv
            from bs4 import BeautifulSoup
            
            total = len(results)
            success = 0
            extracted = 0
            failed = 0
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            semaphore = asyncio.Semaphore(20) # Max 20 concurrent requests
            
            async def fetch_and_parse(session, row):
                nonlocal success, extracted, failed
                item_id = row['id']
                url = row['url']
                content = ""
                
                async with semaphore:
                    if self.app._exit: return item_id, content
                    try:
                        async with session.get(url, headers=headers, timeout=15) as response:
                            response.raise_for_status()
                            html = await response.text()
                            success += 1
                            
                            soup = BeautifulSoup(html, 'html.parser')
                            elements = soup.select(selector)
                            content = " ".join(el.get_text() for el in elements)
                            
                            content = content.replace('\n', ' ').replace('\r', '').strip()
                            content = " ".join(content.split())
                            
                            if content:
                                extracted += 1
                            else:
                                failed += 1
                    except Exception as e:
                        failed += 1
                        
                    self.query_one("#progress-bar", ProgressBar).advance(1)
                    return item_id, content
                    
            async with aiohttp.ClientSession() as session:
                tasks = [fetch_and_parse(session, row) for row in results]
                parsed_results = await asyncio.gather(*tasks)
                
            if self.app._exit:
                self.write_log("Scraping cancelled.\n")
                return

            with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
                fieldnames = ['id', 'content']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                for item_id, content in parsed_results:
                    writer.writerow({'id': item_id, 'content': content})

            metrics = {
                'total': total,
                'success': success,
                'extracted': extracted,
                'failed': failed
            }
            
            self.write_log("Loading data to BigQuery...\n")
            self.query_one("#status-label", Label).update("[bold]Loading data to BigQuery...[/]")
            
            from google.cloud import bigquery
            
            table_id = f"{project}.{dataset}.{dest_table}"
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.CSV,
                skip_leading_rows=0,
                schema=[
                    bigquery.SchemaField("id", "STRING"),
                    bigquery.SchemaField("content", "STRING"),
                ],
                write_disposition="WRITE_TRUNCATE",
            )
            
            with open(csv_filename, "rb") as source_file:
                load_job = client.load_table_from_file(source_file, table_id, job_config=job_config)
                
            await loop.run_in_executor(None, load_job.result)
            
            self.write_log(f"Job finished. Loaded data to {table_id}\n")
            
            # Update status label with report
            report = (
                f"[bold]Scraping Report:[/bold]\n"
                f"- Total URLs: {metrics['total']}\n"
                f"- Successfully loaded: {metrics['success']}\n"
                f"- Descriptions extracted: {metrics['extracted']}\n"
                f"- Failed to get data: {metrics['failed']}"
            )
            self.query_one("#status-label", Label).update(report)
            
            if os.path.exists(csv_filename):
                os.remove(csv_filename)
                
            self.state.set_step_status('web', 'Completed')
            self.state.invalidate_descendants('web')
            
            self.notify("Web scraping completed successfully!", severity="information")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error during scraping: {e}", severity="error")

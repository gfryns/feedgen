from textual.app import ComposeResult
from screens.base_screen import WizardBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar
from textual.containers import Vertical, Horizontal
from screens.dataset_screen import get_bq_client
import asyncio
import csv
import os
import time
import requests
from bs4 import BeautifulSoup

class ScrapingScreen(WizardBaseScreen):
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
                yield Label(f"Product Page URL Column: {url_col}")
                
                yield Label("CSS Selector for description:")
                yield Input(value=self.state.get('selector', 'div[data-testid^="item-description"]'), id="selector")
                
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
            
    async def run_scraping(self, selector: str) -> None:
        logs = self.query_one("#process-logs", Log)
        
        def write_log(text):
            logs.write(text)
            self.log_content += text
            
        self.log_content = ""
        write_log("Starting web scraping...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        url_col = self.state.get('url_col')
        id_col = self.state.get('id_col', 'id')
        
        try:
            client = get_bq_client(self.state)
            
            source_table = "InputFiltered"
            dest_table = "InputFilteredWeb"
            
            query = f"SELECT id, url FROM `{project}.{dataset}.{source_table}`"
            self.write_log(f"Fetching URLs with query: {query}\n")
            
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
            
            csv_filename = "ids_contents.csv"
            self.write_log(f"Found {len(results)} rows. Scraping pages...\n")
            
            self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, total=len(results), progress=0)
            
            def do_scraping():
                total = len(results)
                success = 0
                extracted = 0
                failed = 0
                
                with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
                    fieldnames = ['id', 'content']
                    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    
                    for row in results:
                        item_id = row['id']
                        url = row['url']
                        
                        content = ""
                        try:
                            time.sleep(0.5)
                            response = requests.get(url, headers=headers, timeout=10)
                            response.raise_for_status()
                            success += 1
                            
                            soup = BeautifulSoup(response.content, 'html.parser')
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
                            content = ""
                            
                        writer.writerow({'id': item_id, 'content': content})
                        self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).advance, 1)
                        
                return {
                    'total': total,
                    'success': success,
                    'extracted': extracted,
                    'failed': failed
                }
                
            metrics = await loop.run_in_executor(None, do_scraping)
            
            self.write_log("Loading data to BigQuery...\n")
            
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

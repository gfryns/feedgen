from textual.app import ComposeResult
from screens.base_screen import WizardBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, Select, DataTable
from textual.containers import Vertical, Horizontal, Container
from screens.dataset_screen import get_bq_client
import asyncio
import json
import uuid

class ExamplesScreen(WizardBaseScreen):
    """Screen for Step 3e: Manage Examples."""
    
    def __init__(self, state):
        super().__init__(state)
        self.sheet_header = True
        
        self.methods = [
            ("Load from Google Spreadsheet", "sheet"),
            ("Pick specific products by ID", "ids")
        ]
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3e: Manage Examples", id="title")
            
            yield Static(
                "💡 Note: Examples are used for few-shot prompting. "
                "They should be 3-5 best-in-class examples to show the model what to aim for.",
                id="examples-tip"
            )
            
            method = self.state.get('examples_method', 'sheet')
            yield Select(self.methods, value=method, id="method-select")
            
            # 1. Spreadsheet Container
            with Vertical(id="sheet-container", classes="method-container"):
                yield Label("Spreadsheet URL:")
                yield Input(value=self.state.get('sheet_url', ''), placeholder="Enter URL", id="sheet-url")
                with Horizontal(id="sheet-fields-row"):
                    with Vertical(classes="col3"):
                        yield Label("Sheet Name:")
                        yield Input(value=self.state.get('sheet_name', 'Sheet1'), id="sheet-name")
                    with Vertical(classes="col3"):
                        yield Label("Range (optional):")
                        yield Input(value=self.state.get('sheet_range', ''), placeholder="e.g. A1:D10", id="sheet-range")
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Has Header", id="header-btn")
                
            # 2. Pick by ID Container
            with Vertical(id="ids-container", classes="method-container"):
                yield Label("Source Table:")
                yield Input(value="InputFiltered", id="ids-source")
                yield Label("Product IDs (comma-separated):")
                yield Input(placeholder="ID1, ID2, ID3", id="product-ids")
                
            with Horizontal():
                yield Button("Import examples", variant="success", id="run-btn")
                yield Button("Delete Stored Examples", variant="error", id="delete-btn")
                yield Button("Back to Menu", id="back-btn")
                
            yield Label("", id="status-label")
            
            with Collapsible(title="Examples Preview (0 stored)", id="preview-collapsible", collapsed=True):
                yield DataTable(id="examples-preview")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize view."""
        method = self.state.get('examples_method', 'sheet')
        for m in ["sheet", "ids"]:
            self.query_one(f"#{m}-container").styles.display = "none"
        self.query_one(f"#{method}-container").styles.display = "block"
        self.run_worker(self.load_examples_preview)
        
    def on_select_changed(self, event: Select.Changed) -> None:
        # Hide all containers
        for m in ["sheet", "ids"]:
            self.query_one(f"#{m}-container").styles.display = "none"
            
        # Show selected
        if event.value:
            self.query_one(f"#{event.value}-container").styles.display = "block"
            self.state.set('examples_method', event.value)
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            method = self.query_one("#method-select").value
            self.query_one("#logs-collapsible").collapsed = False
            
            if method == "sheet":
                url = self.query_one("#sheet-url").value
                name = self.query_one("#sheet-name").value
                range_val = self.query_one("#sheet-range").value
                
                self.state.set('sheet_url', url)
                self.state.set('sheet_name', name)
                self.state.set('sheet_range', range_val)
                
                self.run_worker(self.load_from_sheet(url, name, range_val, self.sheet_header))
            elif method == "ids":
                source = self.query_one("#ids-source").value
                ids = self.query_one("#product-ids").value
                self.run_worker(self.load_by_ids(source, ids))

                
        elif event.button.id == "header-btn":
            self.sheet_header = not self.sheet_header
            if self.sheet_header:
                event.button.label = "[green]✔[/] Has Header"
            else:
                event.button.label = "[red]✘[/] No Header"
                
        elif event.button.id == "delete-btn":
            self.query_one("#logs-collapsible").collapsed = False
            self.run_worker(self.clear_examples())
            
    async def load_examples_preview(self) -> None:
        try:
            client = get_bq_client(self.state)
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            table_id = f"{project}.{dataset}.Examples"
            
            # Get count
            count_query = f"SELECT COUNT(*) as total FROM `{table_id}`"
            loop = asyncio.get_running_loop()
            count_res = await loop.run_in_executor(None, lambda: list(client.query(count_query).result()))
            total_count = count_res[0]['total'] if count_res else 0
            
            # Update title
            self.query_one("#preview-collapsible").title = f"Examples Preview ({total_count} stored)"
            
            # Update status in state based on actual count
            if total_count > 0:
                self.state.set_step_status('examples', 'Completed')
            else:
                self.state.set_step_status('examples', 'Pending')
            
            # Get top 5 rows
            query = f"SELECT id, title, description FROM `{table_id}` LIMIT 5"
            res = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
            
            table_widget = self.query_one("#examples-preview", DataTable)
            table_widget.clear(columns=True)
            table_widget.add_columns("ID", "Title", "Description")
            
            for row in res:
                table_widget.add_row(str(row['id']), str(row['title']), str(row['description']))
                
        except Exception:
            self.query_one("#preview-collapsible").title = "Examples Preview (0 stored)"
            try:
                table_widget = self.query_one("#examples-preview", DataTable)
                table_widget.clear(columns=True)
            except Exception:
                pass
                
    async def load_from_sheet(self, url: str, sheet_name: str, range_val: str, has_header: bool) -> None:
        self.log_content = ""
        self.write_log("Loading from Google Sheet...\n")
        
        try:
            import gspread
            import google.auth
            
            self.write_log("Authenticating with Google Sheets...\n")
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
            gc = gspread.authorize(credentials)
            
            self.write_log("Opening spreadsheet...\n")
            sh = gc.open_by_url(url)
            worksheet = sh.worksheet(sheet_name)
            
            self.write_log("Fetching data...\n")
            loop = asyncio.get_running_loop()
            if range_val:
                values = await loop.run_in_executor(None, lambda: worksheet.get(range_val))
            else:
                values = await loop.run_in_executor(None, lambda: worksheet.get_all_values())
                
            if not values:
                raise Exception("No data found in the sheet.")
                
            if has_header:
                headers = values[0]
                rows = values[1:]
            else:
                headers = ['properties', 'title', 'description']
                rows = values
                
            self.write_log(f"Read {len(rows)} rows from sheet.\n")
            
            prop_idx = headers.index('properties') if 'properties' in headers else 0
            title_idx = headers.index('title') if 'title' in headers else 1
            desc_idx = headers.index('description') if 'description' in headers else 2
            
            examples = []
            for row in rows:
                if len(row) <= max(prop_idx, title_idx, desc_idx):
                    continue
                props = row[prop_idx].strip()
                title = row[title_idx].strip()
                desc = row[desc_idx].strip()
                
                if not props and not title and not desc:
                    continue
                    
                try:
                    json.loads(props)
                except json.JSONDecodeError:
                    self.write_log(f"Warning: Invalid JSON in row: {props}. Skipping.\n")
                    continue
                    
                examples.append({
                    'id': str(uuid.uuid4()),
                    'properties': props,
                    'title': title,
                    'description': desc
                })
                
            if not examples:
                raise Exception("No valid examples found.")
                
            client = get_bq_client(self.state)
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            table_id = f"{project}.{dataset}.Examples"
            
            from google.cloud import bigquery
            job_config = bigquery.LoadJobConfig(
                schema=[
                    bigquery.SchemaField("id", "STRING"),
                    bigquery.SchemaField("properties", "STRING"),
                    bigquery.SchemaField("title", "STRING"),
                    bigquery.SchemaField("description", "STRING"),
                ],
                write_disposition="WRITE_TRUNCATE",
            )
            
            self.write_log(f"Loading {len(examples)} examples to {table_id}...\n")
            job = client.load_table_from_json(examples, table_id, job_config=job_config)
            await loop.run_in_executor(None, job.result)
            
            self.write_log("Examples loaded successfully.\n")
            self.state.set_step_status('examples', 'Completed')
            self.state.invalidate_descendants('examples')
            self.notify("Examples loaded successfully!", severity="information")
            
            # Refresh preview
            self.run_worker(self.load_examples_preview)
            
        except Exception as e:
            import gspread
            if isinstance(e, gspread.exceptions.APIError) and ('insufficient authentication scopes' in str(e).lower()):
                self.write_log("\n[ERROR] Request had insufficient authentication scopes.\n")
                self.write_log("To fix this, you need to run in your terminal:\n")
                self.write_log("gcloud auth application-default login --scopes=https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/cloud-platform\n")
            else:
                self.write_log(f"Error: {e}\n")
            self.notify(f"Error: {e}", severity="error")
            
    async def load_by_ids(self, source: str, ids_str: str) -> None:
        self.log_content = ""
        self.write_log(f"Loading examples by ID from {source}...\n")
        
        try:
            ids = [i.strip() for i in ids_str.split(',') if i.strip()]
            if not ids:
                raise Exception("No IDs provided.")
                
            client = get_bq_client(self.state)
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            table_id = f"{project}.{dataset}.Examples"
            
            ids_formatted = ", ".join([f"'{i}'" for i in ids])
            
            # Resolve source table reference
            if '.' in source:
                parts = source.split('.')
                source_ref = ".".join([f"`{p}`" for p in parts])
            else:
                source_ref = f"`{project}.{dataset}.{source}`"
                
            # Verify IDs first
            verify_query = f"SELECT id FROM {source_ref} WHERE id IN ({ids_formatted})"
            self.write_log(f"Verifying IDs with query: {verify_query}\n")
            
            loop = asyncio.get_running_loop()
            found_res = await loop.run_in_executor(None, lambda: list(client.query(verify_query).result()))
            found_ids = [row['id'] for row in found_res]
            
            missing_ids = set(ids) - set(found_ids)
            if missing_ids:
                self.write_log(f"Warning: The following IDs were not found: {list(missing_ids)}\n")
                self.notify(f"Warning: {len(missing_ids)} IDs not found! Check logs.", severity="warning")
                
            if not found_ids:
                raise Exception("None of the provided IDs were found in the source table.")
                
            # Use only found IDs for creation
            ids_formatted = ", ".join([f"'{i}'" for i in found_ids])
            
            sql = f"""
            CREATE OR REPLACE TABLE `{table_id}` AS
            SELECT
              id,
              TO_JSON_STRING((SELECT AS STRUCT * EXCEPT(id) FROM UNNEST([I]))) AS properties,
              title,
              description
            FROM {source_ref} AS I
            WHERE id IN ({ids_formatted})
            """
            
            self.write_log(f"Executing SQL:\n{sql}\n")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: client.query(sql).result())
            
            self.write_log("Examples created successfully.\n")
            self.state.set_step_status('examples', 'Completed')
            self.state.invalidate_descendants('examples')
            self.notify("Examples created successfully!", severity="information")
            
            # Refresh preview
            self.run_worker(self.load_examples_preview)
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error: {e}", severity="error")
            
    async def clear_examples(self) -> None:
        self.log_content = ""
        self.write_log("Clearing examples...\n")
        
        try:
            client = get_bq_client(self.state)
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            table_id = f"{project}.{dataset}.Examples"
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: client.delete_table(table_id, not_found_ok=True))
            
            self.write_log("Examples cleared.\n")
            self.state.set_step_status('examples', 'Pending')
            self.state.invalidate_descendants('examples')
            self.notify("Examples cleared.", severity="information")
            
            # Refresh preview
            self.run_worker(self.load_examples_preview)
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error: {e}", severity="error")

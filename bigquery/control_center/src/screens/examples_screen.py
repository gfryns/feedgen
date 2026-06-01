from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, Select, DataTable
from textual.containers import Vertical, Horizontal, Container
from services.bq_client import get_bq_client
from textual.reactive import reactive
from textual.css.query import NoMatches
import asyncio
import services.examples_service as ex_srv
from messages import StateUpdateMessage, StatusUpdateMessage

class ExamplesScreen(ControlCenterBaseScreen):
    """Screen for Step 3e: Manage Examples."""
    
    def __init__(self, state):
        super().__init__(state)
        self.examples_method = self.state.get('examples_method', 'sheet')
        
        self.methods = [
            ("Load from Google Spreadsheet", "sheet"),
            ("Pick specific products by ID", "ids")
        ]
        
    def watch_sheet_header(self, new_value: bool) -> None:
        try:
            self.query_one("#header-btn", Button).label = "[green]✔[/] Has Header" if new_value else "[red]✘[/] No Header"
        except NoMatches: pass
        
    def watch_examples_method(self, new_value: str) -> None:
        try:
            self.notify(f"Method changed to: {new_value}")
            for m in ["sheet", "ids"]:
                self.query_one(f"#{m}-container").styles.display = "none"
            self.query_one(f"#{new_value}-container").styles.display = "block"
        except NoMatches: pass
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3e: Manage Examples", id="title")
            
            yield Static(
                "💡 Note: Examples are used for few-shot prompting. "
                "They should be 3-5 best-in-class examples to show the model what to aim for.",
                id="examples-tip"
            )
            
            with Vertical(classes="card"):
                yield Label("Examples Source", id="examples-source-title")
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
                
            with Collapsible(title="Examples Preview (0 stored)", id="preview-collapsible", collapsed=True):
                yield DataTable(id="examples-preview")
                
            with Horizontal():
                yield Button("Run Import", variant="success", id="run-btn")
                yield Button("Delete Stored Examples", variant="error", id="delete-btn")
                yield Button("Cancel", id="back-btn")
                
            yield Label("", id="status-label")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize view."""
        self.watch_examples_method(self.examples_method)
        self.run_worker(self.load_examples_preview)
        
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value:
            self.examples_method = event.value
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            method = self.query_one("#method-select").value
            self.post_message(StateUpdateMessage('examples_method', method))
            
            if method == "sheet":
                url = self.query_one("#sheet-url").value
                name = self.query_one("#sheet-name").value
                range_val = self.query_one("#sheet-range").value
                
                self.post_message(StateUpdateMessage('sheet_url', url))
                self.post_message(StateUpdateMessage('sheet_name', name))
                self.post_message(StateUpdateMessage('sheet_range', range_val))
                self.post_message(StateUpdateMessage('examples_source', name))
                
                self.run_worker(self.load_from_sheet(url, name, range_val, self.sheet_header))
            elif method == "ids":
                source = self.query_one("#ids-source").value
                ids = self.query_one("#product-ids").value
                self.post_message(StateUpdateMessage('examples_source', ids))
                self.run_worker(self.load_by_ids(source, ids))

                
        elif event.button.id == "header-btn":
            self.sheet_header = not self.sheet_header
                
        elif event.button.id == "delete-btn":
            self.run_worker(self.clear_examples())
            
    async def load_examples_preview(self) -> None:
        try:
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            loop = asyncio.get_running_loop()
            
            total_count, preview_data = await loop.run_in_executor(
                None, 
                lambda: ex_srv.get_examples_preview(project, dataset)
            )
            
            # Update title
            self.query_one("#preview-collapsible").title = f"Examples Preview ({total_count} stored)"
            
            # Update status in state based on actual count
            self.post_message(StateUpdateMessage('examples_count', total_count))
            if total_count > 0:
                self.post_message(StatusUpdateMessage('examples', 'Completed'))
            else:
                self.post_message(StatusUpdateMessage('examples', 'Pending'))
            
            table_widget = self.query_one("#examples-preview", DataTable)
            table_widget.clear(columns=True)
            table_widget.add_columns("ID", "Title", "Description")
            
            for row in preview_data:
                table_widget.add_row(row[0], row[1], row[2])
                
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
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        
        try:
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(
                None,
                lambda: ex_srv.load_examples_from_sheet(project, dataset, url, sheet_name, range_val, has_header, self.write_log)
            )
            
            self.post_message(StatusUpdateMessage('examples', 'Completed'))
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
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            loop = asyncio.get_running_loop()
            
            count, missing_ids = await loop.run_in_executor(
                None,
                lambda: ex_srv.load_examples_by_ids(project, dataset, source, ids_str, self.write_log)
            )
            
            if missing_ids:
                self.notify(f"Warning: {len(missing_ids)} IDs not found! Check logs.", severity="warning")
                
            self.post_message(StatusUpdateMessage('examples', 'Completed'))
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
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: ex_srv.clear_examples(project, dataset))
            
            self.write_log("Examples cleared.\n")
            self.post_message(StatusUpdateMessage('examples', 'Pending'))
            self.notify("Examples cleared.", severity="information")
            
            # Refresh preview
            self.run_worker(self.load_examples_preview)
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error: {e}", severity="error")

from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Static, DataTable, Select
from textual.containers import Vertical, Horizontal, Container
import asyncio
from services.bq_client import get_bq_client

class SourceScreen(ControlCenterBaseScreen):
    """Screen for Step 3a: Source Table Setup."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3a: Source Table Setup", id="title")
            
            with Container(classes="card"):
                yield Label("Select Raw Input Table:")
                yield Container(id="table-select-container")
                yield Input(value=self.state.get('raw_table', 'InputRaw'), id="raw-table", placeholder="Enter custom table ID")
                
                yield Static(
                    "💡 Tip: If you need to import your feed from Google Merchant Center to BigQuery, "
                    "you can set up the [BigQuery Data Transfer Service](https://cloud.google.com/bigquery/docs/merchant-center-transfer).",
                    id="gmc-tip"
                )
                
                yield Button("Load Input Table Info", variant="primary", id="load-info-btn")
            
            with Container(classes="card"):
                yield Label("Table Preview", id="preview-title")
                yield Label("", id="info-summary")
                yield DataTable(id="examples-table")
            
            with Horizontal():
                yield Button("Save & Return", variant="success", id="select-btn")
                yield Button("Back to Menu", id="back-btn")
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "load-info-btn":
            raw_table = self.query_one("#raw-table").value
            if not raw_table:
                self.notify("Table name is required!", severity="error")
                return
                
            self.run_worker(self.load_table_info(raw_table))
        elif event.button.id == "select-btn":
            raw_table = self.query_one("#raw-table").value
            old_table = self.state.get('raw_table')
            
            if raw_table != old_table:
                self.state.invalidate_descendants('source')
                
            self.state.set('raw_table', raw_table)
            self.state.set_step_status('source', 'Completed')
            self.dismiss(True)
            
    def on_mount(self) -> None:
        """Load tables and auto-load info if table is set."""
        self.query_one("#raw-table").styles.display = "none"
        self.run_worker(self.populate_tables)
        
        raw_table = self.state.get('raw_table')
        if raw_table:
            self.run_worker(self.load_table_info(raw_table))
            
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "table-select":
            if event.value == "other":
                self.query_one("#raw-table").styles.display = "block"
            else:
                self.query_one("#raw-table").styles.display = "none"
                if event.value:
                    self.query_one("#raw-table").value = event.value
                    self.run_worker(self.load_table_info(event.value))
                    
    async def populate_tables(self) -> None:
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        
        try:
            loop = asyncio.get_running_loop()
            client = get_bq_client(project)
            
            def fetch():
                tables = client.list_tables(dataset)
                return [(t.table_id, t.table_id) for t in tables]
                
            options = await loop.run_in_executor(None, fetch)
            options.append(("Other (Enter manually)", "other"))
            
            raw_table = self.state.get('raw_table', 'InputRaw')
            
            val = "other"
            if raw_table in [o[1] for o in options]:
                val = raw_table
                
            select_widget = Select(options, value=val, id="table-select")
            await self.query_one("#table-select-container").mount(select_widget)
            
            if val == "other":
                self.query_one("#raw-table").styles.display = "block"
                
        except Exception as e:
            self.notify(f"Error fetching tables: {e}", severity="error")
            self.query_one("#raw-table").styles.display = "block"
            
    async def load_table_info(self, raw_table: str) -> None:
        self.notify("Loading table info...")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        target_region = self.state.get('region', 'EU')
            
        try:
            from services.source_service import get_table_info
            
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: get_table_info(project, dataset, raw_table, target_region, self.write_log)
            )
            
            for warning in result['warnings']:
                self.notify(warning, severity="warning")
                
            self.query_one("#info-summary", Label).update(result['summary'])
            
            # Update DataTable
            table_widget = self.query_one("#examples-table", DataTable)
            table_widget.clear(columns=True)
            table_widget.add_columns("ID", "Title", "Description")
            
            for row in result['preview']:
                table_widget.add_row(row[0], row[1], row[2])
                
            self.notify("Table info loaded successfully!", severity="information")
                
        except Exception as e:
            self.notify(f"Error loading table info: {e}", severity="error")

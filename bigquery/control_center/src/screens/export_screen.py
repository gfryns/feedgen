from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Log, Select, Checkbox
from textual.containers import Vertical, Horizontal, Container
from textual.markup import escape
from textual.reactive import reactive
from textual.css.query import NoMatches
import asyncio
from messages import StateUpdateMessage, StatusUpdateMessage

class ExportScreen(ControlCenterBaseScreen):
    """Screen for Step 5: Export Feed."""
    
    export_title = reactive(True)
    export_desc = reactive(True)
    export_highlights = reactive(True)
    
    title_available = reactive(True)
    desc_available = reactive(True)
    highlights_available = reactive(True)
    
    def __init__(self, state):
        super().__init__(state)
        
        self.feed_types = [
            ("Supplemental Feed (recommended)", "supplemental"),
            ("Full Feed", "full")
        ]
        
        self.dest_types = [
            ("Cloud Storage (GCS)", "gcs"),
            ("Google Sheets", "sheets")
        ]
        
    def watch_export_title(self, new_value: bool) -> None:
        try:
            self.query_one("#chk-title", Button).label = "[green]✔[/] Title" if new_value else "[red]✘[/] Title"
        except NoMatches: pass
        
    def watch_export_desc(self, new_value: bool) -> None:
        try:
            self.query_one("#chk-desc", Button).label = "[green]✔[/] Desc" if new_value else "[red]✘[/] Desc"
        except NoMatches: pass
        
    def watch_export_highlights(self, new_value: bool) -> None:
        try:
            self.query_one("#chk-highlights", Button).label = "[green]✔[/] Highlights" if new_value else "[red]✘[/] Highlights"
        except NoMatches: pass
        
    def watch_title_available(self, new_value: bool) -> None:
        try:
            btn = self.query_one("#chk-title", Button)
            btn.disabled = not new_value
            if not new_value:
                self.export_title = False
                btn.label = "[gray]✘[/] Title"
        except NoMatches: pass
        
    def watch_desc_available(self, new_value: bool) -> None:
        try:
            btn = self.query_one("#chk-desc", Button)
            btn.disabled = not new_value
            if not new_value:
                self.export_desc = False
                btn.label = "[gray]✘[/] Desc"
        except NoMatches: pass
        
    def watch_highlights_available(self, new_value: bool) -> None:
        try:
            btn = self.query_one("#chk-highlights", Button)
            btn.disabled = not new_value
            if not new_value:
                self.export_highlights = False
                btn.label = "[gray]✘[/] Highlights"
        except NoMatches: pass
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 5: Export Feed", id="title")
            
            with Container(classes="card"):
                yield Label("Export Configuration", id="export-config-title")
                
                with Horizontal(id="export-row-1"):
                    with Vertical(classes="col4"):
                        yield Label("Select Feed Type:")
                        yield Select(self.feed_types, value=self.state.get('feed_type', 'supplemental'), id="feed-type")
                    with Vertical(classes="col4"):
                        yield Label("Select Destination:")
                        yield Select(self.dest_types, value=self.state.get('destination_type', 'gcs'), id="destination-type")
                    with Vertical(classes="col4"):
                        yield Label("GCS Bucket Name:", id="lbl-bucket")
                        yield Input(value=self.state.get('gcs_bucket', ''), placeholder="my-gmc-bucket", id="gcs-bucket")
                        yield Label("Google Sheet ID:", id="lbl-sheet")
                        yield Input(value=self.state.get('sheet_id', ''), placeholder="spreadsheet_id", id="sheet-id")
                    with Vertical(classes="col4"):
                        yield Label("Filename:", id="lbl-filename")
                        yield Input(value=self.state.get('filename', 'supplemental_feed.csv'), placeholder="supplemental_feed.csv", id="filename")
                        yield Label("Sheet Name:", id="lbl-sheet-name")
                        yield Input(value=self.state.get('export_sheet_name', 'Sheet1'), placeholder="Sheet1", id="export-sheet-name")
                        
                with Horizontal(id="export-row-2"):
                    with Vertical(classes="col"):
                        yield Label("Source BigQuery Table:")
                        with Horizontal(id="source-table-row"):
                            yield Container(id="table-select-container")
                            yield Button("↻", id="check-schema-btn")
                        yield Input(value=self.state.get('export_source_table', self.state.get('output_table', 'Output')), placeholder="table", id="raw-table")
                    with Vertical(classes="col", id="chk-container"):
                        yield Label("Columns to Export:")
                        with Horizontal(id="chk-row"):
                            yield Button("[green]✔[/] Title", id="chk-title")
                            yield Button("[green]✔[/] Desc", id="chk-desc")
                            yield Button("[green]✔[/] Highlights", id="chk-highlights")
            
            with Horizontal():
                yield Button("Run Export", variant="success", id="run-btn")
                yield Button("Back", id="back-btn")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
                
            yield Label("", id="status-label")
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize visibility based on state."""
        self.query_one("#raw-table").styles.display = "none"
        self.run_worker(self.populate_tables)
        
        dest_type = self.state.get('destination_type', 'gcs')
        self.update_target_visibility(dest_type)
        
        feed_type = self.state.get('feed_type', 'supplemental')
        if feed_type == "full":
            self.query_one("#chk-container").styles.display = "none"
            
    async def populate_tables(self) -> None:
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        
        try:
            from services.bq_client import get_bq_client
            loop = asyncio.get_running_loop()
            client = get_bq_client(project)
            
            def fetch():
                tables = client.list_tables(dataset)
                return [(t.table_id, t.table_id) for t in tables]
                
            options = await loop.run_in_executor(None, fetch)
            options.append(("Other (Enter manually)", "other"))
            
            export_source_table = self.state.get('export_source_table', self.state.get('output_table', 'Output'))
            
            val = "other"
            if export_source_table in [o[1] for o in options]:
                val = export_source_table
                
            select_widget = Select(options, value=val, id="table-select")
            await self.query_one("#table-select-container").mount(select_widget)
            
            if val == "other":
                self.query_one("#raw-table").styles.display = "block"
                
        except Exception as e:
            self.notify(f"Error fetching tables: {e}", severity="error")
            self.query_one("#raw-table").styles.display = "block"
        
    def update_target_visibility(self, dest_type: str) -> None:
        if dest_type == "gcs":
            self.query_one("#lbl-bucket").styles.display = "block"
            self.query_one("#gcs-bucket").styles.display = "block"
            self.query_one("#lbl-filename").styles.display = "block"
            self.query_one("#filename").styles.display = "block"
            
            self.query_one("#lbl-sheet").styles.display = "none"
            self.query_one("#sheet-id").styles.display = "none"
            self.query_one("#lbl-sheet-name").styles.display = "none"
            self.query_one("#export-sheet-name").styles.display = "none"
        else:
            self.query_one("#lbl-bucket").styles.display = "none"
            self.query_one("#gcs-bucket").styles.display = "none"
            self.query_one("#lbl-filename").styles.display = "none"
            self.query_one("#filename").styles.display = "none"
            
            self.query_one("#lbl-sheet").styles.display = "block"
            self.query_one("#sheet-id").styles.display = "block"
            self.query_one("#lbl-sheet-name").styles.display = "block"
            self.query_one("#export-sheet-name").styles.display = "block"
            
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "destination-type":
            self.update_target_visibility(event.value)
        elif event.select.id == "feed-type":
            if event.value == "full":
                self.query_one("#chk-container").styles.display = "none"
            else:
                self.query_one("#chk-container").styles.display = "block"
        elif event.select.id == "table-select":
            if event.value == "other":
                self.query_one("#raw-table").styles.display = "block"
            else:
                self.query_one("#raw-table").styles.display = "none"
                if event.value:
                    self.query_one("#raw-table").value = event.value
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check-schema-btn":
            raw_table = self.query_one("#raw-table").value
            if not raw_table:
                self.notify("Source Table name is required to check schema!", severity="error")
                return
                
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            
            try:
                from services.export_service import get_table_columns
                columns = get_table_columns(project, dataset, raw_table)
                
                if 'id' not in columns:
                    self.notify("Error: Table must contain an 'id' column!", severity="error")
                    self.query_one("#status-label", Label).update("[red]Error: Table must contain an 'id' column![/]")
                    return
                    
                self.notify("Schema loaded successfully!", severity="information")
                self.query_one("#status-label", Label).update("[green]Schema loaded successfully![/]")
                self.set_timer(7, lambda: self.query_one("#status-label", Label).update(""))
                
                # Update reactive attributes
                self.title_available = 'title' in columns
                self.desc_available = 'description' in columns
                self.highlights_available = 'highlights' in columns
                
            except Exception as e:
                self.notify(f"Error loading schema: {e}", severity="error")
                self.query_one("#status-label", Label).update(f"[red]Error loading schema: {escape(str(e))}[/]")
                self.set_timer(10, lambda: self.query_one("#status-label", Label).update(""))
                
        elif event.button.id == "chk-title":
            self.export_title = not self.export_title
            
        elif event.button.id == "chk-desc":
            self.export_desc = not self.export_desc
            
        elif event.button.id == "chk-highlights":
            self.export_highlights = not self.export_highlights
                
        elif event.button.id == "run-btn":
            feed_type = self.query_one("#feed-type").value
            destination_type = self.query_one("#destination-type").value
            raw_table = self.query_one("#raw-table").value
            
            if destination_type == "gcs":
                destination_target = self.query_one("#gcs-bucket").value
                filename = self.query_one("#filename").value
                sheet_name = "Sheet1" # Default
            else:
                destination_target = self.query_one("#sheet-id").value
                filename = "" 
                sheet_name = self.query_one("#export-sheet-name").value
            
            export_table = "ExportGMC" # Hardcoded default
            
            export_title = self.export_title
            export_desc = self.export_desc
            export_highlights = self.export_highlights
            
            if not raw_table:
                self.notify("Source Table name is required!", severity="error")
                return
                
            self.post_message(StateUpdateMessage('feed_type', feed_type))
            self.post_message(StateUpdateMessage('destination_type', destination_type))
            self.post_message(StateUpdateMessage('raw_table', raw_table))
            self.post_message(StateUpdateMessage('export_table', export_table))
            self.post_message(StateUpdateMessage('gcs_bucket', self.query_one("#gcs-bucket").value))
            self.post_message(StateUpdateMessage('sheet_id', self.query_one("#sheet-id").value))
            self.post_message(StateUpdateMessage('export_sheet_name', sheet_name))
            self.post_message(StateUpdateMessage('destination_target', destination_target))
            self.post_message(StateUpdateMessage('filename', filename))
            self.post_message(StateUpdateMessage('export_source_table', raw_table))
            
            self.run_worker(self.run_export(feed_type, export_table, destination_type, destination_target, filename, raw_table, export_title, export_desc, export_highlights, sheet_name))
            
    async def run_export(self, feed_type: str, export_table: str, destination_type: str, destination_target: str, filename: str, raw_table: str, export_title: bool, export_desc: bool, export_highlights: bool, sheet_name: str) -> None:
        self.log_content = ""
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        output_table = self.state.get('output_table', 'Output')
        
        def log_cb_wrapper(text: str) -> None:
            self.write_log(text)
            clean_text = text.strip().replace("\n", " ")
            if not clean_text:
                return
            if "Starting Merchant Center Export" in clean_text:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Step 1/2: Initializing Merchant Center export...[/]")
            elif "Deploying EmbedForMerchantFeed" in clean_text:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Step 1/2: Deploying BigQuery formatting function...[/]")
            elif "Creating Supplemental Feed" in clean_text or "Creating Full Feed" in clean_text:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Step 1/2: Generating export SQL view...[/]")
            elif "Executing SQL to fetch data" in clean_text:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Step 1/2: Fetching formatted feed records...[/]")
            elif "Fetched" in clean_text and "rows from BigQuery" in clean_text:
                parts = clean_text.split()
                row_count = parts[1] if len(parts) > 1 else "data"
                self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[bold]Step 2/2: Formatting {row_count} records for destination...[/]")
            elif "Exporting data to GCS" in clean_text or "Exporting data to Google Sheet" in clean_text:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Step 2/2: Writing data to external feed destination...[/]")
                
        try:
            from services.export_service import export_to_gmc
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(
                None,
                lambda: export_to_gmc(project, dataset, raw_table, output_table, export_table, feed_type, destination_type, destination_target, filename, sheet_name, log_cb_wrapper, export_title, export_desc, export_highlights)
            )
            
            self.post_message(StatusUpdateMessage('export', 'Completed'))
            
            self.notify("Export completed successfully!", severity="information")
            self.query_one("#status-label", Label).update("[green]Export completed successfully![/]")
            self.set_timer(7, lambda: self.query_one("#status-label", Label).update(""))
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error during export: {e}", severity="error")
            self.query_one("#status-label", Label).update(f"[red]Error during export: {escape(str(e))}[/]")
            self.set_timer(10, lambda: self.query_one("#status-label", Label).update(""))

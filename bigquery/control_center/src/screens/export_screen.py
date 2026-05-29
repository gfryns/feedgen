from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Log, Select, Checkbox
from textual.containers import Vertical, Horizontal, Container
from textual.markup import escape
import asyncio

class ExportScreen(ControlCenterBaseScreen):
    """Screen for Step 5: Export Feed."""
    
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
        
        self.export_title = True
        self.export_desc = True
        self.export_highlights = True
        
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
                            yield Input(value=self.state.get('export_source_table', self.state.get('output_table', 'Output')), placeholder="table", id="raw-table")
                            yield Button("↻", id="check-schema-btn")
                    with Vertical(classes="col", id="chk-container"):
                        yield Label("Columns to Export:")
                        with Horizontal(id="chk-row"):
                            yield Button("[green]✔[/] Title", id="chk-title")
                            yield Button("[green]✔[/] Desc", id="chk-desc")
                            yield Button("[green]✔[/] Highlights", id="chk-highlights")
            
            with Horizontal():
                yield Button("Run Export", variant="success", id="run-btn")
                yield Button("Cancel", id="back-btn")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
                
            yield Label("", id="status-label")
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize visibility based on state."""
        dest_type = self.state.get('destination_type', 'gcs')
        self.update_target_visibility(dest_type)
        
        feed_type = self.state.get('feed_type', 'supplemental')
        if feed_type == "full":
            self.query_one("#chk-container").styles.display = "none"
        
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
                
                # Update buttons
                self.query_one("#chk-title").disabled = 'title' not in columns
                self.query_one("#chk-desc").disabled = 'description' not in columns
                self.query_one("#chk-highlights").disabled = 'highlights' not in columns
                
                # If disabled, update label too
                if 'title' not in columns:
                    self.export_title = False
                    self.query_one("#chk-title").label = "[gray]✘[/] Title"
                if 'description' not in columns:
                    self.export_desc = False
                    self.query_one("#chk-desc").label = "[gray]✘[/] Desc"
                if 'highlights' not in columns:
                    self.export_highlights = False
                    self.query_one("#chk-highlights").label = "[gray]✘[/] Highlights"
                
            except Exception as e:
                self.notify(f"Error loading schema: {e}", severity="error")
                self.query_one("#status-label", Label).update(f"[red]Error loading schema: {escape(str(e))}[/]")
                
        elif event.button.id == "chk-title":
            self.export_title = not self.export_title
            event.button.label = "[green]✔[/] Title" if self.export_title else "[red]✘[/] Title"
            
        elif event.button.id == "chk-desc":
            self.export_desc = not self.export_desc
            event.button.label = "[green]✔[/] Desc" if self.export_desc else "[red]✘[/] Desc"
            
        elif event.button.id == "chk-highlights":
            self.export_highlights = not self.export_highlights
            event.button.label = "[green]✔[/] Highlights" if self.export_highlights else "[red]✘[/] Highlights"
                
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
                
            self.state.update_data({
                'feed_type': feed_type,
                'destination_type': destination_type,
                'raw_table': raw_table,
                'export_table': export_table,
                'gcs_bucket': self.query_one("#gcs-bucket").value,
                'sheet_id': self.query_one("#sheet-id").value,
                'export_sheet_name': sheet_name,
                'destination_target': destination_target,
                'filename': filename,
                'export_source_table': raw_table
            })
            
            self.run_worker(self.run_export(feed_type, export_table, destination_type, destination_target, filename, raw_table, export_title, export_desc, export_highlights, sheet_name))
            
    async def run_export(self, feed_type: str, export_table: str, destination_type: str, destination_target: str, filename: str, raw_table: str, export_title: bool, export_desc: bool, export_highlights: bool, sheet_name: str) -> None:
        self.log_content = ""
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        output_table = self.state.get('output_table', 'Output')
        
        try:
            from services.export_service import export_to_gmc
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(
                None,
                lambda: export_to_gmc(project, dataset, raw_table, output_table, export_table, feed_type, destination_type, destination_target, filename, sheet_name, self.write_log, export_title, export_desc, export_highlights)
            )
            
            self.state.set_step_status('export', 'Completed')
            
            self.notify("Export completed successfully!", severity="information")
            self.query_one("#status-label", Label).update("[green]Export completed successfully![/]")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error during export: {e}", severity="error")
            self.query_one("#status-label", Label).update(f"[red]Error during export: {escape(str(e))}[/]")

from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Log, Select
from textual.containers import Vertical, Horizontal
import asyncio

class ExportScreen(ControlCenterBaseScreen):
    """Screen for Step 5: Export to Merchant Center."""
    
    def __init__(self, state):
        super().__init__(state)
        
        self.feed_types = [
            ("Supplemental Feed (Just ID, Title, Description)", "supplemental"),
            ("Full Feed (Join all original feed columns)", "full")
        ]
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 5: Export to Merchant Center", id="title")
            
            yield Label("Select Feed Type:")
            yield Select(self.feed_types, value=self.state.get('feed_type', 'supplemental'), id="feed-type")
            
            yield Label("Export Table Name:")
            yield Input(value=self.state.get('export_table', 'ExportGMC'), placeholder="ExportGMC", id="export-table")
            
            with Horizontal():
                yield Button("Generate Export Table", variant="success", id="run-btn")
                yield Button("Back to Menu", id="back-btn")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
                
            yield Label("", id="status-label")
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            feed_type = self.query_one("#feed-type").value
            export_table = self.query_one("#export-table").value
            
            if not export_table:
                self.notify("Export Table name is required!", severity="error")
                return
                
            self.state.update_data({
                'feed_type': feed_type,
                'export_table': export_table
            })
            
            self.query_one("#logs-collapsible").collapsed = False
            self.run_worker(self.run_export(feed_type, export_table))
            
    async def run_export(self, feed_type: str, export_table: str) -> None:
        self.log_content = ""
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        raw_table = self.state.get('raw_table')
        output_table = self.state.get('output_table', 'Output')
        insecure = self.state.insecure
        
        try:
            from services.export_service import export_to_gmc
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(
                None,
                lambda: export_to_gmc(project, dataset, raw_table, output_table, export_table, feed_type, insecure, self.write_log)
            )
            
            self.state.set_step_status('export', 'Completed')
            
            self.notify("Export table generated successfully!", severity="information")
            self.query_one("#status-label", Label).update("[green]Export table generated successfully![/]")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error during export: {e}", severity="error")
            self.query_one("#status-label", Label).update(f"[red]Error during export: {e}[/]")

from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, LoadingIndicator, Log
from textual.containers import Vertical, Horizontal
from textual.markup import escape
from validators import is_valid_project_id
import asyncio
import subprocess

class ProjectScreen(ControlCenterBaseScreen):
    """Screen for Cloud Project Setup."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Cloud Project Setup", id="title")
            
            yield Label("GCP Project ID (lowercase, digits, hyphens):")
            yield Input(value=self.state.get('project', ''), placeholder="Enter Project ID", id="project")
            
            with Collapsible(title="What will be set up?", collapsed=True):
                yield Static(
                    "The following operations will be performed:\n\n"
                    "1. Set the active project in gcloud:\n"
                    "   `gcloud config set project <project>`\n\n"
                    "2. Enable Vertex AI API:\n"
                    "   `gcloud services enable aiplatform.googleapis.com`"
                )
                
            with Horizontal():
                yield Button("Save and Enable APIs", variant="success", id="save-enable-btn")
                yield Button("Back to Menu", id="back-btn")
                
            yield LoadingIndicator(id="loading")
            yield Label("", id="status-label")
            
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
            
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-enable-btn":
            project_val = self.query_one("#project").value
            if not project_val:
                self.notify("Project ID is required!", severity="error")
                return
                
            if not is_valid_project_id(project_val):
                self.notify("Invalid Project ID. Must be 6-30 lowercase letters, digits, or hyphens.", severity="error")
                return
                
            old_project = self.state.get('project')
            
            if old_project and project_val != old_project:
                self.state.invalidate_descendants('config')
            
            self.state.update_data({'project': project_val})
            self.state.set_step_status('config', 'Completed')
            
            self.query_one("#loading").styles.display = "block"
            self.query_one("#status-label").update("Status: Enabling APIs...")
            
            # Automatically expand logs when starting
            self.query_one("#logs-collapsible").collapsed = False
            
            self.run_worker(self.enable_apis(project_val))
            
    async def enable_apis(self, project_val: str) -> None:
        self.log_content = "" # Clear previous logs
        
        try:
            from services.project_service import enable_apis
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(None, lambda: enable_apis(project_val, self.write_log))
                
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update("[green]Status: APIs enabled successfully![/]")
            self.notify("APIs enabled successfully!", severity="information")
            
        except Exception as e:
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update(f"[red]Status: Error enabling APIs: {escape(str(e))}[/]")
            self.notify(f"Error enabling APIs: {e}", severity="error")
            self.write_log(f"Error: {e}\n")


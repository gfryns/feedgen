from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, LoadingIndicator, Select
from textual.containers import Vertical, Horizontal, Container
from validators import is_valid_dataset_name
import asyncio
import json
import subprocess
import yaml
import os


class DatasetScreen(ControlCenterBaseScreen):
    """Screen for Step 2: BigQuery Dataset Setup."""
    
    def __init__(self, state):
        super().__init__(state)
        
        self.regions = []
        self.models = []
        
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.regions = [(r['label'], r['value']) for r in config.get('regions', [])]
                self.models = [(m['label'], m['value']) for m in config.get('models', [])]
        except Exception as e:
            self.write_log(f"Error loading config.yaml: {e}\n")
            # Fallbacks just in case
            self.regions = [("EU", "EU"), ("US", "US")]
            self.models = [("Gemini 2.5 Flash", "gemini-2.5-flash")]
            self.prompt_titles = "prompts/titles.txt"
            self.prompt_descriptions = "prompts/descriptions.txt"
            
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                prompts_config = config.get('prompts', {})
                self.prompt_titles = prompts_config.get('titles', 'prompts/titles.txt')
                self.prompt_descriptions = prompts_config.get('descriptions', 'prompts/descriptions.txt')
        except Exception:
            self.prompt_titles = "prompts/titles.txt"
            self.prompt_descriptions = "prompts/descriptions.txt"
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("BigQuery Dataset Setup", id="title")
            
            with Horizontal():
                with Vertical(classes="col"):
                    yield Label("BigQuery Dataset Name:")
                    yield Input(value=self.state.get('dataset', 'feedgen_dataset'), id="dataset")
                with Vertical(classes="col"):
                    yield Label("Region:")
                    yield Select(self.regions, value=self.state.get('region', 'EU'), id="region")
            
            yield Label("Gemini Model Version:")
            yield Select(self.models, value=self.state.get('model', 'gemini-2.5-flash'), id="model")
            
            yield Input(placeholder="Enter custom model ID (e.g., gemini-1.0-pro)", id="custom-model")
            
            with Collapsible(title="What will be done?", collapsed=True):
                yield Static(
                    "The following operations will be performed:\n\n"
                    "1. Create BigQuery Dataset (if not exists)\n"
                    "2. Create Cloud Resource Connection (if not exists)\n"
                    "3. Grant IAM role to Connection Service Account\n"
                    "4. Create Gemini Model in BigQuery\n"
                    "5. Install Stored Procedures from generation.sql\n\n"
                    "💡 Note: Prompts are read from prompts/titles.txt and prompts/descriptions.txt. Customize them before deploying if needed!"
                )
                
            with Horizontal():
                yield Button("Save and Deploy", variant="success", id="save-deploy-btn")
                yield Button("Back to Menu", id="back-btn")
                
            yield LoadingIndicator(id="loading")
            yield Label("", id="status-label")
            
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
            
        yield Footer()
        
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model":
            if event.value == "other":
                self.query_one("#custom-model").styles.display = "block"
            else:
                self.query_one("#custom-model").styles.display = "none"
                
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-deploy-btn":
            dataset_val = self.query_one("#dataset").value
            region_val = self.query_one("#region").value
            model_val = self.query_one("#model").value
            
            if model_val == "other":
                model_val = self.query_one("#custom-model").value
                if not model_val:
                    self.notify("Custom model ID is required!", severity="error")
                    return
                    
            if not dataset_val:
                self.notify("Dataset Name is required!", severity="error")
                return
                
            if not is_valid_dataset_name(dataset_val):
                self.notify("Invalid Dataset Name. Use only letters, numbers, and underscores.", severity="error")
                return
                
            old_dataset = self.state.get('dataset')
            old_region = self.state.get('region')
            old_model = self.state.get('model')
            
            if dataset_val != old_dataset or region_val != old_region:
                # If raw_table is just a name, convert it to a full ID using the OLD project/dataset
                raw_table = self.state.get('raw_table')
                if raw_table and '.' not in raw_table and old_dataset:
                    project_val = self.state.get('project')
                    full_table_id = f"{project_val}.{old_dataset}.{raw_table}"
                    self.state.set('raw_table', full_table_id, save=False)
                    
                self.state.invalidate_descendants('dataset')
                
            if model_val != old_model:
                self.state.invalidate_descendants('procedures')
                
            self.state.set('dataset', dataset_val)
            self.state.set('region', region_val)
            self.state.set('model', model_val)
            
            self.query_one("#loading").styles.display = "block"
            self.query_one("#status-label").update("Status: Deploying...")
            self.query_one("#logs-collapsible").collapsed = False
            
            self.run_worker(self.deploy_all(dataset_val, region_val))
            
    def run_images(self, bucket_name: str) -> None:
        pass # Not used here!
        
    async def deploy_all(self, dataset_val: str, region_val: str) -> None:
        self.log_content = "" # Clear previous logs
        self.write_log("Starting deployment...\n")
        project_val = self.state.get('project')
        connection_val = self.state.get('connection', 'feedgen_connection')
        model_val = self.state.get('model', 'gemini-2.5-flash')
        
        try:
            from services.dataset_service import deploy_dataset_and_model
            loop = asyncio.get_running_loop()
            
            await loop.run_in_executor(
                None, 
                lambda: deploy_dataset_and_model(
                    project_val, dataset_val, region_val, connection_val, model_val, self.prompt_titles, self.prompt_descriptions, self.write_log
                )
            )

            self.state.set_step_status('infra', 'Completed', save=False)
            self.state.set_step_status('dataset', 'Completed', save=False)
            self.state.set_step_status('procedures', 'Completed')
            self.state.invalidate_descendants('procedures')
            
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update("[green]Status: Deployment completed successfully![/]")
            self.notify("Deployment completed!", severity="information")
            
        except Exception as e:
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update(f"[red]Status: Error during deployment: {e}[/]")
            self.notify(f"Error during deployment: {e}", severity="error")
            self.write_log(f"Error: {e}\n")

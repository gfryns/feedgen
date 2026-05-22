from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, LoadingIndicator, Select
from textual.containers import Vertical, Horizontal, Container
from textual.markup import escape
from validators import is_valid_dataset_name, is_valid_project_id
import asyncio
import yaml

class SetupScreen(ControlCenterBaseScreen):
    """Screen for combined Setup: Project, Dataset, Bucket."""
    
    def __init__(self, state):
        super().__init__(state)
        
        self.regions = []
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.regions = [(r['label'], r['value']) for r in config.get('regions', [])]
        except Exception as e:
            self.write_log(f"Error loading config.yaml: {e}\n")
            self.regions = [("EU", "EU"), ("US", "US")]
            
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Environment Setup", id="title")
            
            with Container(classes="card"):
                with Vertical():
                    yield Label("GCP Project ID:")
                    yield Input(value=self.state.get('project', ''), placeholder="Enter Project ID", id="project")
                    
                    with Horizontal():
                        with Vertical(classes="col"):
                            yield Label("BigQuery Dataset Name:")
                            yield Input(value=self.state.get('dataset', 'feedgen_dataset'), id="dataset")
                        with Vertical(classes="col"):
                            yield Label("Region:")
                            yield Select(self.regions, value=self.state.get('region', 'EU'), id="region")
                            
                    yield Label("GCS Bucket ID:")
                    # Get bucket name from config or state
                    default_bucket = self.state.get('bucket', '')
                    if not default_bucket:
                        try:
                            with open('config.yaml', 'r') as f:
                                config = yaml.safe_load(f)
                                buckets_config = config.get('buckets', {})
                                default_bucket = buckets_config.get('name', '')
                        except Exception:
                            pass
                    yield Input(value=default_bucket, placeholder="Enter Bucket ID", id="bucket")
                
            with Collapsible(title="What will be done?", collapsed=True):
                yield Static(
                    "The following operations will be performed:\n\n"
                    "1. Enable necessary APIs (Vertex AI, BigQuery, etc.)\n"
                    "2. Create BigQuery Dataset (if not exists)\n"
                    "3. Save configuration for Bucket\n"
                )
                
            with Horizontal():
                yield Button("Save and Deploy", variant="success", id="save-deploy-btn")
                yield Button("Cancel", id="back-btn")
                
            yield LoadingIndicator(id="loading")
            yield Label("", id="status-label")
            
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
            
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-deploy-btn":
            project_val = self.query_one("#project").value
            dataset_val = self.query_one("#dataset").value
            region_val = self.query_one("#region").value
            bucket_val = self.query_one("#bucket").value
                    
            if not project_val:
                self.notify("Project ID is required!", severity="error")
                return
            if not is_valid_project_id(project_val):
                self.notify("Invalid Project ID.", severity="error")
                return
            if not dataset_val:
                self.notify("Dataset Name is required!", severity="error")
                return
            if not is_valid_dataset_name(dataset_val):
                self.notify("Invalid Dataset Name.", severity="error")
                return
                
            # Save to state
            self.state.update_data({
                'project': project_val,
                'dataset': dataset_val,
                'region': region_val,
                'bucket': bucket_val
            })
            
            self.query_one("#loading").styles.display = "block"
            self.query_one("#status-label").update("Status: Deploying...")
            
            self.run_worker(self.deploy_all(project_val, dataset_val, region_val, bucket_val))
            
    async def deploy_all(self, project_val: str, dataset_val: str, region_val: str, bucket_val: str) -> None:
        self.log_content = ""
        self.write_log("Starting setup and deployment...\n")
        
        try:
            # 1. Enable APIs
            from services.project_service import enable_apis
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: enable_apis(project_val, self.write_log))
            
            # 2. Create Dataset
            from services.setup_service import create_dataset
            await loop.run_in_executor(
                None, 
                lambda: create_dataset(
                    project_val, dataset_val, region_val, log_cb=self.write_log
                )
            )
            
            # 3. Create Bucket (if not exists)
            if bucket_val:
                from services.setup_service import create_bucket
                await loop.run_in_executor(
                    None,
                    lambda: create_bucket(
                        project_val, bucket_val, region_val, log_cb=self.write_log
                    )
                )
            
            # Set step statuses
            self.state.set_step_status('config', 'Completed', save=False)
            self.state.set_step_status('infra', 'Completed', save=False)
            self.state.set_step_status('dataset', 'Completed', save=False)
            self.state.set_step_status('procedures', 'Completed') 
            
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update("[green]Status: Setup completed successfully![/]")
            self.notify("Setup completed!", severity="information")
            
        except Exception as e:
            self.query_one("#loading").styles.display = "none"
            self.query_one("#status-label").update(f"[red]Status: Error: {escape(str(e))}[/]")
            self.notify(f"Error: {e}", severity="error")
            self.write_log(f"Error: {e}\n")

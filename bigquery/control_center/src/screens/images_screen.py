from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, Checkbox, ProgressBar
from textual.containers import Vertical, Horizontal, Container
from services.bq_client import get_bq_client
import asyncio
import math
import services.images_service as img_srv
from messages import StateUpdateMessage, StatusUpdateMessage

class ImagesScreen(ControlCenterBaseScreen):
    """Screen for Step 3d: Image Processing."""
    
    def __init__(self, state):
        super().__init__(state)
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3d: Image Processing", id="title")
            
            image_col = self.state.get('image_col')
            
            if image_col == 'skip' or not image_col:
                yield Static(
                    "There is no image URL configured in the filtered table.\n"
                    "If you want to process images, please go back to Step 3b and map the Image URL column.",
                    id="msg"
                )
                with Horizontal():
                    yield Button("Cancel", id="back-btn")
            else:
                with Container(classes="card"):
                    yield Label("Image Processing Configuration", id="images-title")
                    yield Label(f"Image URL Column: {image_col}")
                    
                    yield Label("GCS Bucket Name:")
                    
                    project = self.state.get('project')
                    bucket = f"{project}-feedgen"
                    try:
                        import yaml
                        with open('config.yaml', 'r') as f:
                            config = yaml.safe_load(f)
                            buckets_config = config.get('buckets', {})
                            if buckets_config.get('name'):
                                bucket = buckets_config.get('name').replace("${project}", project)
                    except Exception:
                        pass
                        
                    yield Input(value=self.state.get('bucket', bucket), id="bucket")
                    
                    yield Label("Bucket Status: Loading...", id="bucket-info")
                
                yield Container(id="actions-container")
                
                yield Label("", id="status-label")
                yield ProgressBar(id="progress-bar")
                
                with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                    yield Log(id="process-logs")
                    yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_mount(self) -> None:
        """Load bucket info if URL is present."""
        image_col = self.state.get('image_col')
        if image_col and image_col != 'skip':
            self.run_worker(self.load_bucket_info)
            
    async def load_bucket_info(self) -> None:
        bucket_name = self.query_one("#bucket").value
        project = self.state.get('project')
        
        try:
            loop = asyncio.get_running_loop()
            count, total_size = await loop.run_in_executor(None, lambda: img_srv.get_bucket_stats(project, bucket_name))
            
            actions_container = self.query_one("#actions-container")
            for child in actions_container.children:
                await child.remove()
                
            if count is not None:
                size_str = self.format_size(total_size)
                self.query_one("#bucket-info", Label).update(f"Bucket Status: Contains {count} images ({size_str})")
                
                await actions_container.mount(
                    Horizontal(
                        Button("Run Image Processing", variant="success", id="run-btn"),
                        Button("Delete stored images", variant="error", id="delete-btn"),
                        Button("Cancel", id="back-btn")
                    )
                )
            else:
                self.query_one("#bucket-info", Label).update("Bucket Status: Not found.")
                await actions_container.mount(
                    Horizontal(
                        Button("Create Bucket", variant="primary", id="create-btn"),
                        Button("Cancel", id="back-btn")
                    )
                )
                
        except Exception as e:
            self.query_one("#bucket-info", Label).update(f"Bucket Status: Error checking ({e})")
            
    def format_size(self, size_bytes: int) -> str:
        if size_bytes == 0: return "0 B"
        size_name = ("B", "KB", "MB", "GB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bucket = self.query_one("#bucket").value
        
        if event.button.id == "run-btn":
            self.post_message(StateUpdateMessage('bucket', bucket))
            self.query_one("#progress-bar").styles.display = "block"
            self.run_worker(lambda: self.run_images(bucket), thread=True)
        elif event.button.id == "create-btn":
            self.run_worker(self.create_bucket(bucket))
        elif event.button.id == "delete-btn":
            self.run_worker(self.delete_images(bucket))
                
    async def create_bucket(self, bucket_name: str) -> None:
        self.notify("Creating bucket...")
        try:
            project = self.state.get('project')
            region = self.state.get('region', 'US')
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: img_srv.create_bucket(project, bucket_name, region))
            
            self.notify("Bucket created successfully!", severity="information")
            self.run_worker(self.load_bucket_info)
        except Exception as e:
            self.notify(f"Error creating bucket: {e}", severity="error")
            
    async def delete_images(self, bucket_name: str) -> None:
        self.query_one("#status-label", Label).update("[bold]Deleting images...[/]")
        self.notify("Deleting images...")
        self.query_one("#progress-bar").styles.display = "block"
        try:
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            loop = asyncio.get_running_loop()
            
            def progress_cb(total=None, progress=None, advance=None):
                if total is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").update, total=total, progress=progress)
                if advance is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").advance, advance)
                    
            count = await loop.run_in_executor(
                None, 
                lambda: img_srv.delete_images(project, dataset, bucket_name, progress_cb, lambda: self.app._exit)
            )
            
            self.notify(f"Deleted {count} images!", severity="information")
            self.query_one("#status-label", Label).update(f"[green]Done! Deleted {count} images.[/]")
            
            self.post_message(StatusUpdateMessage('images', 'Pending'))
            
            self.run_worker(self.load_bucket_info)
        except Exception as e:
            self.notify(f"Error deleting images: {e}", severity="error")
            
    def run_images(self, bucket_name: str) -> None:
        self.app.call_from_thread(self.query_one("#status-label", Label).update, "[bold]Processing images...[/]")
        """Runs in a background thread (sync worker)."""
        self.log_content = ""
        self.write_log("Starting image processing...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        connection_val = self.state.get('connection', 'feedgen_connection')
        region_val = self.state.get('region', 'EU')
        img_url_col = self.state.get('image_col')
        
        try:
            def progress_cb(total=None, progress=None, advance=None):
                if total is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").update, total=total, progress=progress)
                if advance is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").advance, advance)
                    
            result = img_srv.run_image_processing(
                project, dataset, bucket_name, connection_val, region_val, img_url_col,
                log_cb=self.write_log,
                progress_cb=progress_cb,
                is_cancelled=lambda: self.app._exit
            )
            
            if result.get('cancelled'):
                return
                
            report = (
                f"[bold]Image Processing Report:[/bold]\n"
                f"- Total URLs found: {result['total']}\n"
                f"- Successfully processed: {result['success']}\n"
                f"- Skipped (already exist): {result['skipped']}\n"
                f"- Failed: {result['total'] - result['success'] - result['skipped']}"
            )
            
            self.app.call_from_thread(self.query_one("#status-label", Label).update, report)
            self.app.call_from_thread(self.run_worker, self.load_bucket_info)
            self.app.call_from_thread(self.notify, "Image processing completed!", severity="information")
            
            self.post_message(StatusUpdateMessage('images', 'Completed'))
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.app.call_from_thread(self.notify, f"Error during image processing: {e}", severity="error")

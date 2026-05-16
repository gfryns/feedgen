from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, Checkbox, ProgressBar
from textual.containers import Vertical, Horizontal, Container
from screens.dataset_screen import get_bq_client
import asyncio
import os
import subprocess
import requests
from google.cloud import storage
import math
import time
import ssl
import certifi

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
                    yield Button("Back to Menu", id="back-btn")
            else:
                yield Label(f"Image URL Column: {image_col}")
                
                yield Label("GCS Bucket Name:")
                yield Input(value=self.state.get('bucket', f"{self.state.get('project')}-images"), id="bucket")
                
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
            storage_client = storage.Client(project=project)
            loop = asyncio.get_running_loop()
            
            def get_bucket_stats():
                try:
                    bucket = storage_client.get_bucket(bucket_name)
                    blobs = list(bucket.list_blobs(prefix="feedgen_images/"))
                    count = len(blobs)
                    total_size = sum(blob.size for blob in blobs)
                    return count, total_size
                except Exception:
                    return None, None
                    
            count, total_size = await loop.run_in_executor(None, get_bucket_stats)
            
            actions_container = self.query_one("#actions-container")
            for child in actions_container.children:
                await child.remove()
                
            if count is not None:
                size_str = self.format_size(total_size)
                self.query_one("#bucket-info", Label).update(f"Bucket Status: Contains {count} images ({size_str})")
                
                await actions_container.mount(
                    Horizontal(
                        Button("Delete stored images", variant="error", id="delete-btn"),
                        Button("Run Image Processing", variant="success", id="run-btn"),
                        Button("Back to Menu", id="back-btn")
                    )
                )
            else:
                self.query_one("#bucket-info", Label).update("Bucket Status: Not found.")
                await actions_container.mount(
                    Horizontal(
                        Button("Create Bucket", variant="primary", id="create-btn"),
                        Button("Back to Menu", id="back-btn")
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
            self.state.set('bucket', bucket)
            self.query_one("#logs-collapsible").collapsed = False
            self.query_one("#progress-bar").styles.display = "block"
            self.run_worker(lambda: self.run_images(bucket), thread=True)
        elif event.button.id == "create-btn":
            self.run_worker(self.create_bucket(bucket))
        elif event.button.id == "delete-btn":
            self.run_worker(self.delete_images(bucket))
                
    async def create_bucket(self, bucket_name: str) -> None:
        self.notify("Creating bucket...")
        try:
            storage_client = storage.Client(project=self.state.get('project'))
            region = self.state.get('region', 'US')
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: storage_client.create_bucket(bucket_name, location=region))
            
            self.notify("Bucket created successfully!", severity="information")
            self.run_worker(self.load_bucket_info)
        except Exception as e:
            self.notify(f"Error creating bucket: {e}", severity="error")
            
    async def delete_images(self, bucket_name: str) -> None:
        self.notify("Deleting images...")
        try:
            storage_client = storage.Client(project=self.state.get('project'))
            bucket = storage_client.get_bucket(bucket_name)
            
            loop = asyncio.get_running_loop()
            
            def do_delete():
                blobs = bucket.list_blobs(prefix="feedgen_images/")
                count = 0
                for blob in blobs:
                    blob.delete()
                    count += 1
                return count
                
            count = await loop.run_in_executor(None, do_delete)
            
            self.notify(f"Deleted {count} images!", severity="information")
            
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            client = get_bq_client(self.state)
            sql_drop = f"DROP TABLE IF EXISTS `{project}.{dataset}.Images`"
            await loop.run_in_executor(None, lambda: client.query(sql_drop).result())
            
            self.state.set_step_status('images', 'Pending')
            self.state.invalidate_descendants('images')
            
            self.run_worker(self.load_bucket_info)
        except Exception as e:
            self.notify(f"Error deleting images: {e}", severity="error")
            
    def run_images(self, bucket_name: str) -> None:
        """Runs in a background thread (sync worker)."""
        self.log_content = ""
        self.write_log("Starting image processing...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        insecure = self.state.insecure
        
        try:
            storage_client = storage.Client(project=project)
            bucket = storage_client.get_bucket(bucket_name)
            
            # 2. Fetch URLs
            client = get_bq_client(self.state)
            query = f"SELECT DISTINCT image_url FROM `{project}.{dataset}.InputFiltered` WHERE image_url IS NOT NULL"
            self.write_log(f"Fetching image URLs...\n")
            
            results = list(client.query(query).result())
            urls = [row['image_url'] for row in results]
            self.write_log(f"Found {len(urls)} unique image URLs.\n")
            
            self.write_log("Processing images sequentially...\n")
            
            # Reset progress bar to 0 and set total
            self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, total=len(urls), progress=0)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            success_count = 0
            
            for url in urls:
                filename = url.split('/')[-1]
                if not filename or '?' in filename:
                    import hashlib
                    filename = f"image_{hashlib.md5(url.encode()).hexdigest()}.jpg"
                    
                blob = bucket.blob(f"feedgen_images/{filename}")
                
                self.write_log(f"Downloading: {url}\n")
                
                try:
                    time.sleep(0.2) # Politeness
                    
                    if insecure:
                        response = requests.get(url, headers=headers, stream=True, timeout=10, verify=False)
                    else:
                        response = requests.get(url, headers=headers, stream=True, timeout=10, verify=certifi.where())
                        
                    response.raise_for_status()
                    blob.upload_from_file(response.raw, content_type=response.headers.get('Content-Type', 'image/jpeg'))
                    success_count += 1
                    self.write_log(f"Success: {filename}\n")
                except Exception as e:
                    self.write_log(f"Error {url}: {e}\n")
                    
                self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).advance, 1)
                    
            self.write_log(f"Successfully processed {success_count}/{len(urls)} images.\n")
            
            self.write_log("Creating external table in BigQuery...\n")
            
            connection_val = self.state.get('connection', 'feedgen_connection')
            region_val = self.state.get('region', 'EU')
            
            connection_path = f"{project}.{region_val.lower()}.{connection_val}"
            
            sql_external = f"""
            CREATE OR REPLACE EXTERNAL TABLE `{project}.{dataset}.Images`
            WITH CONNECTION `{connection_path}`
            OPTIONS(
              object_metadata = 'SIMPLE',
              uris = ['gs://{bucket_name}/feedgen_images/*'],
              max_staleness = INTERVAL 7 DAY,
              metadata_cache_mode = 'AUTOMATIC');
            """
            
            client.query(sql_external).result()
            self.write_log("External table 'Images' created.\n")
            
            self.state.set_step_status('images', 'Completed')
            self.state.invalidate_descendants('images')
            
            report = (
                f"[bold]Image Processing Report:[/bold]\n"
                f"- Total URLs found: {len(urls)}\n"
                f"- Successfully processed: {success_count}\n"
                f"- Failed: {len(urls) - success_count}"
            )
            
            self.app.call_from_thread(self.query_one("#status-label", Label).update, report)
            self.app.call_from_thread(self.run_worker, self.load_bucket_info)
            self.app.call_from_thread(self.notify, "Image processing completed!", severity="information")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.app.call_from_thread(self.notify, f"Error during image processing: {e}", severity="error")

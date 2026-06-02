from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Select, Collapsible, Log
from textual.containers import Vertical, Horizontal, Container
from services.bq_client import get_bq_client
import asyncio
import re
import subprocess
from messages import StateUpdateMessage, StatusUpdateMessage

class OptionsScreen(ControlCenterBaseScreen):
    """Screen for Step 3b: Filtering Options."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3b: Filtering Options", id="title")
            
            with Container(classes="card", id="mapping-card"):
                yield Label("Column Mapping", id="mapping-title")
                with Horizontal():
                    with Vertical(classes="col5"):
                        yield Label("Map ID Column:")
                        yield Container(id="id-col-container")
                    with Vertical(classes="col5"):
                        yield Label("Map Title Column:")
                        yield Container(id="title-col-container")
                    with Vertical(classes="col5"):
                        yield Label("Map Description Column:")
                        yield Container(id="desc-col-container")
                    with Vertical(classes="col5"):
                        yield Label("Map URL Column (Optional):")
                        yield Container(id="url-col-container")
                    with Vertical(classes="col5"):
                        yield Label("Map Image URL Column (Optional):")
                        yield Container(id="image-col-container")
            
            with Container(classes="card", id="options-card"):
                yield Label("Additional Options", id="options-title")
                yield Label("Additional Columns to include (comma-separated, or * for all):")
                yield Input(value=self.state.get('include_cols', 'brand,category'), id="include-cols")
                
                yield Label("Additional SQL clauses (e.g., WHERE clicks > 10):")
                yield Input(value=self.state.get('filters', ''), placeholder="WHERE ...", id="filters")
            
            with Horizontal():
                yield Button("Run Filter", variant="success", id="save-create-btn")
                yield Button("Back", id="back-btn")
                
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_mount(self) -> None:
        """Load schema and populate drop-downs."""
        self.run_worker(self.load_schema)
        
    async def load_schema(self) -> None:
        self.notify("Loading table schema...")
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        raw_table = self.state.get('raw_table')
        
        if '.' not in raw_table:
            full_ref = f"{project}.{dataset}.{raw_table}"
        else:
            full_ref = raw_table
            
        try:
            client = get_bq_client(self.state.get('project'))
            table = client.get_table(full_ref)
            cols = [field.name for field in table.schema]
            
            options = [(c, c) for c in cols]
            options_with_skip = [("None (Skip)", "skip")] + options
            
            # Guess columns
            id_guess = next((c for c in cols if re.search(r'(id|sku)', c, re.I)), cols[0])
            title_guess = next((c for c in cols if re.search(r'(title|name)', c, re.I)), cols[1] if len(cols)>1 else cols[0])
            desc_guess = next((c for c in cols if re.search(r'(desc|text|summary)', c, re.I)), cols[2] if len(cols)>2 else cols[0])
            url_guess = next((c for c in cols if re.search(r'(url|link|page)', c, re.I)), "skip")
            image_guess = next((c for c in cols if re.search(r'(img|image|photo|pic)', c, re.I)), "skip")
            
            id_val = self.state.get('id_col', id_guess)
            title_val = self.state.get('title_col', title_guess)
            desc_val = self.state.get('desc_col', desc_guess)
            url_val = self.state.get('url_col', url_guess)
            image_val = self.state.get('image_col', image_guess)
            
            # Validate that loaded values exist in options to avoid Textual crash
            valid_options = [o[1] for o in options]
            valid_options_with_skip = [o[1] for o in options_with_skip]
            
            if id_val not in valid_options: id_val = id_guess
            if title_val not in valid_options: title_val = title_guess
            if desc_val not in valid_options: desc_val = desc_guess
            
            if url_val not in valid_options_with_skip: url_val = "skip"
            if image_val not in valid_options_with_skip: image_val = "skip"
            
            await self.query_one("#id-col-container").mount(Select(options, value=id_val, id="id-col"))
            await self.query_one("#title-col-container").mount(Select(options, value=title_val, id="title-col"))
            await self.query_one("#desc-col-container").mount(Select(options, value=desc_val, id="desc-col"))
            
            await self.query_one("#url-col-container").mount(Select(options_with_skip, value=url_val, id="url-col"))
            await self.query_one("#image-col-container").mount(Select(options_with_skip, value=image_val, id="image-col"))
            
            self.notify("Schema loaded!", severity="information")
            
        except Exception as e:
            self.notify(f"Error loading schema: {e}", severity="error")
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-create-btn":
            include_cols = self.query_one("#include-cols").value
            filters = self.query_one("#filters").value
            
            id_col = self.query_one("#id-col").value
            title_col = self.query_one("#title-col").value
            desc_col = self.query_one("#desc-col").value
            url_col = self.query_one("#url-col").value
            image_col = self.query_one("#image-col").value
            
            self.post_message(StateUpdateMessage('include_cols', include_cols))
            self.post_message(StateUpdateMessage('filters', filters))
            self.post_message(StateUpdateMessage('id_col', id_col))
            self.post_message(StateUpdateMessage('title_col', title_col))
            self.post_message(StateUpdateMessage('desc_col', desc_col))
            self.post_message(StateUpdateMessage('url_col', url_col))
            self.post_message(StateUpdateMessage('image_col', image_col))
            
            self.run_worker(self.create_filtered_table(id_col, title_col, desc_col, url_col, image_col, include_cols, filters))
            
    async def create_filtered_table(self, id_col: str, title_col: str, desc_col: str, url_col: str, image_col: str, include_cols: str, filters: str) -> None:
        self.log_content = "" # Clear previous logs
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        raw_table = self.state.get('raw_table')
        
        try:
            from services.filter_service import create_filtered_table as run_filter
            loop = asyncio.get_running_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: run_filter(project, dataset, raw_table, id_col, title_col, desc_col, url_col, image_col, include_cols, filters, self.write_log)
            )
            
            self.post_message(StateUpdateMessage('filter_rows', result['num_rows']))
            self.post_message(StateUpdateMessage('filter_cols', result['num_cols']))
            self.post_message(StateUpdateMessage('filter_col_names', result['cols']))
            
            self.post_message(StatusUpdateMessage('filter', 'Completed'))
            
            self.notify("InputFiltered table created successfully!", severity="information")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error creating table: {e}", severity="error")

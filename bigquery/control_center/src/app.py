from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Label, ListView, ListItem, DataTable
from textual.containers import Horizontal, Vertical, Container
from textual import on
from textual.reactive import reactive
from state_manager import ControlCenterStateManager
from messages import StateUpdateMessage, StatusUpdateMessage, OngoingStateUpdateMessage
from screens.setup_screen import SetupScreen
from screens.source_screen import SourceScreen
from screens.options_screen import OptionsScreen
from screens.scraping_screen import ScrapingScreen
from screens.images_screen import ImagesScreen
from screens.examples_screen import ExamplesScreen
from screens.generation_screen import GenerationScreen
from screens.export_screen import ExportScreen
from action_logger import log_action

class StepListItem(ListItem):
    def __init__(self, step_id: str, base_text: str):
        super().__init__(id=step_id)
        self.step_id = step_id
        self.base_text = base_text
        self.static = Static(f"● {base_text}", markup=True)
        
    def compose(self) -> ComposeResult:
        yield self.static
        
    def on_mount(self) -> None:
        self.watch(self.app, "step_statuses", self.update_status)
        
    def update_status(self, step_statuses: dict) -> None:
        if not hasattr(self.app, 'state'):
            return
            
        status = self.app.get_computed_status(self.step_id, step_statuses)
        
        if status == 'Completed':
            status_str = "[#009E73]●[/]"
        elif status == 'Pending' or status == 'Processing':
            status_str = "[#E69F00]●[/]"
        elif 'Skipped' in status:
            status_str = "[#9E9E9E]●[/]"
        else:
            status_str = "[#D55E00]●[/]"
            
        self.static.update(f"{status_str} {self.base_text}")

class ControlCenterApp(App):
    """A Textual app for the FeedGen Control Center."""
    TITLE = "FeedGen"
    
    CSS_PATH = "styles.tcss"
    
    project_id = reactive("")
    dataset_name = reactive("")
    bucket_name = reactive("")
    step_statuses = reactive({})
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle Dark Mode")
    ]
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("WIZARD STEPS", id="sidebar-title")
                with ListView(id="steps-list"):
                    yield StepListItem("project", "1. Environment Setup")
                    yield ListItem(Static("2. Input Setup", markup=True), id="input_header")
                    yield StepListItem("source", "   2a. Source Feed")
                    yield StepListItem("filter", "   2b. Feed Filtering")
                    yield StepListItem("web", "   2c. Import Product Pages Infos")
                    yield StepListItem("images", "   2d. Import Product Images")
                    yield StepListItem("examples", "   2e. Select Examples")
                    yield StepListItem("gen", "3. Generation options")
                    yield StepListItem("export", "4. Export Feed")
            with Container(id="main-content"):
                yield Static(self.get_art(), id="dashboard-art", markup=True)
                yield Label("--- Dashboard ---", id="dashboard-title", classes="bold")
                yield DataTable(id="dashboard-table")
        yield Footer()
        
    def action_quit(self) -> None:
        """Handle quit action and set cancel flag."""
        self.is_cancelled = True
        self.workers.cancel_all()
        self.exit()

    def on_mount(self) -> None:
        """Initialize state manager and update sidebar."""
        import sys
        import os
        
        self.state = ControlCenterStateManager()
        self.is_cancelled = False
        self.state.debug = '--debug' in sys.argv
        
        # Populate reactive attributes
        self.project_id = self.state.get('project', '')
        self.dataset_name = self.state.get('dataset', 'feedgen_dataset')
        self.bucket_name = self.state.get('bucket', '')
        self.step_statuses = self.state.get('steps') or {}
        
        if self.state.debug:
            from action_logger import DEBUG_LOG_FILE
            if os.path.exists(DEBUG_LOG_FILE):
                os.remove(DEBUG_LOG_FILE)
            log_action("App Started", "Debug mode is ON")
            
        self.theme = self.state.get('theme', 'textual-dark')
        
        table = self.query_one("#dashboard-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Step", "Status", "Details")
        
        self.update_dashboard()
        
        # Update sidebar dots now that state is available
        for item in self.query(StepListItem):
            item.update_status(self.step_statuses)
            
        # Check for ongoing generation to resume
        if self.state.get_step_status('gen') == 'Processing':
            from screens.resume_modal import ResumeModal
            self.push_screen(ResumeModal(), self.on_resume_decision)
            
    def watch_step_statuses(self, new_value: dict) -> None:
        try:
            self.update_dashboard()
        except Exception: pass
        
    def watch_project_id(self, new_value: str) -> None:
        try:
            self.update_dashboard()
        except Exception: pass
        
    def watch_dataset_name(self, new_value: str) -> None:
        try:
            self.update_dashboard()
        except Exception: pass
        
    def watch_bucket_name(self, new_value: str) -> None:
        try:
            self.update_dashboard()
        except Exception: pass
        
    @on(StateUpdateMessage)
    def on_state_update(self, message: StateUpdateMessage) -> None:
        old_val = self.state.get(message.key)
        self.state.set(message.key, message.value)
        
        if message.key == 'raw_table' and message.value != old_val:
            self.state.invalidate_descendants('source')
            
        if message.key == 'project':
            self.project_id = message.value
        elif message.key == 'dataset':
            self.dataset_name = message.value
        elif message.key == 'bucket':
            self.bucket_name = message.value
            
    @on(StatusUpdateMessage)
    def on_status_update(self, message: StatusUpdateMessage) -> None:
        self.state.set_step_status(message.step, message.status)
        
        if message.status == 'Completed' and message.step in ['source', 'filter']:
            self.state.invalidate_descendants(message.step)
            self.step_statuses = self.state.get('steps') or {}
        else:
            self.step_statuses = {**self.step_statuses, message.step: message.status}
            
    @on(OngoingStateUpdateMessage)
    def on_ongoing_state_update(self, message: OngoingStateUpdateMessage) -> None:
        if message.clear:
            self.state.set('ongoing_generation', None)
        else:
            ongoing = self.state.get('ongoing_generation') or {}
            if message.job_ids:
                if 'job_ids' not in ongoing: ongoing['job_ids'] = {}
                ongoing['job_ids'].update(message.job_ids)
            if message.prefixes:
                if 'prefixes' not in ongoing: ongoing['prefixes'] = {}
                ongoing['prefixes'].update(message.prefixes)
            if message.total_rows is not None:
                ongoing['total_rows'] = message.total_rows
            self.state.set('ongoing_generation', ongoing)
        
    def on_resume_decision(self, resume: bool) -> None:
        if resume:
            self.route_to_step('gen')
        else:
            # Cancel existing jobs in background to avoid freezing UI
            def cancel_existing_jobs():
                ongoing = self.state.get('ongoing_generation')
                if ongoing:
                    job_ids = ongoing.get('job_ids', {})
                    from google.cloud import aiplatform
                    import re
                    
                    for t, job_id in job_ids.items():
                        try:
                            # Extract location from job_id
                            match = re.search(r'locations/([^/]+)/', job_id)
                            loc = match.group(1) if match else "global"
                            
                            aiplatform.init(project=self.project_id, location=loc)
                            job = aiplatform.BatchPredictionJob(job_id)
                            job.cancel()
                        except Exception:
                            pass
                            
            import threading
            threading.Thread(target=cancel_existing_jobs, daemon=True).start()
            
            from services.generation_service import update_ongoing_state
            update_ongoing_state(clear=True)
            self.post_message(StatusUpdateMessage('gen', 'Pending'))
        
    def get_computed_status(self, step: str, step_statuses: dict = None) -> str:
        """Calculate the display status based on state and dependencies."""
        def get_status(s):
            if step_statuses and s in step_statuses:
                return step_statuses[s]
            return self.state.get_step_status(s)
            
        if step == 'project':
            status = get_status('config')
            allowed = True
        elif step == 'dataset':
            status = 'Completed' if get_status('infra') == 'Completed' and get_status('procedures') == 'Completed' else 'Pending'
            allowed = get_status('config') == 'Completed'
        elif step == 'web':
            allowed, _ = self.state.check_dependency(step)
            if allowed:
                url_col = self.state.get('url_col')
                if url_col == 'skip' or not url_col:
                    return 'Skipped'
            status = get_status(step)
        elif step == 'images':
            allowed, _ = self.state.check_dependency(step)
            if allowed:
                image_col = self.state.get('image_col')
                if image_col == 'skip' or not image_col:
                    return 'Skipped'
            status = get_status(step)
        else:
            status = get_status(step)
            allowed, _ = self.state.check_dependency(step)
            
        if status == 'Completed':
            return 'Completed'
        elif status == 'Processing':
            return 'Processing'
        elif allowed:
            return 'Pending'
        else:
            return 'Not Ready'


                
    def get_color(self, status: str) -> str:
        if status == 'Completed': return "#009E73"
        if status == 'Pending' or status == 'Processing': return "#E69F00"
        if status == 'Not Ready': return "#D55E00"
        if 'Skipped' in status: return "#9E9E9E"
        return "white"
        
    def get_art(self) -> str:
        return """
███████╗███████╗███████╗██████╗  ██████╗ ███████╗███╗   ██╗
██╔════╝██╔════╝██╔════╝██╔══██╗██╔════╝ ██╔════╝████╗  ██║
█████╗  █████╗  █████╗  ██║  ██║██║  ███╗█████╗  ██╔██╗ ██║
██╔══╝  ██╔══╝  ██╔══╝  ██║  ██║██║   ██║██╔══╝  ██║╚██╗██║
██║     ███████╗███████╗██████╔╝╚██████╔╝███████╗██║ ╚████║
╚═╝     ╚══════╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝

                      in BigQuery
"""
        
    def update_dashboard(self) -> None:
        table = self.query_one("#dashboard-table", DataTable)
        table.clear()
        
        state = self.state
        project = self.project_id or 'N/A'
        dataset = self.dataset_name or 'N/A'
        
        steps_data = [
            ('project', '1. Environment Setup', f"Project: {project} | Dataset: {dataset}"),
            ('source', '2a. Source Feed', f"Raw Table: {state.get('raw_table', 'N/A')}"),
            ('filter', '2b. Feed Filtering', f"Rows: {state.get('filter_rows', 'N/A')} | Cols: {state.get('filter_cols', 'N/A')} ({', '.join(state.get('filter_col_names', [])[:3])}...)"),
            ('web', '2c. Import Product Pages', f"Selector: {state.get('selector', 'N/A')}"),
            ('images', '2d. Import Product Images', f"Bucket: {state.get('bucket', 'N/A')} | Folder: images"),
            ('examples', '2e. Select Examples', f"Count: {state.get('examples_count', 0)} | Source: {state.get('examples_source', 'N/A')}"),
            ('gen', '3. Generation options', f"Lang: {state.get('language', 'N/A')} | Out: {project}.{dataset}.{state.get('output_table', 'Output')}"),
            ('export', '4. Export Feed', "")
        ]
        
        for step_id, title, details in steps_data:
            status = self.get_computed_status(step_id)
            status_formatted = f"[{self.get_color(status)}]{status}[/]"
            table.add_row(title, status_formatted, details, key=step_id)
            
    def watch_theme(self, theme: str) -> None:
        """Watch for theme changes and save preference."""
        if hasattr(self, 'state') and self.state:
            self.state.set('theme', theme)
            
    def route_to_step(self, step_id: str) -> None:
        """Centralized routing logic."""
        if getattr(self.state, 'debug', False):
            log_action("Route Triggered", f"Routing to '{step_id}'")
            
        if step_id == 'input_header':
            return
            
        if step_id == 'project':
            self.push_screen(SetupScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'source':
            self.push_screen(SourceScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'filter':
            self.push_screen(OptionsScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'web':
            self.push_screen(ScrapingScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'images':
            self.push_screen(ImagesScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'examples':
            self.push_screen(ExamplesScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'gen':
            self.push_screen(GenerationScreen(self.state), callback=self.on_config_screen_result)
        elif step_id == 'export':
            self.push_screen(ExportScreen(self.state), callback=self.on_config_screen_result)
        
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle step selection from the sidebar."""
        self.route_to_step(event.item.id)
        
    @on(DataTable.RowSelected, "#dashboard-table")
    def on_dashboard_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle step selection from the dashboard table."""
        self.route_to_step(event.row_key.value)
            
    def on_config_screen_result(self, result: bool) -> None:
        """Callback when a screen is dismissed."""
        if getattr(self.state, 'debug', False):
            log_action("Screen Dismissed", f"Result: {result}")
        self.update_dashboard()

if __name__ == "__main__":
    app = ControlCenterApp()
    app.run()

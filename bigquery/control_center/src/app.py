from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Label, ListView, ListItem, DataTable
from textual.containers import Horizontal, Vertical, Container
from textual import on
from state_manager import ControlCenterStateManager
from screens.setup_screen import SetupScreen
from screens.source_screen import SourceScreen
from screens.options_screen import OptionsScreen
from screens.scraping_screen import ScrapingScreen
from screens.images_screen import ImagesScreen
from screens.examples_screen import ExamplesScreen
from screens.generation_screen import GenerationScreen
from screens.export_screen import ExportScreen
from action_logger import log_action

class ControlCenterApp(App):
    """A Textual app for the FeedGen Control Center."""
    TITLE = "FeedGen"
    
    CSS_PATH = "styles.tcss"
    
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
                    yield ListItem(Static("1. Environment Setup", markup=True), id="project")
                    yield ListItem(Static("2. Input Setup", markup=True), id="input_header")
                    yield ListItem(Static("   2a. Source Feed", markup=True), id="source")
                    yield ListItem(Static("   2b. Feed Filtering", markup=True), id="filter")
                    yield ListItem(Static("   2c. Import Product Pages Infos", markup=True), id="web")
                    yield ListItem(Static("   2d. Import Product Images", markup=True), id="images")
                    yield ListItem(Static("   2e. Select Examples", markup=True), id="examples")
                    yield ListItem(Static("3. Generation options", markup=True), id="gen")
                    yield ListItem(Static("4. Export to GMC", markup=True), id="export")
            with Container(id="main-content"):
                yield Static(self.get_art(), id="dashboard-art", markup=True)
                yield Label("--- Dashboard ---", id="dashboard-title", classes="bold")
                yield DataTable(id="dashboard-table")
        yield Footer()
        
    def action_quit(self) -> None:
        """Handle quit action and set cancel flag."""
        self.is_cancelled = True
        self.exit()

    def on_mount(self) -> None:
        """Initialize state manager and update sidebar."""
        import sys
        import os
        
        self.state = ControlCenterStateManager()
        self.is_cancelled = False
        self.state.debug = '--debug' in sys.argv
        
        if self.state.debug:
            from action_logger import DEBUG_LOG_FILE
            if os.path.exists(DEBUG_LOG_FILE):
                os.remove(DEBUG_LOG_FILE)
            log_action("App Started", "Debug mode is ON")
            
        self.theme = self.state.get('theme', 'textual-dark')
        
        table = self.query_one("#dashboard-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Step", "Status", "Details")
        
        self.update_sidebar_status()
        self.update_dashboard()
        
        # Check for ongoing generation to resume
        ongoing = self.state.get('ongoing_generation')
        if ongoing:
            from screens.resume_modal import ResumeModal
            self.push_screen(ResumeModal(), self.on_resume_decision)
            
    def on_resume_decision(self, resume: bool) -> None:
        if resume:
            self.state.set('auto_resume', True, save=False)
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
                            
                            aiplatform.init(project=self.state.get('project'), location=loc)
                            job = aiplatform.BatchPredictionJob(job_id)
                            job.cancel()
                        except Exception:
                            pass
                            
            import threading
            threading.Thread(target=cancel_existing_jobs, daemon=True).start()
            
            from services.generation_service import update_ongoing_state
            update_ongoing_state(clear=True)
        
    def get_computed_status(self, step: str) -> str:
        """Calculate the display status based on state and dependencies."""
        if step == 'project':
            status = self.state.get_step_status('config')
            allowed = True
        elif step == 'dataset':
            status = 'Completed' if self.state.get_step_status('infra') == 'Completed' and self.state.get_step_status('procedures') == 'Completed' else 'Pending'
            allowed = self.state.get_step_status('config') == 'Completed'
        elif step == 'web':
            allowed, _ = self.state.check_dependency(step)
            if allowed:
                url_col = self.state.get('url_col')
                if url_col == 'skip' or not url_col:
                    return 'Skipped'
            status = self.state.get_step_status(step)
        elif step == 'images':
            allowed, _ = self.state.check_dependency(step)
            if allowed:
                image_col = self.state.get('image_col')
                if image_col == 'skip' or not image_col:
                    return 'Skipped'
            status = self.state.get_step_status(step)
        else:
            status = self.state.get_step_status(step)
            allowed, _ = self.state.check_dependency(step)
            
        if status == 'Completed':
            return 'Completed'
        elif allowed:
            return 'Pending'
        else:
            return 'Not Ready'

    def update_sidebar_status(self) -> None:
        """Update the status labels in the sidebar."""
        base_texts = {
            'project': "1. Environment Setup",
            'source': "   2a. Source Feed",
            'filter': "   2b. Feed Filtering",
            'web': "   2c. Import Product Pages Infos",
            'images': "   2d. Import Product Images",
            'examples': "   2e. Select Examples",
            'gen': "3. Generation options",
            'export': "4. Export to GMC"
        }
        
        for step, base_text in base_texts.items():
            status = self.get_computed_status(step)
            
            if status == 'Completed':
                status_str = "[#009E73]●[/]"
            elif status == 'Pending':
                status_str = "[#E69F00]●[/]"
            elif 'Skipped' in status:
                status_str = "[#9E9E9E]●[/]"
            else:
                status_str = "[#D55E00]●[/]"
                
            try:
                item = self.query_one(f"#{step}", ListItem)
                static = item.query_one(Static)
                static.update(f"{status_str} {base_text}")
            except Exception:
                pass
                
    def get_color(self, status: str) -> str:
        if status == 'Completed': return "#009E73"
        if status == 'Pending': return "#E69F00"
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
        project = state.get('project', 'N/A')
        dataset = state.get('dataset', 'N/A')
        
        steps_data = [
            ('project', '1. Environment Setup', f"Project: {project} | Dataset: {dataset}"),
            ('source', '2a. Source Feed', f"Raw Table: {state.get('raw_table', 'N/A')}"),
            ('filter', '2b. Feed Filtering', f"Columns: {state.get('include_cols', 'N/A')}"),
            ('web', '2c. Import Product Pages', f"Selector: {state.get('selector', 'N/A')}"),
            ('images', '2d. Import Product Images', f"Bucket: {state.get('bucket', 'N/A')}"),
            ('examples', '2e. Select Examples', f"Sheet: {state.get('sheet_name', 'N/A')}"),
            ('gen', '3. Generation options', f"Lang: {state.get('language', 'N/A')} | Out: {project}.{dataset}.{state.get('output_table', 'Output')}"),
            ('export', '4. Export to GMC', f"Type: {state.get('feed_type', 'supplemental')} | Target: {project}.{dataset}.{state.get('export_table', 'ExportGMC')}")
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
        self.update_sidebar_status()
        self.update_dashboard()

if __name__ == "__main__":
    app = ControlCenterApp()
    app.run()

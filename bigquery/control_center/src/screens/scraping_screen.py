from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar
from textual.containers import Vertical, Horizontal, Container
from textual import on
import asyncio
from services.scraping_service import detect_css_selector, run_web_scraping

class ScrapingScreen(ControlCenterBaseScreen):
    """Screen for Step 3c: Web Scraping."""
    
    def __init__(self, state):
        super().__init__(state)
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 3c: Retrieve Product Page Info", id="title")
            
            url_col = self.state.get('url_col')
            
            if url_col == 'skip' or not url_col:
                yield Static(
                    "There is no product page URL configured in the filtered table.\n"
                    "If you want to enrich data with web scraping, please go back to Step 3b and map the URL column.",
                    id="msg"
                )
                with Horizontal():
                    yield Button("Back to Menu", id="back-btn")
            else:
                with Container(classes="card"):
                    yield Label("Scraping Configuration", id="scraping-title")
                    yield Label(f"Product Page URL Column: {url_col}")
                    
                    yield Label("CSS Selector for description:")
                    with Horizontal(id="selector-row"):
                        yield Input(value=self.state.get('selector', 'div[data-testid^="item-description"]'), id="selector")
                        yield Button("Auto-detect", id="detect-selector-btn")
                
                with Horizontal():
                    yield Button("Run Scraping", variant="success", id="run-btn")
                    yield Button("Back to Menu", id="back-btn")
                    
                yield ProgressBar(id="progress-bar")
                
                with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                    yield Log(id="process-logs")
                    yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
                    
                yield Label("", id="status-label")
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            selector = self.query_one("#selector").value
            self.state.set('selector', selector)
            self.query_one("#progress-bar").styles.display = "block"
            self.run_worker(self.run_scraping(selector))
        elif event.button.id == "detect-selector-btn":
            self.run_worker(self.detect_selector)
            

            
    async def detect_selector(self) -> None:
        self.notify("Auto-detecting selector...")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        url_col = self.state.get('url_col')
        
        sample_count = 5 # Default value
            
        if not url_col or url_col == 'skip':
            self.notify("No URL column mapped!", severity="error")
            return
            
        try:
            selector = await detect_css_selector(project, dataset, url_col, sample_count, self.write_log)
            
            self.query_one("#selector", Input).value = selector
            self.notify(f"Suggested selector: {selector}", severity="information")
            
        except Exception as e:
            self.notify(f"Error detecting selector: {e}", severity="error")
            
    async def run_scraping(self, selector: str) -> None:
        self.log_content = ""
        self.write_log("Starting web scraping...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        url_col = self.state.get('url_col')
        
        try:
            def progress_cb(total=None, progress=None, advance=None):
                if total is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").update, total=total, progress=progress)
                if advance is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar").advance, advance)
                    
            result = await run_web_scraping(
                project, dataset, selector, url_col,
                log_cb=self.write_log, 
                progress_cb=progress_cb, 
                is_cancelled=lambda: self.app._exit
            )
            
            if result.get('cancelled'):
                return
                
            # Update status label with report
            report = (
                f"[bold]Scraping Report:[/bold]\n"
                f"- Total URLs: {result['total']}\n"
                f"- Successfully loaded: {result['success']}\n"
                f"- Descriptions extracted: {result['extracted']}\n"
                f"- Failed to get data: {result['failed']}"
            )
            self.query_one("#status-label", Label).update(report)
            
            self.state.set_step_status('web', 'Completed')
            self.state.invalidate_descendants('web')
            
            self.notify("Web scraping completed successfully!", severity="information")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.notify(f"Error during scraping: {e}", severity="error")

from textual import on
from textual.screen import Screen
from textual.widgets import Button, Log
from textual.message import Message
import platform
import subprocess
import threading

class LogMessage(Message):
    """Custom message for safely writing logs from background threads."""
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()

class ControlCenterBaseScreen(Screen):
    """Base screen class providing common setup, logging, and callbacks."""
    
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.log_content = ""
        self._dismissed = False
        self._main_thread_id = threading.get_ident()

    @on(Button.Pressed, "#back-btn")
    def go_back(self, event: Button.Pressed) -> None:
        if getattr(self.state, 'debug', False):
            from action_logger import log_action
            log_action("BaseScreen go_back", f"Screen: {self.__class__.__name__} - _dismissed={self._dismissed}")
            
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(False)

    @on(Button.Pressed, "#copy-logs-btn")
    def copy_logs(self, event: Button.Pressed) -> None:
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(['pbcopy'], input=self.log_content.encode(), check=True)
            elif system == "Windows":
                subprocess.run(['clip'], input=self.log_content.encode(), check=True)
            elif system == "Linux":
                try:
                    subprocess.run(['xclip', '-selection', 'clipboard'], input=self.log_content.encode(), check=True)
                except FileNotFoundError:
                    subprocess.run(['xsel', '--clipboard', '--input'], input=self.log_content.encode(), check=True)
            else:
                raise Exception(f"Unsupported OS: {system}")
            self.notify("Logs copied to clipboard!", severity="information")
        except Exception as e:
            self.notify(f"Failed to copy logs: {e}", severity="error")

    def notify(self, message: str, *, severity: str = "information", timeout: float = 3.0, markup: bool = False) -> None:
        from textual.markup import escape
        if not markup:
            message = escape(str(message))
        super().notify(message, severity=severity, timeout=timeout)

    def write_log(self, text: str) -> None:
        """Write to the log widget safely, regardless of which thread calls this."""
        if threading.get_ident() == self._main_thread_id:
            # We are on the main thread, safe to write directly
            self._do_write_log(text)
        else:
            # We are on a background worker thread, post a message to the main thread
            self.post_message(LogMessage(text))

    def _do_write_log(self, text: str) -> None:
        """Internal method to actually write the log on the main thread."""
        try:
            logs = self.query_one("#process-logs", Log)
            logs.write(text)
        except Exception:
            pass
        self.log_content += text

    @on(LogMessage)
    def on_log_message(self, message: LogMessage) -> None:
        """Handle log messages sent from background threads."""
        self._do_write_log(message.text)

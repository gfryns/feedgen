from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Grid

class ResumeModal(ModalScreen[bool]):
    """Modal screen for confirming resume of ongoing generation."""
    
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("An ongoing generation was detected from a previous session.\nDo you want to resume polling and merging results?", id="question"),
            Button("Yes, Resume", variant="primary", id="resume"),
            Button("No, Start Fresh", variant="error", id="fresh"),
            id="dialog"
        )
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "resume":
            self.dismiss(True)
        else:
            self.dismiss(False)

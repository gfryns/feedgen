from textual.message import Message

class StateUpdateMessage(Message):
    """Message sent to the App to update global state."""
    def __init__(self, key: str, value: any) -> None:
        self.key = key
        self.value = value
        super().__init__()

class StatusUpdateMessage(Message):
    """Message sent to the App to update step status."""
    def __init__(self, step: str, status: str) -> None:
        self.step = step
        self.status = status
        super().__init__()

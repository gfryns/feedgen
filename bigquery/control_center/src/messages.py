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
class OngoingStateUpdateMessage(Message):
    """Message sent to the App to update ongoing generation state."""
    def __init__(self, job_ids=None, prefixes=None, total_rows=None, clear=False) -> None:
        self.job_ids = job_ids
        self.prefixes = prefixes
        self.total_rows = total_rows
        self.clear = clear
        super().__init__()

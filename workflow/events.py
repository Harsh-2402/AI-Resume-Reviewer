"""Progress events emitted from graph nodes via LangGraph's custom stream writer."""
import time
from dataclasses import asdict, dataclass, field
from typing import Any

BATCH = ""  # candidate_id for batch-level events


@dataclass
class ProgressEvent:
    candidate_id: str
    stage: str
    status: str  # started | completed | warning | failed | info
    message: str = ""
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def time_str(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))


def emit(candidate_id: str, stage: str, status: str, message: str = "", **data: Any) -> None:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 — outside a graph run (tests, scripts)
        return
    writer(ProgressEvent(candidate_id, stage, status, message, data=data).to_dict())


def parse_event(chunk: Any) -> ProgressEvent | None:
    """Accept raw stream chunks: dict, (namespace, dict) or (namespace, mode, dict)."""
    payload = chunk
    if isinstance(chunk, tuple):
        payload = chunk[-1]
    if isinstance(payload, dict) and {"candidate_id", "stage", "status"} <= payload.keys():
        return ProgressEvent(**payload)
    return None

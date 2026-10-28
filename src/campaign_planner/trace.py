import json
import re
from pathlib import Path
from uuid import uuid4

from .schemas import utc_now


def public(value):
    """Do not log transport headers, credentials, or hidden reasoning blocks."""
    if isinstance(value, dict):
        return {
            k: public(v)
            for k, v in value.items()
            if not any(
                x in k.lower() for x in ("api_key", "authorization", "reasoning", "thinking", "secret")
            )
        }
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    return value


class Trace:
    def __init__(self, path, mode):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mode, self.sequence = mode, 0
        self.trace_id = str(uuid4())
        # Output directories represent one invocation; rerunning explicitly replaces its evidence.
        self.path.write_text("", encoding="utf-8")

    def add(self, event, **data):
        self.sequence += 1
        item = public(
            dict(
                sequence=self.sequence,
                timestamp=utc_now().isoformat(),
                mode=self.mode,
                trace_id=self.trace_id,
                event=event,
                **data,
            )
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")

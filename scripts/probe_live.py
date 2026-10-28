"""Minimal, sanitized connectivity diagnostic; never prints keys or request headers."""

import difflib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from campaign_planner.runner import write_json
from campaign_planner.tools import PROJECT_ROOT


def sanitize(value):
    text = str(value)
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
        secret = os.getenv(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:800]


if __name__ == "__main__":
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        timeout=30,
        max_retries=0,
    )
    result = {"configured_model": os.environ["OPENAI_MODEL"]}
    try:
        response = client.chat.completions.create(
            model=os.environ["OPENAI_MODEL"], messages=[{"role": "user", "content": "仅回复OK"}], max_tokens=8
        )
        result.update(status="connected", response_present=bool(response.choices))
    except Exception as exc:
        body = getattr(exc, "body", {})
        result.update(
            status="failed",
            exception_type=type(exc).__name__,
            http_status=getattr(exc, "status_code", None),
            error=sanitize(body),
        )
        try:
            names = [m.id for m in client.models.list().data]
            result.update(
                listed_model_count=len(names),
                configured_model_listed=os.environ["OPENAI_MODEL"] in names,
                close_model_names=difflib.get_close_matches(os.environ["OPENAI_MODEL"], names, n=5),
            )
        except Exception as listing_exc:
            result["model_list_error"] = type(listing_exc).__name__
    client.close()
    write_json(Path("examples/live-initial/connection-diagnostic.json"), result)
    print(json.dumps(result, ensure_ascii=False))

"""Validation independent of the LLM; dates and money are never guessed."""

import hashlib
import json
import re
from datetime import datetime, timezone


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("时间必须是带时区的 ISO 8601 字符串")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("截止时间必须带时区")
    return result.astimezone(timezone.utc)


def utc_now():
    return datetime.now(timezone.utc)


def validate_request(raw, now, *, check_deadline=True):
    if not isinstance(raw, dict):
        return None, {"status": "invalid_input", "reason": "输入必须是 JSON 对象"}
    missing = [k for k in ("theme", "budget", "deadline") if raw.get(k) is None or raw.get(k) == ""]
    if missing:
        return None, {"status": "needs_input", "missing_fields": missing, "reason": "请补充必填信息"}
    try:
        if not isinstance(raw["theme"], str) or not raw["theme"].strip():
            raise ValueError("主题必须是非空字符串")
        if type(raw["budget"]) is not int or raw["budget"] < 0:
            raise ValueError("预算必须是非负整数模拟单位")
        deadline = parse_time(raw["deadline"])
        if check_deadline and deadline <= now:
            raise ValueError("截止时间已过")
        tier = raw.get("preferred_tier", "standard")
        if tier not in ("standard", "economy"):
            raise ValueError("preferred_tier 必须为 standard 或 economy")
        simplify = raw.get("allow_simplification", True)
        if type(simplify) is not bool:
            raise ValueError("allow_simplification 必须为布尔值")
        required = raw.get("required_channels", [])
        if not isinstance(required, list) or any(not isinstance(c, str) or not c.strip() for c in required):
            raise ValueError("required_channels 必须是非空字符串列表")
        normalized = dict(
            theme=raw["theme"].strip(),
            budget=raw["budget"],
            deadline=deadline.isoformat(),
            preferred_tier=tier,
            allow_simplification=simplify,
            required_channels=sorted(set(required)),
        )
        fingerprint = digest(normalized)
        request_id = raw.get("request_id", "campaign-" + fingerprint[:20])
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
            raise ValueError("request_id 仅允许 1～80 个字母、数字、下划线或短横线")
        return dict(normalized, request_id=request_id, fingerprint=fingerprint), None
    except (ValueError, TypeError, OverflowError) as exc:
        return None, {"status": "invalid_input", "reason": str(exc)}


class ExecutionLimit(Exception):
    pass


class BusinessError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details

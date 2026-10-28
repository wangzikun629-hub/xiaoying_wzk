"""Framework integration checks; these test doubles are not live-model evidence."""

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from campaign_planner.models import OfflineModel
from campaign_planner.runner import run


def test_full_endpoint_is_rejected_before_sending_requests(monkeypatch):
    from campaign_planner.models import live_model

    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-secret")
    monkeypatch.setenv("OPENAI_MODEL", "protocol-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://protocol-test.invalid/chat/completions")
    with pytest.raises(ValueError, match="API 根地址"):
        live_model()


class ForbiddenToolModel(OfflineModel):
    def _generate(self, messages, **kwargs):
        if self.engine.model_calls == 1:
            msg = AIMessage(
                content="测试非法工具边界",
                tool_calls=[
                    dict(name="execute", args={"command": "echo blocked"}, id="forbidden", type="tool_call")
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])
        return super()._generate(messages, **kwargs)


def test_unoffered_shell_call_is_rejected_and_counted(tmp_path, request_data, monkeypatch):
    import campaign_planner.models as models

    monkeypatch.setattr(models, "OfflineModel", ForbiddenToolModel)
    result = run(
        request_data,
        db=tmp_path / "state.sqlite",
        output=tmp_path / "evidence",
        now="2030-06-01T10:00:00+08:00",
    )
    assert result["status"] == "completed"
    events = [json.loads(line) for line in open(result["trace_path"], encoding="utf-8")]
    assert any(e["event"] == "tool_rejected" and e["tool"] == "execute" for e in events)
    assert result["tool_calls"] == len(result["attempts"]) + 1


def test_live_without_config_fails_explicitly_without_mock(tmp_path, request_data, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    result = run(
        request_data,
        mode="live",
        db=tmp_path / "live.sqlite",
        output=tmp_path / "evidence",
        now="2030-06-01T10:00:00+08:00",
    )
    assert result["status"] == "incomplete"
    assert result["reason"] == "model_unavailable"
    assert result["total_cost"] == result["model_calls"] == result["tool_calls"] == 0
    assert result["mode"] == "live"


def test_invalid_model_arguments_are_observed_not_crashes(tmp_path, request_data, monkeypatch):
    import campaign_planner.models as models

    class InvalidArgs(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.engine.model_calls == 1:
                message = AIMessage(
                    content="测试工具参数错误",
                    tool_calls=[
                        dict(name="estimate_plan", args={"invented": True}, id="invalid", type="tool_call")
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", InvalidArgs)
    result = run(
        request_data,
        db=tmp_path / "state.sqlite",
        output=tmp_path / "evidence",
        now="2030-06-01T10:00:00+08:00",
    )
    assert result["status"] == "completed"
    assert result["attempts"][0]["result"]["error_code"] == "invalid_tool_arguments"

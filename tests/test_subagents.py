"""YAML configuration and real framework delegation, with deterministic model doubles."""

import json

import pytest
import yaml
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from campaign_planner.models import OfflineModel, campaign_fields
from campaign_planner.runner import run
from campaign_planner.subagents import SubagentConfigError, load_subagents
from campaign_planner.tools import PROJECT_ROOT


def events(result):
    return [json.loads(line) for line in open(result["trace_path"], encoding="utf-8")]


def test_yaml_agents_really_run_with_shared_accounting(invoke):
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert [(r["agent"], r["status"]) for r in result["subagent_runs"]] == [
        ("content-writer", "succeeded"),
        ("plan-reviewer", "succeeded"),
    ]
    assert {a["agent"] for a in result["attempts"] if a["tool"] == "generate_script"} == {"content-writer"}
    assert {a["agent"] for a in result["attempts"] if a["tool"] != "generate_script"} == {"main"}
    trace = events(result)
    assert result["model_calls"] == len([e for e in trace if e["event"] == "model_request"])
    assert result["tool_calls"] == len(result["attempts"]) + len(result["subagent_runs"])
    assert {e["purpose"] for e in trace if e["event"] == "model_request"} >= {
        "decision",
        "subagent:content-writer",
        "subagent:plan-reviewer",
    }


def test_partial_child_result_returns_to_parent_without_double_charge(invoke):
    result = invoke(faults={"generate:social_copy": "once"})
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert [r["status"] for r in result["subagent_runs"] if r["role"] == "writer"] == ["partial", "succeeded"]
    attempts = [a for a in result["attempts"] if a["tool"] == "generate_script"]
    assert attempts[1]["arguments"]["deliverables"] == ["social_copy"]
    assert (
        result["tool_results"]["video_script"]["result_id"]
        == (attempts[0]["result"]["completed"][0]["result_id"])
    )
    assert [a["agent"] for a in result["attempts"] if a["tool"] == "estimate_plan"] == ["main"] * 3


@pytest.mark.parametrize(
    "limit,amount,cost",
    [("max_models", 4, 0), ("max_models", 5, 8), ("max_tools", 4, 0), ("max_tools", 5, 8)],
)
def test_child_and_parent_share_limits_and_resume(invoke, tmp_path, limit, amount, cost):
    first = invoke(**{limit: amount})
    assert first["status"] == "incomplete" and first["reason"] == "execution_limit"
    assert first["total_cost"] == cost
    assert first["model_calls" if limit == "max_models" else "tool_calls"] == amount
    second = run(resume_id=first["request_id"], db=tmp_path / "state.sqlite", output=tmp_path / "resume")
    assert second["status"] == "completed" and second["total_cost"] == 8
    for key, value in first["tool_results"].items():
        assert second["tool_results"][key] == value


def test_children_cannot_save_or_estimate(invoke, monkeypatch):
    import campaign_planner.models as models

    injected = set()

    class WrongToolModel(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.agent_role in ("writer", "reviewer") and self.agent_role not in injected:
                injected.add(self.agent_role)
                message = AIMessage(
                    content="边界测试",
                    tool_calls=[
                        dict(
                            name="estimate_plan" if self.agent_role == "writer" else "save_plan",
                            args={},
                            id=f"bad-{self.agent_role}",
                            type="tool_call",
                        )
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", WrongToolModel)
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    rejected = [(e["agent"], e["tool"]) for e in events(result) if e["event"] == "tool_rejected"]
    assert ("content-writer", "estimate_plan") in rejected
    assert ("plan-reviewer", "save_plan") in rejected
    assert all(a["agent"] == "main" for a in result["attempts"] if a["tool"] == "save_plan")


def test_unconfigured_framework_default_agent_is_rejected(invoke, monkeypatch):
    import campaign_planner.models as models

    class UnknownDelegate(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.engine.model_calls == 1:
                message = AIMessage(
                    content="边界测试",
                    tool_calls=[
                        dict(
                            name="task",
                            args=dict(subagent_type="general-purpose", description="不可委派"),
                            id="unknown",
                            type="tool_call",
                        )
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", UnknownDelegate)
    result = invoke()
    assert result["status"] == "completed"
    assert any(
        e["event"] == "tool_rejected" and e["result"]["error_code"] == "subagent_not_allowed"
        for e in events(result)
    )
    assert all(r["agent"] != "general-purpose" for r in result["subagent_runs"])


@pytest.mark.parametrize("renamed", [False, True])
def test_wrong_delegate_name_returns_choices_for_model_correction(invoke, monkeypatch, renamed):
    import campaign_planner.agent as agent
    import campaign_planner.models as models

    if renamed:
        specs = [spec.model_copy(update={"name": "custom-" + spec.role}) for spec in load_subagents()]
        monkeypatch.setattr(agent, "load_subagents", lambda: specs)

    injected = False
    corrected_from_feedback = False

    class CorrectingDelegate(OfflineModel):
        def _generate(self, messages, **kwargs):
            nonlocal injected, corrected_from_feedback
            quote = self.engine.state["quotes"].get(self.engine.state.get("active_quote"))
            target = None
            if self.agent_role == "main" and quote and quote["feasible"] and not injected:
                injected = True
                target = "writer"
            elif self.agent_role == "main" and injected and not corrected_from_feedback:
                previous = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
                feedback = json.loads(previous.content)
                assert feedback["error_code"] == "subagent_not_allowed"
                target = next(name for name, role in feedback["allowed_subagents"].items() if role == "writer")
                corrected_from_feedback = True
            if target:
                message = AIMessage(
                    content="根据可用名称委派，错误后依据工具反馈修正。",
                    tool_calls=[dict(
                        name="task", args=dict(subagent_type=target, description="生成当前缺失内容"),
                        id=f"delegate-{self.engine.model_calls}", type="tool_call",
                    )],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", CorrectingDelegate)
    result = invoke()
    assert corrected_from_feedback and result["status"] == "completed" and result["total_cost"] == 8
    rejected = [e for e in events(result) if e["event"] == "tool_rejected"]
    assert len(rejected) == 1 and rejected[0]["arguments"]["subagent_type"] == "writer"
    assert rejected[0]["result"]["allowed_subagents"] == {
        spec.name: spec.role for spec in (specs if renamed else load_subagents())
    }
    assert all(item["agent"] != "writer" for item in result["subagent_runs"])


def test_parent_cannot_skip_enabled_review_before_save(invoke, monkeypatch):
    import campaign_planner.models as models

    injected = False

    class SkipReview(OfflineModel):
        def _generate(self, messages, **kwargs):
            nonlocal injected
            state = self.engine.state
            if self.agent_role == "main" and state["results"] and not injected:
                injected = True
                message = AIMessage(
                    content="测试提前保存",
                    tool_calls=[
                        dict(
                            name="save_plan",
                            args=dict(
                                quote_id=state["active_quote"],
                                campaign=campaign_fields(self.engine.request["theme"]),
                            ),
                            id="skip-review",
                            type="tool_call",
                        )
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", SkipReview)
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert any(
        e["event"] == "tool_rejected" and e["result"]["error_code"] == "review_required"
        for e in events(result)
    )
    assert len([a for a in result["attempts"] if a["tool"] == "save_plan"]) == 1


def test_writer_summary_cannot_claim_unexecuted_work_succeeded(invoke, monkeypatch):
    import campaign_planner.models as models

    class LyingWriter(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.agent_role == "writer":
                message = AIMessage(content='{"status":"succeeded","message":"all done"}')
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", LyingWriter)
    result = invoke(max_models=9)
    assert result["status"] == "incomplete" and result["total_cost"] == 0
    assert result["reason"] == "execution_limit"
    assert result["tool_results"] == {} and result["saved_plan_id"] is None
    assert result["subagent_runs"] and all(r["status"] == "failed" for r in result["subagent_runs"])


def test_writer_returns_after_tool_without_requesting_another_model_summary(invoke, monkeypatch):
    import campaign_planner.models as models

    class ErrorAfterGeneration(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.agent_role == "writer" and self.engine.state["results"]:
                raise RuntimeError("child summary unavailable")
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", ErrorAfterGeneration)
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert [r["status"] for r in result["subagent_runs"] if r["role"] == "writer"] == ["succeeded"]
    assert len([a for a in result["attempts"] if a["tool"] == "generate_script"]) == 1
    assert set(result["tool_results"]) == {"video_script", "social_copy"}


def test_partial_writer_cannot_loop_on_stale_quote(invoke, monkeypatch):
    import campaign_planner.models as models

    class RetryingWriter(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.agent_role == "writer" and any(isinstance(m, ToolMessage) for m in messages):
                pytest.fail("writer must return its first tool observation to the parent")
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", RetryingWriter)
    result = invoke(faults={"generate:social_copy": "once"})
    assert result["status"] == "completed" and result["total_cost"] == 8
    attempts = [a for a in result["attempts"] if a["tool"] == "generate_script"]
    assert len(attempts) == 2
    assert attempts[0]["result"]["status"] == "partial"
    assert attempts[1]["arguments"]["deliverables"] == ["social_copy"]
    assert [r["status"] for r in result["subagent_runs"] if r["role"] == "writer"] == ["partial", "succeeded"]


def test_new_plan_invalidates_previous_review(invoke, monkeypatch):
    import campaign_planner.models as models

    injected = False

    class ReplanAfterReview(OfflineModel):
        def _generate(self, messages, **kwargs):
            nonlocal injected
            reviewed = any(r["role"] == "reviewer" for r in self.engine.state.get("subagent_runs", []))
            if self.agent_role == "main" and reviewed and not injected:
                injected = True
                message = AIMessage(
                    content="审查后产生新计划版本",
                    tool_calls=[
                        dict(name="estimate_plan", args=dict(tier="economy"), id="new-plan", type="tool_call")
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", ReplanAfterReview)
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    reviews = [r for r in result["subagent_runs"] if r["role"] == "reviewer"]
    assert len(reviews) == 2 and reviews[0]["fingerprint"] != reviews[1]["fingerprint"]


@pytest.mark.parametrize("role", ["writer", "reviewer"])
def test_child_model_error_is_returned_without_losing_success(invoke, monkeypatch, role):
    import campaign_planner.models as models

    injected = False

    class OnceErrorModel(OfflineModel):
        def _generate(self, messages, **kwargs):
            nonlocal injected
            if self.agent_role == role and not injected:
                injected = True
                raise RuntimeError("test model unavailable")
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr(models, "OfflineModel", OnceErrorModel)
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert [r["status"] for r in result["subagent_runs"] if r["role"] == role] == ["failed", "succeeded"]
    assert len([a for a in result["attempts"] if a["tool"] == "generate_script"]) == 1


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"subagents": "wrong"},
        {"subagents": [], "unknown": True},
        {
            "subagents": [
                dict(name="bad", role="writer", description="x", system_prompt="x", tools=["save_plan"])
            ]
        },
        {
            "subagents": [
                dict(name="bad", role="reviewer", description="x", system_prompt="x", tools=["execute"])
            ]
        },
        {"subagents": [dict(name="bad", role="writer", description="x", system_prompt="x", tools=[])]},
        {"subagents": [dict(name="bad", role="other", description="x", system_prompt="x", tools=[])]},
        {"subagents": [dict(name="bad", role="reviewer", description=" ", system_prompt="x", tools=[])]},
    ],
)
def test_invalid_yaml_schema_is_rejected(tmp_path, data):
    path = tmp_path / "subagents.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(SubagentConfigError):
        load_subagents(path)


def test_duplicate_names_and_roles_are_rejected(tmp_path):
    data = yaml.safe_load((PROJECT_ROOT / "config/subagents.yaml").read_text(encoding="utf-8"))
    data["subagents"].append(data["subagents"][0])
    path = tmp_path / "subagents.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(SubagentConfigError):
        load_subagents(path)


def test_malformed_yaml_and_unsafe_tags_are_rejected(tmp_path):
    path = tmp_path / "subagents.yaml"
    for source in ("subagents: [", "!!python/object/apply:os.system ['echo forbidden']"):
        path.write_text(source, encoding="utf-8")
        with pytest.raises(SubagentConfigError):
            load_subagents(path)


def test_invalid_config_stops_before_any_call(invoke, tmp_path, monkeypatch):
    import campaign_planner.agent as agent

    monkeypatch.setattr(agent, "load_subagents", lambda: load_subagents(tmp_path / "missing.yaml"))
    result = invoke()
    assert result["status"] == "incomplete" and result["reason"] == "invalid_subagent_config"
    assert result["model_calls"] == result["tool_calls"] == result["total_cost"] == 0


@pytest.mark.parametrize("disabled", [set(), {"writer"}, {"reviewer"}, {"writer", "reviewer"}])
def test_yaml_renaming_and_enabled_switches_work(invoke, tmp_path, monkeypatch, disabled):
    import campaign_planner.agent as agent

    data = yaml.safe_load((PROJECT_ROOT / "config/subagents.yaml").read_text(encoding="utf-8"))
    for spec in data["subagents"]:
        spec["enabled"] = spec["role"] not in disabled
        spec["name"] = "custom-" + spec["role"]
    path = tmp_path / "subagents.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(agent, "load_subagents", lambda: load_subagents(path))
    result = invoke()
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert {r["agent"] for r in result["subagent_runs"]} == {
        "custom-" + role for role in {"writer", "reviewer"} - disabled
    }

import json

import pytest

from campaign_planner.runner import run
from campaign_planner.storage import Storage


def test_budget_replanning_uses_observation_and_reestimates(invoke):
    result = invoke()
    assert result["status"] == "completed"
    quotes = [a["result"] for a in result["attempts"] if a["tool"] == "estimate_plan"]
    assert [(q["total_cost"], q["budget_ok"]) for q in quotes] == [(12, False), (8, True)]
    assert result["total_cost"] == 8 == sum(r["cost"] for r in result["tool_results"].values())
    assert all(s["status"] == "succeeded" for s in result["task_plan"]["steps"])
    assert len(result["plan_history"]) == 2


def test_normal_standard_completion(invoke):
    result = invoke({"budget": 20})
    assert result["status"] == "completed"
    assert result["total_cost"] == 12
    assert result["elapsed_minutes"] == 123  # search 1 + estimate 1 + generation 120 + save 1
    assert len(result["tool_results"]) == 3


@pytest.mark.parametrize("field", ["budget", "deadline"])
def test_missing_fields_stop_before_model_or_tool(invoke, field):
    result = invoke({field: None})
    assert result["status"] == "needs_input"
    assert field in result["missing_fields"]
    assert result["model_calls"] == result["tool_calls"] == 0


@pytest.mark.parametrize("budget", [True, -1, 1.5, "10"])
def test_invalid_money(invoke, budget):
    assert invoke({"budget": budget})["status"] == "invalid_input"


def test_no_feasible_budget_has_gap_and_no_generation(invoke):
    result = invoke({"budget": 5})
    assert result["status"] == "incomplete"
    assert result["reason"] == "budget_infeasible"
    assert result["budget_gap"] == 3
    assert result["total_cost"] == 0
    assert not any(a["tool"] in ("generate_script", "save_plan") for a in result["attempts"])


def test_budget_gap_uses_candidates_that_satisfy_required_channels(invoke):
    result = invoke(
        {"preferred_tier": "economy", "required_channels": ["校园公众号", "短视频平台"]}
    )
    assert result["status"] == "incomplete"
    assert result["reason"] == "budget_infeasible"
    assert result["budget_gap"] == 2
    assert result["total_cost"] == 0
    assert result["saved_plan_id"] is None


def test_batch_failure_does_not_fail_unattempted_items(invoke):
    result = invoke(
        {"preferred_tier": "economy"}, faults={"generate:video_script": "always"}, max_models=4
    )
    assert result["reason"] == "execution_limit"
    attempts = [a for a in result["attempts"] if a["tool"] == "generate_script"]
    assert len(attempts) == 1
    assert [f["deliverable"] for f in attempts[0]["result"]["failures"]] == ["video_script"]
    statuses = {step["step_id"]: step["status"] for step in result["task_plan"]["steps"]}
    assert statuses["video_script"] == "failed"
    assert statuses["social_copy"] == "pending"
    assert statuses["save"] == "blocked"
    assert result["total_cost"] == 0


def test_once_failure_preserves_partial_results_and_does_not_double_charge(invoke):
    result = invoke({"preferred_tier": "economy"}, faults={"generate:social_copy": "once"})
    attempts = [a for a in result["attempts"] if a["tool"] == "generate_script"]
    assert result["status"] == "completed"
    assert result["total_cost"] == 8
    assert [a["status"] for a in attempts] == ["partial", "succeeded"]
    first_video = attempts[0]["result"]["completed"][0]
    assert result["tool_results"]["video_script"]["result_id"] == first_video["result_id"]
    assert attempts[1]["arguments"]["deliverables"] == ["social_copy"]
    assert [a["result"]["cost_delta"] for a in attempts] == [4, 4]


def test_persistent_primary_failure_model_switches_backend(invoke):
    result = invoke({"preferred_tier": "economy"}, faults={"primary": "always"})
    assert result["status"] == "completed"
    assert [p["backend"] for p in result["plan_history"]] == ["primary", "backup"]
    assert result["total_cost"] == 8
    assert all(r["origin"] == "template" for r in result["tool_results"].values())
    assert any(a["status"] == "failed" for a in result["attempts"])


def test_identical_three_fields_are_idempotent(invoke):
    first, second = invoke(), invoke()
    assert first["saved_plan_id"] == second["saved_plan_id"]
    assert second["cached"]
    assert second["model_calls"] == second["tool_calls"] == 0
    assert first["attempts"] == second["attempts"]


def test_explicit_new_id_creates_independent_campaign(invoke):
    first = invoke({"request_id": "campaign-first"})
    second = invoke({"request_id": "campaign-second"})
    assert first["status"] == second["status"] == "completed"
    assert first["saved_plan_id"] != second["saved_plan_id"]
    assert first["total_cost"] == second["total_cost"] == 8
    assert not second["cached"]


def test_id_conflict_does_not_overwrite_saved_state(invoke):
    first = invoke({"request_id": "same-id"})
    second = invoke({"request_id": "same-id", "budget": 20})
    assert second["reason"] == "request_id_conflict"
    third = invoke({"request_id": "same-id"})
    assert third["saved_plan_id"] == first["saved_plan_id"]
    assert third["total_cost"] == 8


def test_zero_materials_stops_without_fabrication(invoke):
    result = invoke({"theme": "深海潜航设备交流"})
    assert result["status"] == "incomplete"
    assert result["reason"] == "no_materials"
    assert result["total_cost"] == 0
    assert result["tool_results"] == {}


def test_partial_materials_model_removes_only_optional_work(invoke):
    result = invoke({"theme": "校园环保旧物回收", "budget": 20})
    assert result["status"] == "completed"
    assert [p["tier"] for p in result["plan_history"]] == ["standard", "economy"]
    assert set(result["tool_results"]) == {"video_script", "social_copy"}


def test_user_can_forbid_simplification(invoke):
    result = invoke({"allow_simplification": False})
    assert result["status"] == "incomplete"
    assert result["budget_gap"] == 2
    assert result["total_cost"] == 0


def test_time_infeasible_does_not_execute_generation(invoke):
    result = invoke({"deadline": "2030-06-01T10:30:00+08:00"})
    assert result["status"] == "incomplete"
    assert result["reason"] == "deadline_infeasible"
    assert result["time_gap_minutes"] > 0
    assert result["total_cost"] == 0


@pytest.mark.parametrize("limit_type", ["max_models", "max_tools"])
def test_execution_limits_preserve_successful_retrieval(invoke, limit_type):
    result = invoke(**{limit_type: 1})
    assert result["status"] == "incomplete"
    assert result["reason"] == "execution_limit"
    assert result["attempts"][0]["status"] == "succeeded"
    assert result["model_calls" if limit_type == "max_models" else "tool_calls"] == 1


def test_save_failure_retains_scripts_and_can_resume(invoke, tmp_path):
    db = tmp_path / "state.sqlite"
    first = invoke({"preferred_tier": "economy"}, faults={"save": "always"})
    assert first["status"] == "incomplete"
    assert first["reason"] == "save_failed"
    assert first["total_cost"] == 8
    second = run(mode="mock", db=db, output=tmp_path / "resume", resume_id=first["request_id"])
    assert second["status"] == "completed"
    assert second["total_cost"] == 8
    assert second["tool_results"] == first["tool_results"]
    new_attempts = second["attempts"][len(first["attempts"]) :]
    assert [a["tool"] for a in new_attempts] == ["save_plan"]


def test_partial_generation_survives_restart_and_resume(invoke, tmp_path):
    first = invoke({"preferred_tier": "economy"}, faults={"generate:social_copy": "always"}, max_models=6)
    assert first["status"] == "incomplete"
    assert first["total_cost"] == 4
    video = first["tool_results"]["video_script"]
    second = run(
        mode="mock", db=tmp_path / "state.sqlite", output=tmp_path / "resume", resume_id=first["request_id"]
    )
    assert second["status"] == "completed"
    assert second["total_cost"] == 8
    assert second["tool_results"]["video_script"] == video
    assert second["elapsed_minutes"] > first["elapsed_minutes"]


def test_cannot_reset_simulated_clock_on_resume(invoke, tmp_path):
    first = invoke(max_models=1)
    result = run(
        db=tmp_path / "state.sqlite",
        output=tmp_path / "bad-clock",
        resume_id=first["request_id"],
        now="2030-06-01T09:00:00+08:00",
    )
    assert result["reason"] == "resume_clock_cannot_reset"


def test_live_does_not_reuse_mock_state(invoke, tmp_path):
    result = invoke()
    request = {k: v for k, v in result["request"].items() if k != "fingerprint"}
    live = run(
        request,
        db=tmp_path / "state.sqlite",
        output=tmp_path / "live",
        mode="live",
        now="2030-06-01T10:00:00+08:00",
    )
    assert live["reason"] == "evidence_mode_conflict"
    assert live["model_calls"] == 0


def test_saved_plan_is_authoritative_and_export_has_actual_content(invoke):
    result = invoke()
    store = Storage(result["saved_store"])
    try:
        saved = store.plan(result["request_id"])
        assert saved["total_cost"] == result["total_cost"]
        assert all(s["status"] == "succeeded" for s in saved["task_plan"]["steps"])
    finally:
        store.close()
    events = [json.loads(line) for line in open(result["trace_path"], encoding="utf-8")]
    assert any(e["event"] == "model_decision" for e in events)
    assert {e["mode"] for e in events} == {"mock"}

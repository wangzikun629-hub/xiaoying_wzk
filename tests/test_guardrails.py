import json
from datetime import timedelta

import pytest

from campaign_planner.models import campaign_fields
from campaign_planner.runner import decide_incomplete, snapshot
from campaign_planner.schemas import parse_time, validate_request
from campaign_planner.storage import BusyRequest, Storage
from campaign_planner.tools import Engine
from campaign_planner.trace import Trace


@pytest.fixture
def engine(tmp_path, request_data):
    now = parse_time("2030-06-01T10:00:00+08:00")
    request, _ = validate_request(request_data, now)
    state = dict(
        request=request,
        status="running",
        mode="mock",
        clock_mode="simulated",
        clock_anchor=now.isoformat(),
        elapsed_minutes=0,
        spent=0,
        results={},
        materials={},
        attempts=[],
        plans=[],
        quotes={},
        fault_counts={},
        active_run_id="test",
        runs=[],
    )
    store = Storage(tmp_path / "guard.sqlite")
    store.put(state)
    e = Engine(store, state, Trace(tmp_path / "trace.jsonl", "mock"))
    e.execute("search_materials", {"query": request["theme"]})
    yield e
    store.close()


def quote(engine, **kwargs):
    return engine.execute("estimate_plan", dict(tier="economy", **kwargs))["quote_id"]


def test_over_budget_quote_cannot_be_executed(engine):
    q = engine.execute("estimate_plan", {"tier": "standard"})
    assert q["status"] == "succeeded" and not q["budget_ok"]
    rejected = engine.execute("generate_script", dict(quote_id=q["quote_id"], deliverables=["video_script"]))
    assert rejected["error_code"] == "infeasible_quote"
    assert engine.state["spent"] == 0


def test_generation_requires_quote_and_rejects_early_save(engine):
    assert (
        engine.execute("generate_script", dict(quote_id="invented", deliverables=["video_script"]))[
            "error_code"
        ]
        == "stale_quote"
    )
    q = quote(engine)
    assert (
        engine.execute("save_plan", dict(quote_id=q, campaign=campaign_fields("test")))["error_code"]
        == "dependency_missing"
    )
    assert engine.storage.plan(engine.request["request_id"]) is None


def test_quote_is_invalidated_by_changed_rules(engine):
    q = quote(engine)
    engine.rules["deliverables"]["video_script"]["cost"] = 100
    result = engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script"]))
    assert result["error_code"] == "stale_quote"
    assert engine.state["spent"] == 0


def test_old_plan_quote_cannot_be_used_after_replanning(engine):
    old = quote(engine)
    quote(engine, backend="backup")
    result = engine.execute("generate_script", dict(quote_id=old, deliverables=["video_script"]))
    assert result["error_code"] == "stale_quote"


def test_cannot_generate_result_twice_or_add_an_unquoted_item(engine):
    q = quote(engine)
    invalid = engine.execute("generate_script", dict(quote_id=q, deliverables=["channel_adaptation"]))
    assert invalid["error_code"] == "invalid_deliverables"
    engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script"]))
    q = quote(engine)
    duplicate = engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script"]))
    assert duplicate["error_code"] == "already_completed"
    assert engine.state["spent"] == 4


def test_required_channel_cannot_be_dropped(engine):
    engine.request["required_channels"] = ["校园公众号"]
    result = engine.execute("estimate_plan", dict(tier="economy", channels=["短视频平台"]))
    assert result["error_code"] == "scope_violation"


def test_unknown_channel_has_no_feasible_quote(engine):
    result = engine.execute("estimate_plan", dict(tier="economy", channels=["不存在的渠道"]))
    assert not result["feasible"]
    assert result["missing_channels"] == ["不存在的渠道"]
    assert result["minimum_budget_gap"] is None


def test_economy_multi_channel_is_not_a_valid_cheaper_plan(engine):
    result = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号", "短视频平台"]))
    assert result["budget_ok"]
    assert not result["scope_ok"] and not result["feasible"]
    assert result["scope_issues"] == ["economy_requires_one_channel"]
    rejected = engine.execute(
        "generate_script", dict(quote_id=result["quote_id"], deliverables=["video_script"])
    )
    assert rejected["error_code"] == "infeasible_quote"
    assert engine.state["spent"] == 0


def test_budget_alternative_explicitly_reduces_optional_channels(engine):
    result = engine.execute("estimate_plan", dict(tier="standard"))
    alternative = next(c for c in result["alternatives"] if c["tier"] == "economy")
    assert len(result["plan"]["channels"]) >= 2
    assert len(alternative["channels"]) == 1 and alternative["total_cost"] == 8
    assert result["minimum_budget_gap"] == 0


def test_hard_multi_channel_requirement_cannot_be_silently_simplified(engine):
    engine.request["required_channels"] = ["校园公众号", "短视频平台"]
    result = engine.execute("estimate_plan", dict(tier="standard"))
    assert result["minimum_budget_gap"] == 2
    assert not any(c["tier"] == "economy" for c in result["alternatives"])


def test_save_rechecks_clock_not_only_quote(engine):
    q = quote(engine)
    engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script", "social_copy"]))
    engine.state["clock_anchor"] = (parse_time(engine.request["deadline"]) - timedelta(minutes=1)).isoformat()
    result = engine.execute("save_plan", dict(quote_id=q, campaign=campaign_fields("test")))
    assert result["error_code"] == "constraint_changed"
    assert engine.storage.plan(engine.request["request_id"]) is None


def test_database_commit_failure_does_not_create_false_success(engine, monkeypatch):
    q = quote(engine)
    engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script", "social_copy"]))

    def fail(*args):
        raise OSError("injected disk error")

    monkeypatch.setattr(engine.storage, "save_plan", fail)
    result = engine.execute("save_plan", dict(quote_id=q, campaign=campaign_fields("test")))
    assert result["status"] == "failed"
    assert engine.state["status"] != "completed"
    assert engine.state["attempts"][-1]["status"] == "failed"
    assert engine.state["spent"] == 8
    assert engine.storage.plan(engine.request["request_id"]) is None


def test_invalid_citations_cannot_be_saved_as_success(engine):
    engine.generator = lambda *args: dict(
        text="这是足够长但引用了不存在素材的脚本内容，必须被拒绝。", material_ids=["invented"]
    )
    q = quote(engine)
    result = engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script"]))
    assert result["status"] == "failed"
    assert engine.state["results"] == {}
    assert engine.state["spent"] == 0


def test_all_affordable_alternatives_too_slow_reports_time_not_current_budget(engine):
    engine.request["deadline"] = "2030-06-01T10:30:00+08:00"
    result = engine.execute("estimate_plan", dict(tier="standard"))
    assert not result["budget_ok"] and result["minimum_budget_gap"] == 0
    assert decide_incomplete(engine) == "deadline_infeasible"
    output = snapshot(engine.state, engine.storage)
    assert output["time_gap_minutes"] == 33
    assert output["current_plan_time_gap_minutes"] == 93


def test_campaign_text_cannot_expand_channels_while_reusing_economy_results(engine):
    q = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号"]))["quote_id"]
    engine.execute("generate_script", dict(quote_id=q, deliverables=["video_script", "social_copy"]))
    ids = {k: r["result_id"] for k, r in engine.state["results"].items()}
    campaign = campaign_fields("毕业季")
    campaign["schedule"] = "先发布校园公众号，再安排校内社群转发。"
    rejected = engine.execute("save_plan", dict(quote_id=q, campaign=campaign))
    assert rejected["error_code"] == "scope_violation"
    assert engine.storage.plan(engine.request["request_id"]) is None
    corrected = engine.execute("save_plan", dict(quote_id=q, campaign=campaign_fields("毕业季")))
    assert corrected["status"] == "succeeded"
    assert engine.state["spent"] == 8
    assert {k: r["result_id"] for k, r in engine.state["results"].items()} == ids


def test_same_request_cannot_run_in_two_process_slots(engine):
    other = Storage(engine.storage.path)
    try:
        with engine.storage.request_lock("same"):
            with pytest.raises(BusyRequest):
                with other.request_lock("same"):
                    pytest.fail("second lock must not succeed")
    finally:
        other.close()


def test_trace_redacts_credentials_and_hidden_reasoning(engine):
    engine.trace.add("test", api_key="secret", reasoning="private", text="sk-abcdefghijklmnop")
    last = json.loads(engine.trace.path.read_text(encoding="utf-8").splitlines()[-1])
    assert "api_key" not in last and "reasoning" not in last
    assert last["text"] == "[REDACTED]"

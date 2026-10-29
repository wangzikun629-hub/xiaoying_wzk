"""Regression coverage for consistency across plan changes and finalization."""

import copy
import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from campaign_planner.models import OfflineModel, campaign_fields, make_generator
from campaign_planner.runner import render_plan, run, snapshot
from campaign_planner.schemas import ExecutionLimit, digest


def prepare(engine, channels=None, tier="economy"):
    quote = engine.execute("estimate_plan", dict(tier=tier, channels=channels))
    assert quote["feasible"]
    result = engine.execute(
        "generate_script", dict(quote_id=quote["quote_id"], deliverables=quote["remaining"])
    )
    assert result["status"] == "succeeded"
    return quote


def test_completed_request_rejects_all_further_business_changes(engine):
    quote = prepare(engine)
    assert (
        engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))[
            "status"
        ]
        == "succeeded"
    )
    before = copy.deepcopy(engine.state)
    saved = engine.storage.plan(engine.request["request_id"])
    for name in ("search_materials", "estimate_plan", "generate_script", "save_plan"):
        assert engine.execute(name, {})["error_code"] == "request_completed"
        assert engine.state == before
    assert engine.storage.plan(engine.request["request_id"]) == saved


def test_agent_stops_before_another_model_can_replan_after_save(invoke, monkeypatch):
    post_save_calls = []

    class MustStop(OfflineModel):
        def _generate(self, messages, **kwargs):
            if self.engine.state["status"] == "completed":
                post_save_calls.append(self.agent_role)
                raise AssertionError("post-save model must not run")
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr("campaign_planner.models.OfflineModel", MustStop)
    result = invoke()
    assert result["status"] == "completed" and not result["missing"]
    assert result["reason"] is None
    assert post_save_calls == []
    with open(result["trace_path"], encoding="utf-8") as stream:
        assert not any(json.loads(line)["event"] == "runtime_error" for line in stream)


def test_completed_snapshot_uses_saved_plan_even_if_active_quote_is_changed(engine):
    quote = prepare(engine)
    engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    saved = engine.storage.plan(engine.request["request_id"])
    engine.state["quotes"][quote["quote_id"]]["plan"]["deliverables"].append("channel_adaptation")
    engine.state["spent"] += 4
    output = snapshot(engine.state, engine.storage)
    assert output["task_plan"] == saved["task_plan"]
    assert output["current_results"] == saved["results"]
    assert output["total_cost"] == 8 and output["missing"] == []


def test_channel_change_requires_new_content_and_keeps_previous_charges(engine):
    engine.request["budget"] = 20
    prepare(engine, ["校园公众号"])
    original = copy.deepcopy(engine.current_results)
    quote = engine.execute("estimate_plan", dict(tier="economy", channels=["短视频平台"]))
    assert quote["remaining"] == ["video_script", "social_copy"]
    assert quote["total_cost"] == 16
    assert engine.current_results == {}
    rejected = engine.execute(
        "save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季"))
    )
    assert rejected["error_code"] == "dependency_missing"
    assert snapshot(engine.state, engine.storage)["missing"] == quote["remaining"]
    engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=quote["remaining"]))
    assert engine.state["result_history"] == list(original.values())
    engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    saved = engine.storage.plan(engine.request["request_id"])
    assert all(r["channels"] == ["短视频平台"] for r in saved["results"].values())
    assert saved["total_cost"] == sum(r["cost"] for r in saved["charged_results"]) == 16
    assert "未用于当前方案的已完成工作费用：8" in render_plan(saved)


def test_switching_back_reuses_archived_results_without_charging_again(engine):
    engine.request["budget"] = 20
    prepare(engine, ["校园公众号"])
    original = copy.deepcopy(engine.current_results)
    prepare(engine, ["短视频平台"])
    quote = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号"]))
    assert quote["remaining"] == [] and quote["total_cost"] == 16
    assert engine.current_results == original
    assert (
        engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=["video_script"]))[
            "error_code"
        ]
        == "already_completed"
    )
    assert engine.state["spent"] == 16
    engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    saved = engine.storage.plan(engine.request["request_id"])
    assert saved["results"] == original
    for step in saved["task_plan"]["steps"]:
        if step["step_id"] in original:
            assert step["result_id"] == original[step["step_id"]]["result_id"]


def test_partial_scope_change_cannot_hide_previous_spending(engine):
    quote = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号"]))
    engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=["video_script"]))
    original = copy.deepcopy(engine.state["results"])
    changed = engine.execute("estimate_plan", dict(tier="economy", channels=["短视频平台"]))
    assert not changed["feasible"] and changed["total_cost"] == 12
    assert changed["remaining"] == ["video_script", "social_copy"]
    assert (
        engine.execute(
            "generate_script", dict(quote_id=changed["quote_id"], deliverables=changed["remaining"])
        )["error_code"]
        == "infeasible_quote"
    )
    assert engine.state["results"] == original and engine.state["spent"] == 4


@pytest.mark.parametrize(
    "changed_id, expected_missing",
    [
        ("campus-01", ["video_script", "channel_adaptation"]),
        ("unrelated", []),
    ],
)
def test_material_versions_invalidate_only_affected_content_and_dependents(
    engine, changed_id, expected_missing
):
    engine.request["budget"] = 40
    engine.request["deadline"] = "2030-06-01T18:00:00+08:00"

    def generate(key, backend, instance):
        mid = "campus-01" if key == "video_script" else "campus-02"
        return dict(text="基于当前素材生成内容，具体入口和日期由运营确认。" * 3, material_ids=[mid])

    engine.generator = generate
    prepare(engine, tier="standard")
    original = copy.deepcopy(engine.current_results)
    if changed_id == "unrelated":
        engine.catalog["materials"].append(dict(engine.catalog["materials"][1], id="unrelated"))
    else:
        engine.catalog["materials"][0]["content"] += "新增的已核实合成事实。"
    engine.execute("search_materials", dict(query=engine.request["theme"]))
    quote = engine.execute("estimate_plan", dict(tier="standard"))
    assert quote["feasible"]
    assert quote["remaining"] == expected_missing
    if expected_missing:
        engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=expected_missing))
        assert engine.current_results["video_script"]["result_id"] != original["video_script"]["result_id"]
        assert (
            engine.current_results["channel_adaptation"]["result_id"]
            != original["channel_adaptation"]["result_id"]
        )
    assert engine.current_results["social_copy"] == original["social_copy"]
    saved = engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    assert saved["status"] == "succeeded"


def test_removed_cited_material_is_reported_as_missing_before_save(engine):
    engine.request["budget"] = 20
    prepare(engine)
    engine.execute("search_materials", dict(query=engine.request["theme"], kinds=["channel_adaptation"]))
    quote = engine.execute("estimate_plan", dict(tier="economy"))
    assert quote["remaining"] == ["video_script", "social_copy"]
    generated = engine.execute(
        "generate_script", dict(quote_id=quote["quote_id"], deliverables=quote["remaining"])
    )
    assert generated["status"] == "succeeded"
    assert (
        engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))[
            "status"
        ]
        == "succeeded"
    )


def test_legacy_results_can_reuse_their_recorded_quote_and_material_hash(engine):
    prepare(engine)
    for result in engine.state["results"].values():
        for key in ("channels", "material_versions", "dependency_results"):
            result.pop(key)
    quote = engine.execute("estimate_plan", dict(tier="economy"))
    assert quote["remaining"] == [] and quote["total_cost"] == 8
    assert quote["existing_hash"] == digest(engine.current_results)


@pytest.mark.parametrize(
    "tier, channels, budget, deadline, elapsed",
    [
        ("economy", [], 10, "2030-06-01T11:05:00+08:00", 64),
        ("standard", [], 20, "2030-06-01T12:05:00+08:00", 124),
        ("standard", ["校园公众号", "短视频平台", "校内社群"], 20, "2030-06-01T12:05:00+08:00", 124),
    ],
)
def test_save_failure_near_deadline_reports_real_cause_and_resumes(
    invoke, tmp_path, tier, channels, budget, deadline, elapsed
):
    first = invoke(
        dict(preferred_tier=tier, required_channels=channels, budget=budget, deadline=deadline),
        faults={"save": "always"},
    )
    assert first["reason"] == "save_failed"
    assert first["time_gap_minutes"] == first["current_plan_time_gap_minutes"] == 0
    second = run(resume_id=first["request_id"], db=tmp_path / "state.sqlite", output=tmp_path / "resume")
    assert second["status"] == "completed" and second["elapsed_minutes"] == elapsed
    assert second["tool_results"] == first["tool_results"]


@pytest.mark.parametrize("allow_simplification", [True, False])
def test_economy_preference_upgrades_to_meet_required_channels(invoke, allow_simplification):
    result = invoke(
        dict(
            preferred_tier="economy",
            budget=20,
            allow_simplification=allow_simplification,
            required_channels=["校园公众号", "短视频平台"],
        )
    )
    assert result["status"] == "completed"
    assert [p["tier"] for p in result["plan_history"]] == ["economy", "standard"]
    assert result["total_cost"] == 12


def test_custom_save_duration_is_used_by_execution_and_snapshot(engine):
    engine.rules["operations"]["save_plan"] = 7
    engine.state["cost_rules"] = copy.deepcopy(engine.rules)
    quote = prepare(engine)
    assert quote["remaining_minutes"] == 67
    output = snapshot(engine.state, engine.storage)
    assert output["estimated_total_cost"] == 8 and output["current_plan_time_gap_minutes"] == 0
    engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    assert engine.state["elapsed_minutes"] == 69


def test_resume_keeps_custom_rules_and_reuses_successes(invoke, tmp_path):
    from campaign_planner.tools import PROJECT_ROOT

    rules = json.loads((PROJECT_ROOT / "data/cost_rules.json").read_text(encoding="utf-8"))
    rules["operations"]["save_plan"] = 7
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    first = invoke(dict(preferred_tier="economy"), rules_path=path, faults={"save": "always"})
    second = run(resume_id=first["request_id"], db=tmp_path / "state.sqlite", output=tmp_path / "resume")
    assert second["status"] == "completed" and second["elapsed_minutes"] == 70
    assert second["tool_results"] == first["tool_results"]


@pytest.mark.parametrize("writer_enabled", [True, False])
def test_generation_failure_before_quote_returns_structured_incomplete(invoke, monkeypatch, writer_enabled):
    import campaign_planner.agent as agent

    if not writer_enabled:
        original_load = agent.load_subagents
        monkeypatch.setattr(
            agent, "load_subagents", lambda: [s for s in original_load() if s.role != "writer"]
        )

    class EarlyGeneration(OfflineModel):
        def _generate(self, messages, **kwargs):
            calls = []
            if self.agent_role == "writer" or self.engine.tool_calls == 0:
                name, args = "generate_script", dict(quote_id="missing", deliverables=["video_script"])
                if writer_enabled and self.agent_role == "main":
                    name, args = "task", dict(subagent_type="content-writer", description="生成内容")
                calls = [dict(name=name, args=args, id="early-generation", type="tool_call")]
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="工具失败后停止", tool_calls=calls))]
            )

    monkeypatch.setattr("campaign_planner.models.OfflineModel", EarlyGeneration)
    result = invoke()
    assert result["status"] == "incomplete" and result["reason"] == "stale_quote"
    assert result["task_plan"]["version"] == 0
    assert [s["status"] for s in result["task_plan"]["steps"]] == ["failed"]
    assert result["total_cost"] == 0 and result["saved_plan_id"] is None


def test_history_reuses_a_complete_dependency_bundle_before_declaring_deadline_infeasible(engine):
    engine.request.update(budget=20, deadline="2030-06-01T13:40:00+08:00", allow_simplification=False)
    engine.request["required_channels"] = sorted(engine.state["materials"]["campus-02"]["channels"])[:2]

    def generate(key, backend, instance):
        mid = (
            "campus-01"
            if key == "video_script" and "campus-01" in instance.state["materials"]
            else "campus-02"
        )
        return dict(text="有明确素材依据的活动参与说明，日期和入口由运营核实。" * 3, material_ids=[mid])

    engine.generator = generate
    prepare(engine, tier="standard")
    original = copy.deepcopy(engine.current_results)
    engine.execute("search_materials", dict(query=engine.request["theme"], kinds=["channel_adaptation"]))
    quote = engine.execute("estimate_plan", dict(tier="standard"))
    assert quote["feasible"]
    engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=["video_script"]))
    assert engine.state["results"]["video_script"]["result_id"] != original["video_script"]["result_id"]
    engine.execute("search_materials", dict(query=engine.request["theme"]))
    quote = engine.execute("estimate_plan", dict(tier="standard"))
    assert quote["feasible"] and quote["remaining"] == []
    assert engine.current_results == original
    assert quote["total_cost"] == 16 and quote["remaining_minutes"] == 1
    engine.execute("save_plan", dict(quote_id=quote["quote_id"], campaign=campaign_fields("毕业季")))
    saved = engine.storage.plan(engine.request["request_id"])
    assert saved["results"] == original and saved["elapsed_minutes"] == 162
    assert saved["total_cost"] == sum(r["cost"] for r in saved["charged_results"]) == 16


@pytest.mark.parametrize("interruption", ["execution_limit", "interrupted"])
def test_legacy_partial_generation_resumes_without_recharging_video(engine, tmp_path, interruption):
    def generate(key, backend, instance):
        if key == "social_copy":
            raise ExecutionLimit("生成视频后中断")
        return dict(text="已成功生成且需要跨版本续跑复用的视频内容。" * 3, material_ids=["campus-01"])

    engine.generator = generate
    quote = engine.execute("estimate_plan", dict(tier="economy"))
    with pytest.raises(ExecutionLimit):
        engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=quote["remaining"]))
    video = engine.state["results"]["video_script"]
    for key in ("channels", "material_versions", "dependency_results"):
        video.pop(key)
    attempt = engine.state["attempts"][-1]
    assert "result" not in attempt
    if interruption == "interrupted":
        attempt["status"] = "running"
        attempt.pop("error_code")
    engine.persist()
    result = run(resume_id=engine.request["request_id"], db=engine.storage.path, output=tmp_path / "resume")
    assert result["status"] == "completed" and result["total_cost"] == 8
    assert result["current_results"]["video_script"] == video
    assert result["task_plan"]["steps"][2]["result_id"] == video["result_id"]
    new_attempts = result["attempts"][len(engine.state["attempts"]) :]
    assert [a["arguments"]["deliverables"] for a in new_attempts if a["tool"] == "generate_script"] == [
        ["social_copy"]
    ]


def test_legacy_partial_result_does_not_borrow_a_later_unrelated_quote(engine):
    engine.request["budget"] = 20
    quote = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号"]))
    engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=["video_script"]))
    video = engine.state["results"]["video_script"]
    for key in ("channels", "material_versions", "dependency_results"):
        video.pop(key)
    attempt = engine.state["attempts"][-1]
    attempt.pop("result")
    attempt.update(status="partial", error_code="execution_limit")
    changed = engine.execute("estimate_plan", dict(tier="economy", channels=["短视频平台"]))
    assert changed["remaining"] == ["video_script", "social_copy"]
    restored = engine.execute("estimate_plan", dict(tier="economy", channels=["校园公众号"]))
    assert restored["remaining"] == ["social_copy"] and restored["total_cost"] == 8


@pytest.mark.parametrize("cached", [False, True])
def test_plan_export_failure_preserves_completed_response_for_fresh_and_cached_runs(
    invoke, monkeypatch, cached
):
    from pathlib import Path

    first = invoke() if cached else None
    real_write = Path.write_text

    def fail_export(path, *args, **kwargs):
        if path.name == "plan.md":
            raise OSError("模拟方案导出失败")
        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_export)
    result = invoke()
    assert result["status"] == "completed" and result["export_status"] == "failed"
    assert result["cached"] == cached and result["saved_plan_id"]
    output = json.loads(Path(result["trace_path"]).with_name("output.json").read_text(encoding="utf-8"))
    assert output["status"] == "completed" and output["export_status"] == "failed"
    if first:
        assert result["saved_plan_id"] == first["saved_plan_id"]
        assert result["tool_results"] == first["tool_results"]
        assert result["model_calls"] == result["tool_calls"] == 0


@pytest.mark.parametrize("backend", ["primary", "backup"])
def test_adaptation_uses_the_selected_base_content_and_dependency_ids(engine, backend):
    engine.request["budget"] = 20
    engine.generator = lambda key, *args: dict(
        text=f"{key} 核心信息与专属行动引导：按原稿说明参与。" * 3, material_ids=["campus-01"]
    )
    quote = engine.execute("estimate_plan", dict(tier="standard", backend=backend))
    engine.execute(
        "generate_script", dict(quote_id=quote["quote_id"], deliverables=["video_script", "social_copy"])
    )
    sources = copy.deepcopy(engine.current_results)
    captured = []

    class RecordingModel:
        def invoke(self, messages):
            prompt = json.loads(messages[0].content)
            captured.append(prompt)
            return AIMessage(
                content=json.dumps(
                    dict(text="依据原有视频、图文核心信息改写的多渠道内容。" * 3, material_ids=["campus-01"])
                )
            )

    engine.generator = make_generator("live", RecordingModel())
    quote = engine.execute("estimate_plan", dict(tier="standard", backend=backend))
    result = engine.execute(
        "generate_script", dict(quote_id=quote["quote_id"], deliverables=["channel_adaptation"])
    )
    assert result["status"] == "succeeded"
    adaptation = result["completed"][0]
    assert adaptation["dependency_results"] == {k: r["result_id"] for k, r in sources.items()}
    if backend == "primary":
        assert len(captured) == 1
        assert captured[0]["source_results"] == {
            k: dict(result_id=r["result_id"], content=r["content"]) for k, r in sources.items()
        }
    else:
        assert captured == []
        assert all(r["content"]["text"] in adaptation["content"]["text"] for r in sources.values())

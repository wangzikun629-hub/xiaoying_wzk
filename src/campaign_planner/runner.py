import copy
import importlib.metadata
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from .schemas import ExecutionLimit, digest, parse_time, utc_now, validate_request
from .storage import BusyRequest, Storage
from .tools import PROJECT_ROOT, Engine
from .trace import Trace, public


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(public(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def render_plan(plan):
    lines = [f"# {plan['request']['theme']}", "", f"证据模式：{plan['mode']}；方案 ID：{plan['plan_id']}", ""]
    for key, label in (
        ("goal", "目标"),
        ("audience", "受众"),
        ("message", "核心信息"),
        ("schedule", "排期"),
        ("roles", "执行角色"),
        ("suggested_metrics", "建议指标"),
    ):
        lines += [f"## {label}", "", plan["campaign"][key], ""]
    lines += ["渠道：" + "、".join(plan["channels"]), ""]
    for key, result in plan["results"].items():
        lines += [
            f"## {key}",
            "",
            f"来源：{result['origin']}；模拟费用：{result['cost']}",
            "",
            result["content"]["text"],
            "",
            "素材 ID：" + ", ".join(result["content"]["material_ids"]),
            "",
        ]
    lines += [
        f"费用合计：{plan['total_cost']} 模拟单位",
        f"累计模拟耗时：{plan['elapsed_minutes']} 分钟",
        f"完成时间：{plan['completed_at']}",
        "",
    ]
    return "\n".join(lines)


def metadata(mode, faults, state=None):
    versions = {}
    for package in ("campaign-planner", "deepagents", "langchain", "langchain-openai", "langgraph"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    source = {
        str(p.relative_to(PROJECT_ROOT)): p.read_text(encoding="utf-8")
        for directory, suffix in (
            ("src", ".py"),
            ("scripts", ".py"),
            ("tests", ".py"),
            ("data", ".json"),
            ("config", ".md"),
            ("skills", ".md"),
        )
        for p in (PROJECT_ROOT / directory).rglob("*" + suffix)
    }
    for name in ("pyproject.toml", "uv.lock", "uv.toml"):
        source[name] = (PROJECT_ROOT / name).read_text(encoding="utf-8")
    return dict(
        mode=mode,
        provider="openai-compatible" if mode == "live" else "none",
        model=os.getenv("OPENAI_MODEL") if mode == "live" else "offline-deterministic-test-policy",
        model_settings=dict(
            temperature=0,
            timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "60")),
            transport_retries=0,
        )
        if mode == "live"
        else None,
        versions=versions,
        source_sha256=digest(source),
        faults=faults,
        clock_mode=state.get("clock_mode") if state else None,
        clock_anchor=state.get("clock_anchor") if state else None,
        rules_sha256=state.get("rules_sha256") if state else None,
        materials_sha256=state.get("materials_sha256") if state else None,
        note="Mock verifies workflow only; source_sha256 identifies actual working files, not a Git commit.",
    )


def snapshot(state, store):
    q = state["quotes"].get(state.get("active_quote"))
    plan = (
        copy.deepcopy(q["plan"])
        if q
        else {
            "version": 0,
            "steps": [
                dict(step_id=a["attempt_id"], action=a["tool"], depends_on=[], status=a["status"])
                for a in state["attempts"]
            ],
        }
    )
    for step in plan["steps"]:
        if step["step_id"] in state["results"]:
            step.update(status="succeeded", result_id=state["results"][step["step_id"]]["result_id"])
        elif step["step_id"] == "save":
            saved_attempts = [a for a in state["attempts"] if a["tool"] == "save_plan"]
            step["status"] = (
                "succeeded"
                if state["status"] == "completed"
                else saved_attempts[-1]["status"]
                if saved_attempts
                else "pending"
                if set(q["plan"]["deliverables"]) <= state["results"].keys()
                else "blocked"
            )
        elif step["action"] == "generate_script":
            related = [
                a
                for a in state["attempts"]
                if a["tool"] == "generate_script"
                and step["step_id"] in a["arguments"].get("deliverables", [])
            ]
            step["status"] = "failed" if related else "pending" if q["feasible"] else "blocked"
    current_time = parse_time(state["clock_anchor"]) if state["clock_mode"] == "simulated" else utc_now()
    current_time += timedelta(minutes=state["elapsed_minutes"])
    alternatives = q.get("alternatives", []) if q else []
    affordable = [c for c in alternatives if c["total_cost"] <= state["request"]["budget"]]
    minimum_time_gap = (
        min(
            max(
                0,
                (
                    (current_time + timedelta(minutes=c["remaining_minutes"]))
                    - parse_time(state["request"]["deadline"])
                ).total_seconds()
                / 60,
            )
            for c in (affordable or alternatives)
        )
        if alternatives
        else None
    )
    return dict(
        status=state["status"],
        request_id=state["request"]["request_id"],
        reason=state.get("reason"),
        request=state["request"],
        task_plan=plan,
        plan_history=state["plans"],
        attempts=state["attempts"],
        tool_results=state["results"],
        total_cost=state["spent"],
        estimated_total_cost=q["total_cost"] if q else None,
        elapsed_minutes=state["elapsed_minutes"],
        clock_mode=state["clock_mode"],
        saved_plan_id=state.get("saved_plan_id"),
        saved_store=str(store.path),
        budget_gap=(q.get("minimum_budget_gap") if q and not q["budget_ok"] else 0),
        time_gap_minutes=0 if state["status"] == "completed" else minimum_time_gap,
        current_plan_time_gap_minutes=q["time_gap_minutes"] if q else None,
        missing=([k for k in q["plan"]["deliverables"] if k not in state["results"]] if q else []),
        runs=state["runs"],
        mode=state["mode"],
    )


def decide_incomplete(engine):
    state = engine.state
    q = state["quotes"].get(state.get("active_quote"))
    if engine.halt_reason:
        return engine.halt_reason
    if q and q.get("alternatives"):
        affordable = [c for c in q["alternatives"] if c["total_cost"] <= engine.request["budget"]]
        if not affordable:
            return "budget_infeasible"
        if not any(engine.fits_time(c["remaining_minutes"]) for c in affordable):
            return "deadline_infeasible"
    if q and not q["budget_ok"]:
        return "budget_infeasible" if q.get("minimum_budget_gap") else "current_plan_over_budget"
    if q and not q["deadline_ok"]:
        return "deadline_infeasible"
    if q and not q["scope_ok"]:
        return "insufficient_materials" if q["missing_materials"] else "scope_infeasible"
    return state.get("last_error") or "not_saved"


def run(
    raw=None,
    *,
    mode="mock",
    db=None,
    output=None,
    now=None,
    faults=None,
    max_models=20,
    max_tools=32,
    resume_id=None,
    rules_path=None,
    materials_path=None,
    model_override=None,
):
    if mode not in ("mock", "live") or max_models < 1 or max_tools < 1:
        raise ValueError("非法模式或运行上限")
    start = parse_time(now) if now else utc_now()
    output = Path(output or PROJECT_ROOT / "outputs" / mode / ("run-" + uuid4().hex[:12]))
    output.mkdir(parents=True, exist_ok=True)
    trace = Trace(output / "trace.jsonl", mode)
    store = Storage(db or PROJECT_ROOT / "outputs" / mode / "state.sqlite")
    faults = faults or {}

    def finish(result, state=None):
        result.update(trace_path=str(trace.path.resolve()))
        write_json(output / "output.json", result)
        write_json(output / "run-metadata.json", metadata(mode, faults, state))
        return result

    try:
        if resume_id:
            old = store.get(resume_id)
            if old is None:
                return finish(dict(status="invalid_input", reason="request_not_found"))
            raw = {k: v for k, v in old["request"].items() if k != "fingerprint"}
        write_json(output / "input.json", raw)
        request, error = validate_request(raw, start, check_deadline=False)
        if error:
            trace.add("validation", result=error)
            return finish(dict(error, model_calls=0, tool_calls=0))
        try:
            with store.request_lock(request["request_id"]):
                state = store.get(request["request_id"])
                if state:
                    if state["request"]["fingerprint"] != request["fingerprint"]:
                        return finish(
                            dict(
                                status="invalid_input",
                                reason="request_id_conflict",
                                model_calls=0,
                                tool_calls=0,
                            )
                        )
                    if state["mode"] != mode:
                        return finish(
                            dict(
                                status="invalid_input",
                                reason="evidence_mode_conflict",
                                model_calls=0,
                                tool_calls=0,
                            )
                        )
                    if state["status"] == "completed" or not resume_id:
                        trace.add(
                            "idempotent_return", status=state["status"], plan_id=state.get("saved_plan_id")
                        )
                        result = snapshot(state, store)
                        result.update(cached=True, model_calls=0, tool_calls=0)
                        plan = store.plan(request["request_id"])
                        if plan:
                            (output / "plan.md").write_text(render_plan(plan), encoding="utf-8")
                        return finish(result, state)
                    if (
                        now
                        and state["clock_mode"] == "simulated"
                        and parse_time(now) != parse_time(state["clock_anchor"])
                    ):
                        return finish(dict(status="invalid_input", reason="resume_clock_cannot_reset"), state)
                else:
                    if parse_time(request["deadline"]) <= start:
                        return finish(
                            dict(
                                status="invalid_input", reason="deadline_expired", model_calls=0, tool_calls=0
                            )
                        )
                    state = dict(
                        request=request,
                        mode=mode,
                        status="running",
                        reason=None,
                        clock_anchor=start.isoformat(),
                        clock_mode="simulated" if now else "wall",
                        elapsed_minutes=0,
                        spent=0,
                        materials={},
                        results={},
                        attempts=[],
                        quotes={},
                        plans=[],
                        runs=[],
                        fault_counts={},
                    )
                # An unclosed attempt may have committed item results. Preserve those; report interruption.
                for attempt in state["attempts"]:
                    if attempt["status"] == "running":
                        attempt.update(status="failed", error_code="interrupted")
                run_id = str(uuid4())
                state.update(active_run_id=run_id, status="running", reason=None)
                run_record = dict(
                    run_id=run_id, trace_path=str(trace.path.resolve()), resumed=bool(resume_id)
                )
                state["runs"].append(run_record)
                store.put(state)
                engine = Engine(
                    store,
                    state,
                    trace,
                    faults=faults,
                    max_models=max_models,
                    max_tools=max_tools,
                    rules=json.loads(Path(rules_path).read_text(encoding="utf-8")) if rules_path else None,
                    materials=json.loads(Path(materials_path).read_text(encoding="utf-8"))
                    if materials_path
                    else None,
                )
                state.update(rules_sha256=digest(engine.rules), materials_sha256=digest(engine.catalog))
                trace.add(
                    "run_start",
                    run_id=run_id,
                    request=request,
                    resumed=bool(resume_id),
                    limits=dict(model_calls=max_models, tool_calls=max_tools),
                )
                try:
                    from .agent import build_agent
                    from .models import OfflineModel, live_model, make_generator

                    model = model_override or (
                        OfflineModel(engine=engine) if mode == "mock" else live_model()
                    )
                    engine.generator = make_generator(mode, model)
                    if not engine.fits_time(0):
                        engine.halt_reason = "deadline_infeasible"
                    else:
                        agent, inputs = build_agent(engine, model)
                        agent.invoke(
                            inputs,
                            config={
                                "recursion_limit": max_models * 5 + max_tools * 3 + 20,
                                "configurable": {"thread_id": request["request_id"] + ":" + run_id},
                            },
                        )
                except ExecutionLimit:
                    engine.halt_reason = "execution_limit"
                except KeyboardInterrupt:
                    engine.halt_reason = "interrupted"
                except Exception as exc:
                    # No transport exception strings: providers may include credentials or headers.
                    engine.halt_reason = "model_unavailable" if mode == "live" else "runtime_error"
                    trace.add("runtime_error", exception_type=type(exc).__name__, reason=engine.halt_reason)
                if state["status"] != "completed":
                    state.update(status="incomplete", reason=decide_incomplete(engine))
                run_record.update(
                    model_calls=engine.model_calls,
                    tool_calls=engine.tool_calls,
                    status=state["status"],
                    reason=state.get("reason"),
                )
                store.put(state)
                result = snapshot(state, store)
                result.update(
                    run_id=run_id, cached=False, model_calls=engine.model_calls, tool_calls=engine.tool_calls
                )
                saved = store.plan(request["request_id"])
                if saved:
                    try:
                        (output / "plan.md").write_text(render_plan(saved), encoding="utf-8")
                        result["export_status"] = "succeeded"
                    except OSError:
                        result["export_status"] = "failed"
                trace.add(
                    "run_end",
                    status=result["status"],
                    reason=result["reason"],
                    total_cost=result["total_cost"],
                    model_calls=engine.model_calls,
                    tool_calls=engine.tool_calls,
                )
                return finish(result, state)
        except BusyRequest:
            return finish(
                dict(status="in_progress", reason="same_request_is_running", model_calls=0, tool_calls=0)
            )
    finally:
        store.close()

"""Generate actual inputs, outputs, traces and acceptance assertions. No fabricated LLM traces."""

import argparse
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from campaign_planner.runner import run, write_json
from campaign_planner.tools import PROJECT_ROOT

NOW = "2030-06-01T10:00:00+08:00"
BASE = dict(theme="毕业季校园影像征集", budget=10, deadline="2030-06-01T13:00:00+08:00")
SCENARIOS = [
    ("C01-normal", {"budget": 20}, {}, {}),
    ("C02a-missing-budget", {"budget": None}, {}, {}),
    ("C02b-missing-deadline", {"deadline": None}, {}, {}),
    ("C03a-once-failure", {"preferred_tier": "economy"}, {"generate:social_copy": "once"}, {}),
    ("C03b-primary-unavailable", {"preferred_tier": "economy"}, {"primary": "always"}, {}),
    ("C04-budget-replan", {}, {}, {}),
    ("C05-budget-infeasible", {"budget": 5}, {}, {}),
    ("C06-repeated-run", {}, {}, {}),
    ("C07a-partial-materials", {"theme": "环保旧物回收", "budget": 20}, {}, {}),
    ("C07b-partial-generation", {"preferred_tier": "economy"}, {"generate:social_copy": "once"}, {}),
    ("C07c-no-materials", {"theme": "深海潜航设备交流"}, {}, {}),
    ("C08-execution-limit", {}, {}, {"max_models": 1}),
    ("C09-deadline-infeasible", {"deadline": "2030-06-01T10:30:00+08:00"}, {}, {}),
    ("C10-id-conflict", {}, {}, {}),
    ("C11-save-failure", {"preferred_tier": "economy"}, {"save": "always"}, {}),
    (
        "C12a-resume-generation",
        {"preferred_tier": "economy"},
        {"generate:social_copy": "always"},
        {"max_models": 6},
    ),
    ("C12b-resume-save", {"preferred_tier": "economy"}, {"save": "always"}, {}),
]


def observations(result, tool):
    return [a["result"] for a in result.get("attempts", []) if a["tool"] == tool and "result" in a]


def check(name, result, followup=None):
    """Validate constraints and real decisions separately from the graph's final prose."""
    failures = []

    def expect(condition, description):
        if not condition:
            failures.append(description)

    if "total_cost" in result:
        expect(result["total_cost"] <= result["request"]["budget"], "实际费用不能超预算")
        expect(
            result["total_cost"] == sum(r["cost"] for r in result["tool_results"].values()),
            "实际费用与账目一致",
        )
    complete = name.startswith(("C01", "C03", "C04", "C06", "C07a", "C07b", "C10"))
    if complete:
        expect(result["status"] == "completed", "应完成并正式保存")
    if name.startswith("C02"):
        expect(result["status"] == "needs_input", "缺字段应 needs_input")
        expect(result["model_calls"] == result["tool_calls"] == 0, "缺字段不执行模型/工具")
    if name.startswith("C04"):
        quotes = observations(result, "estimate_plan")
        expect(any(q["total_cost"] == 12 and not q["budget_ok"] for q in quotes), "实际观察到报价12超限")
        expect(any(q["total_cost"] == 8 and q["feasible"] for q in quotes), "模型改选后重新报价8")
        expect(result["total_cost"] == 8, "实际只计8")
        expect(len(result.get("task_plan", {}).get("channels", [])) == 1, "精简版实际缩减为单渠道")
    if name.startswith("C03b"):
        expect(
            any(p["backend"] == "backup" for p in result.get("plan_history", [])), "持续故障后选择备用方式"
        )
    if name.startswith(("C03a", "C07b")):
        attempts = observations(result, "generate_script")
        partial = next((a for a in attempts if a["status"] == "partial"), None)
        expect(partial is not None, "必须实际发生部分成功")
        if partial:
            for item in partial["completed"]:
                expect(
                    result["tool_results"].get(item["deliverable"], {}).get("result_id") == item["result_id"],
                    "保留部分成功结果ID",
                )
    if name.startswith("C05"):
        expect(result["status"] == "incomplete" and result.get("budget_gap") == 3, "预算5应返回缺口3")
        expect(result["total_cost"] == 0, "无可行方案不生成")
    if name.startswith("C07c"):
        expect(result["status"] == "incomplete" and not result.get("tool_results"), "零素材不得编造")
    if name.startswith("C08"):
        expect(result.get("reason") == "execution_limit", "达到上限明确未完成")
    if name.startswith("C09"):
        expect(result.get("reason") == "deadline_infeasible", "截止时间不足")
    if name.startswith("C11"):
        expect(result["status"] == "incomplete" and not result.get("saved_plan_id"), "保存失败不能记成功")
    if followup and name.startswith("C06"):
        expect(
            followup.get("cached") and followup["model_calls"] == followup["tool_calls"] == 0,
            "重复执行无调用",
        )
        expect(followup.get("saved_plan_id") == result.get("saved_plan_id"), "重复返回同一方案")
    if followup and name.startswith("C10"):
        expect(followup.get("reason") == "request_id_conflict", "不同输入不能覆盖相同ID")
    if name.startswith("C12"):
        expect(result["status"] == "incomplete", "首轮实际失败或中止")
        expect(bool(result["tool_results"]), "首轮必须有已成功结果可供续跑复用")
        expect(followup is not None and followup["status"] == "completed", "续跑后完成")
        if followup:
            expect(followup["total_cost"] == 8, "续跑不重复收费")
            for key, item in result["tool_results"].items():
                expect(followup["tool_results"].get(key) == item, "续跑复用已成功结果")
    return failures


def generate(mode="mock", root=None, selected=None, summary_name="summary.json"):
    root = Path(root or PROJECT_ROOT / "examples" / mode)
    records = []
    with tempfile.TemporaryDirectory(prefix="campaign-examples-") as temporary:
        for name, changes, faults, options in SCENARIOS:
            if selected and name not in selected:
                continue
            folder = root / name
            raw = dict(BASE, **changes, request_id=name)
            db = Path(temporary) / (name + ".sqlite")
            result = run(raw, mode=mode, db=db, output=folder, now=NOW, faults=faults, **options)
            followup = None
            if name.startswith(("C06", "C10")):
                second_input = dict(raw, budget=raw["budget"] + 1) if name.startswith("C10") else raw
                followup = run(second_input, mode=mode, db=db, output=folder / "second", now=NOW)
            elif name.startswith("C12"):
                followup = run(mode=mode, db=db, output=folder / "resume", resume_id=raw["request_id"])
            errors = check(name, result, followup)
            record = dict(
                scenario=name,
                mode=mode,
                status=result["status"],
                passed=not errors,
                errors=errors,
                total_cost=result.get("total_cost"),
                model_calls=result.get("model_calls"),
                tool_calls=result.get("tool_calls"),
            )
            write_json(folder / "assertions.json", record)
            records.append(record)
            print(f"{name}: {'PASS' if not errors else 'FAIL'} ({mode})")
    write_json(
        root / summary_name,
        dict(
            mode=mode,
            total=len(records),
            passed=sum(r["passed"] for r in records),
            records=records,
            boundary="Mock validates engineering only, not real LLM decisions.",
        ),
    )
    return records


if __name__ == "__main__":
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "mock"], default="mock")
    parser.add_argument("--output")
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--summary-name", default="summary.json", help="Use a distinct name for disjoint batches")
    args = parser.parse_args()
    results = generate(args.mode, args.output, args.scenario, args.summary_name)
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)

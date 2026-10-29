"""Acceptance evidence must show the intended failure, not a service outage."""

import copy
import importlib.util
from pathlib import Path

import pytest

from campaign_planner.runner import snapshot

spec = importlib.util.spec_from_file_location(
    "run_examples", Path(__file__).resolve().parents[1] / "scripts/run_examples.py"
)
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)


@pytest.mark.parametrize(
    "scenario, changes, faults",
    [
        ("C07c-no-materials", {"theme": "深海潜航设备交流"}, {}),
        ("C11-save-failure", {"preferred_tier": "economy"}, {"save": "always"}),
    ],
)
@pytest.mark.parametrize("mutation", ["service_outage", "missing_observation", "none"])
def test_business_failure_evidence_requires_actual_cause(invoke, scenario, changes, faults, mutation):
    result = copy.deepcopy(invoke(changes, faults=faults))
    if mutation == "service_outage":
        result.update(reason="model_unavailable", attempts=[], tool_results={}, total_cost=0)
    elif mutation == "missing_observation":
        result["attempts"] = []
    errors = examples.check(scenario, result)
    if mutation == "none":
        assert errors == []
    else:
        assert errors


@pytest.mark.parametrize("replanned", [False, True])
@pytest.mark.parametrize("incorrect_unattempted_failure", [False, True])
def test_unattempted_evidence_checks_the_current_quote(engine, replanned, incorrect_unattempted_failure):
    engine.faults = {"generate:video_script": "always"}
    quote = engine.execute("estimate_plan", dict(tier="economy"))
    engine.execute("generate_script", dict(quote_id=quote["quote_id"], deliverables=quote["remaining"]))
    if replanned:
        engine.execute("estimate_plan", dict(tier="economy", backend="backup"))
    engine.state.update(status="incomplete", reason="execution_limit")
    result = snapshot(engine.state, engine.storage)
    if incorrect_unattempted_failure:
        next(s for s in result["task_plan"]["steps"] if s["step_id"] == "social_copy")["status"] = "failed"
    errors = examples.check("C14-unattempted-steps", result)
    assert bool(errors) == incorrect_unattempted_failure

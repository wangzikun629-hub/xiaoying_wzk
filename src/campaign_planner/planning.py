"""Shared, read-only checks for result reuse, remaining work and feasibility."""

import json
from datetime import timedelta
from pathlib import Path

from .schemas import digest, parse_time, utc_now

BASE_DELIVERABLES = ("video_script", "social_copy")


def current_time(state):
    anchor = parse_time(state["clock_anchor"]) if state["clock_mode"] == "simulated" else utc_now()
    return anchor + timedelta(minutes=state["elapsed_minutes"])


class Planning:
    def __init__(self, state, rules=None):
        self.state = state
        self.request = state["request"]
        self.rules = (
            rules
            or state.get("cost_rules")
            or json.loads(
                (Path(__file__).resolve().parents[2] / "data/cost_rules.json").read_text(encoding="utf-8")
            )
        )
        self.now = current_time(state)

    def _legacy_channels(self, result):
        interrupted_scopes = set()
        for attempt in self.state["attempts"]:
            if attempt["tool"] != "generate_script":
                continue
            quote = self.state["quotes"].get(attempt["arguments"].get("quote_id"))
            if not quote:
                continue
            if any(
                r["result_id"] == result["result_id"] for r in attempt.get("result", {}).get("completed", [])
            ):
                return quote["plan"]["channels"]
            # An interrupted legacy batch committed each item before recording its summary.
            if (
                "result" not in attempt
                and (
                    attempt["status"] in ("running", "partial")
                    or attempt.get("error_code") in ("execution_limit", "interrupted")
                )
                and result["deliverable"] in attempt["arguments"].get("deliverables", [])
                and result["backend"] == quote["plan"]["backend"]
                and result["materials_hash"] == quote["materials_hash"]
            ):
                interrupted_scopes.add(tuple(sorted(quote["plan"]["channels"])))
        # Never guess a channel scope when the persisted evidence is ambiguous.
        return list(next(iter(interrupted_scopes))) if len(interrupted_scopes) == 1 else None

    def results(self, plan):
        candidates = {key: [] for key in self.rules["deliverables"]}
        materials = self.state["materials"]
        history = [*self.state.get("result_history", []), *self.state["results"].values()]
        for result in reversed(history):
            if result["deliverable"] not in candidates:
                continue
            channels = result.get("channels")
            if channels is None:
                channels = self._legacy_channels(result)
            if channels is None or set(channels) != set(plan["channels"]):
                continue
            versions = result.get("material_versions")
            if versions is None:
                if result["materials_hash"] != digest(materials):
                    continue
            elif any(
                mid not in materials or digest(materials[mid]) != version for mid, version in versions.items()
            ):
                continue
            candidates[result["deliverable"]].append(result)
        usable = {
            key: values[0] for key, values in candidates.items() if values and key != "channel_adaptation"
        }
        if "channel_adaptation" in self.rules["tiers"][plan["tier"]]:
            for adaptation in candidates["channel_adaptation"]:
                dependencies = adaptation.get(
                    "dependency_results",
                    {key: usable[key]["result_id"] for key in BASE_DELIVERABLES if key in usable},
                )
                if set(dependencies) != set(BASE_DELIVERABLES):
                    continue
                sources = {
                    key: next((r for r in candidates[key] if r["result_id"] == dependencies[key]), None)
                    for key in BASE_DELIVERABLES
                }
                if all(sources.values()):
                    # A complete compatible bundle avoids regenerating an existing adaptation.
                    return dict(usable, **sources, channel_adaptation=adaptation)
        return usable

    def assess(self, plan):
        wanted = self.rules["tiers"][plan["tier"]]
        existing = self.results(plan)
        remaining = [k for k in wanted if k not in existing]
        cost_items = [dict(deliverable=k, **self.rules["deliverables"][k]) for k in remaining]
        minutes = sum(i["minutes"] for i in cost_items) + self.rules["operations"]["save_plan"]
        total = self.state["spent"] + sum(i["cost"] for i in cost_items)
        materials = self.state["materials"].values()
        available = set().union(*(set(m["kinds"]) for m in materials))
        supported = set().union(*(set(m["channels"]) for m in materials))
        missing_materials = sorted(set(wanted) - available)
        missing_channels = sorted(set(plan["channels"]) - supported)
        scope_issues = []
        count = len(set(plan["channels"]))
        if plan["tier"] == "standard" and count < 2:
            scope_issues.append("standard_requires_two_channels")
        if plan["tier"] == "economy" and count != 1:
            scope_issues.append("economy_requires_one_channel")
        if not set(self.request["required_channels"]) <= set(plan["channels"]):
            scope_issues.append("required_channels_missing")
        scope_ok = not missing_materials and not missing_channels and not scope_issues
        finish = self.now + timedelta(minutes=minutes)
        deadline = parse_time(self.request["deadline"])
        budget_ok, deadline_ok = total <= self.request["budget"], finish <= deadline
        return dict(
            remaining=remaining,
            cost_items=cost_items,
            remaining_cost=total - self.state["spent"],
            total_cost=total,
            remaining_minutes=minutes,
            expected_finish=finish.isoformat(),
            budget_ok=budget_ok,
            deadline_ok=deadline_ok,
            scope_ok=scope_ok,
            feasible=budget_ok and deadline_ok and scope_ok,
            budget_gap=max(0, total - self.request["budget"]),
            time_gap_minutes=max(0, (finish - deadline).total_seconds() / 60),
            missing_materials=missing_materials,
            missing_channels=missing_channels,
            scope_issues=scope_issues,
        )

    def alternatives(self, channels):
        supported = sorted(set().union(*(set(m["channels"]) for m in self.state["materials"].values())))
        if not set(channels) <= set(supported):
            return []
        candidates = []
        for tier in self.rules["tiers"]:
            if (
                tier == "economy"
                and self.request["preferred_tier"] == "standard"
                and not self.request["allow_simplification"]
            ):
                continue
            selected = list(self.request["required_channels"])
            for channel in [*channels, *supported]:
                if len(selected) >= (1 if tier == "economy" else 2):
                    break
                if channel not in selected and channel in supported:
                    selected.append(channel)
            scopes = [channels, selected]
            scopes.extend(
                r["channels"]
                for r in [*self.state.get("result_history", []), *self.state["results"].values()]
                if "channels" in r
            )
            seen = set()
            for scope in scopes:
                signature = tuple(sorted(set(scope)))
                if signature in seen:
                    continue
                seen.add(signature)
                plan = dict(tier=tier, channels=list(signature))
                assessment = self.assess(plan)
                if assessment["scope_ok"]:
                    candidates.append(dict(**plan, **assessment))
        return candidates

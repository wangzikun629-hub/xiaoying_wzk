"""Deterministic business guardrails. No automatic choice of tier or fallback."""

import copy
import json
import threading
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from .schemas import BusinessError, ExecutionLimit, digest, parse_time, utc_now

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUSINESS_TOOLS = {"search_materials", "estimate_plan", "generate_script", "save_plan"}


class Engine:
    def __init__(
        self,
        storage,
        state,
        trace,
        *,
        rules=None,
        materials=None,
        faults=None,
        max_models=20,
        max_tools=32,
        generator=None,
    ):
        self.storage, self.state, self.trace = storage, state, trace
        self.rules = rules or json.loads((PROJECT_ROOT / "data/cost_rules.json").read_text(encoding="utf-8"))
        self.catalog = materials or json.loads(
            (PROJECT_ROOT / "data/materials.json").read_text(encoding="utf-8")
        )
        self.faults = faults or {}
        self.max_models, self.max_tools = max_models, max_tools
        self.model_calls = self.tool_calls = 0
        self.generator = generator
        self.halt_reason = None
        self.tool_lock = threading.RLock()

    @property
    def request(self):
        return self.state["request"]

    def current_time(self):
        anchor = (
            parse_time(self.state["clock_anchor"]) if self.state["clock_mode"] == "simulated" else utc_now()
        )
        return anchor + timedelta(minutes=self.state["elapsed_minutes"])

    def fits_time(self, minutes):
        return self.current_time() + timedelta(minutes=minutes) <= parse_time(self.request["deadline"])

    def tick(self, minutes):
        self.state["elapsed_minutes"] += minutes

    def persist(self):
        self.storage.put(self.state)

    def count_model(self, purpose):
        if self.model_calls >= self.max_models:
            self.halt_reason = "execution_limit"
            raise ExecutionLimit("达到模型调用上限")
        self.model_calls += 1
        self.trace.add("model_request", purpose=purpose, count=self.model_calls)

    def count_tool(self, name):
        if self.tool_calls >= self.max_tools:
            self.halt_reason = "execution_limit"
            raise ExecutionLimit("达到工具调用上限")
        self.tool_calls += 1
        self.trace.add("tool_call_count", tool=name, count=self.tool_calls)

    def fault(self, key):
        spec = self.faults.get(key)
        if not spec:
            return False
        used = self.state["fault_counts"].get(key, 0)
        if spec == "always" or (spec == "once" and used == 0):
            self.state["fault_counts"][key] = used + 1
            self.persist()
            return True
        return False

    def execute(self, name, arguments, *, counted=False):
        if not counted:
            self.count_tool(name)
        if name not in BUSINESS_TOOLS:
            return {"status": "failed", "error_code": "unknown_tool", "message": "未知业务工具"}
        args = copy.deepcopy(arguments)
        reason = str(args.pop("reason", ""))[:300]
        attempt = dict(
            attempt_id=str(uuid4()),
            step_id=name,
            tool=name,
            arguments=args,
            reason=reason,
            run_id=self.state["active_run_id"],
            status="running",
        )
        self.state["attempts"].append(attempt)
        self.persist()
        self.trace.add("tool_start", **attempt)
        before_cost, before_time = self.state["spent"], self.state["elapsed_minutes"]
        try:
            result = getattr(self, name)(**args)
        except BusinessError as exc:
            result = dict(status="failed", error_code=exc.code, message=str(exc), **exc.details)
        except (TypeError, ValueError, KeyError) as exc:
            result = dict(status="failed", error_code="invalid_tool_arguments", message=type(exc).__name__)
        except ExecutionLimit:
            attempt["status"] = "partial" if self.state["spent"] > before_cost else "failed"
            attempt["error_code"] = "execution_limit"
            self.persist()
            raise
        except Exception as exc:
            result = dict(status="failed", error_code="tool_error", message=type(exc).__name__)
        result.update(
            cost_delta=self.state["spent"] - before_cost,
            minutes_delta=self.state["elapsed_minutes"] - before_time,
        )
        attempt.update(status=result["status"], result=copy.deepcopy(result))
        self.state["last_observation"] = result
        if result["status"] == "failed":
            self.state["last_error"] = result.get("error_code", "tool_failure")
        self.persist()
        self.trace.add(
            "tool_result",
            attempt_id=attempt["attempt_id"],
            tool=name,
            arguments=args,
            result=result,
            spent=self.state["spent"],
            current_time=self.current_time().isoformat(),
        )
        return result

    def search_materials(self, query, kinds=None):
        if not isinstance(query, str) or not query.strip():
            raise BusinessError("invalid_query", "检索词不能为空")
        kinds = kinds or list(self.rules["deliverables"])
        if not isinstance(kinds, list) or not set(kinds) <= self.rules["deliverables"].keys():
            raise BusinessError("invalid_query", "未知素材类型")
        if self.fault("search"):
            self.tick(1)
            raise BusinessError("search_unavailable", "素材检索失败", retryable=True)
        self.tick(self.rules["operations"]["search_materials"])
        # Query refinement cannot change the original campaign's subject.
        theme = self.request["theme"].casefold()
        scored = [
            (sum(len(tag) for tag in m["tags"] if tag.casefold() in theme), m)
            for m in self.catalog["materials"]
            if set(m["kinds"]) & set(kinds)
        ]
        best = max((score for score, _ in scored), default=0)
        # Prefer topic-specific evidence to a generic 'campus' match.
        matched = [m for score, m in scored if score == best and score > 0]
        self.state["materials"] = {m["id"]: m for m in matched}
        available = set().union(*(set(m["kinds"]) for m in matched)) if matched else set()
        missing = sorted(set(kinds) - available)
        channels = sorted(set().union(*(set(m["channels"]) for m in matched))) if matched else []
        return dict(
            status="succeeded" if matched and not missing else "partial" if matched else "failed",
            error_code=None if matched else "no_materials",
            materials=matched,
            available_kinds=sorted(available),
            missing_kinds=missing,
            available_channels=channels,
            message="合成素材；无法检索到的事实不得编造",
        )

    def estimate_plan(self, tier, backend="primary", channels=None):
        if tier not in self.rules["tiers"] or backend not in ("primary", "backup"):
            raise BusinessError("invalid_plan", "未知内容包或后端")
        if (
            tier == "economy"
            and self.request["preferred_tier"] == "standard"
            and not self.request["allow_simplification"]
        ):
            raise BusinessError("scope_violation", "用户不允许精简标准版")
        materials = list(self.state["materials"].values())
        if not materials:
            raise BusinessError("no_materials", "请先检索与主题匹配的素材")
        available = set().union(*(set(m["kinds"]) for m in materials))
        supported = set().union(*(set(m["channels"]) for m in materials))
        if channels is None:
            channels = list(self.request["required_channels"])
            for channel in sorted(supported):
                if len(channels) >= (2 if tier == "standard" else 1):
                    break
                if channel not in channels:
                    channels.append(channel)
        if (
            not isinstance(channels, list)
            or not channels
            or any(not isinstance(c, str) for c in channels)
            or not set(self.request["required_channels"]) <= set(channels)
        ):
            raise BusinessError("scope_violation", "渠道不能为空且须覆盖用户必需渠道")
        wanted = self.rules["tiers"][tier]
        missing_materials = sorted(set(wanted) - available)
        missing_channels = sorted(set(channels) - supported)
        existing = self.state["results"]
        remaining = [k for k in wanted if k not in existing]
        cost_items = [dict(deliverable=k, **self.rules["deliverables"][k]) for k in remaining]
        remaining_cost = sum(i["cost"] for i in cost_items)
        self.tick(self.rules["operations"]["estimate_plan"])
        minutes = sum(i["minutes"] for i in cost_items) + self.rules["operations"]["save_plan"]
        budget_ok = self.state["spent"] + remaining_cost <= self.request["budget"]
        finish = self.current_time() + timedelta(minutes=minutes)
        deadline = parse_time(self.request["deadline"])
        multi_ok = tier != "standard" or len(set(channels)) >= 2
        scope_ok = not missing_materials and not missing_channels and multi_ok
        version = len(self.state["plans"]) + 1
        steps = [
            dict(step_id="retrieve", action="search_materials", depends_on=[], status="succeeded"),
            dict(
                step_id=f"estimate-v{version}",
                action="estimate_plan",
                depends_on=["retrieve"],
                status="succeeded",
            ),
        ]
        for key in wanted:
            deps = [f"estimate-v{version}"]
            if key == "channel_adaptation":
                deps += ["video_script", "social_copy"]
            steps.append(
                dict(
                    step_id=key,
                    action="generate_script",
                    depends_on=deps,
                    status="succeeded" if key in existing else "pending",
                    result_id=existing.get(key, {}).get("result_id"),
                    **self.rules["deliverables"][key],
                )
            )
        steps.append(dict(step_id="save", action="save_plan", depends_on=wanted, status="pending"))
        plan = dict(
            version=version,
            tier=tier,
            backend=backend,
            channels=sorted(set(channels)),
            deliverables=wanted,
            steps=steps,
        )
        quote = dict(
            quote_id=str(uuid4()),
            plan=plan,
            rules_hash=digest(self.rules),
            materials_hash=digest(self.state["materials"]),
            existing_hash=digest(existing),
            feasible=budget_ok and finish <= deadline and scope_ok,
            budget_ok=budget_ok,
            deadline_ok=finish <= deadline,
            scope_ok=scope_ok,
            spent=self.state["spent"],
            remaining_cost=remaining_cost,
            total_cost=self.state["spent"] + remaining_cost,
            cost_items=cost_items,
            remaining=remaining,
            remaining_minutes=minutes,
            expected_finish=finish.isoformat(),
            budget_gap=max(0, self.state["spent"] + remaining_cost - self.request["budget"]),
            time_gap_minutes=max(0, (finish - deadline).total_seconds() / 60),
            missing_materials=missing_materials,
            missing_channels=missing_channels,
            scope_issues=[] if multi_ok else ["standard_requires_two_channels"],
        )
        # Minimum is valid only within this finite, declared catalog and hard scope.
        candidates = []
        allowed = [tier] if not self.request["allow_simplification"] else list(self.rules["tiers"])
        for candidate in allowed:
            items = self.rules["tiers"][candidate]
            if (
                set(items) <= available
                and not missing_channels
                and (candidate != "standard" or len(set(channels)) >= 2)
            ):
                candidates.append(
                    dict(
                        tier=candidate,
                        total_cost=self.state["spent"]
                        + sum(self.rules["deliverables"][k]["cost"] for k in items if k not in existing),
                        remaining_minutes=sum(
                            self.rules["deliverables"][k]["minutes"] for k in items if k not in existing
                        )
                        + 1,
                    )
                )
        quote["alternatives"] = candidates
        quote["minimum_budget_gap"] = (
            max(0, min(c["total_cost"] for c in candidates) - self.request["budget"]) if candidates else None
        )
        self.state["plans"].append(plan)
        self.state["quotes"][quote["quote_id"]] = quote
        self.state["active_quote"] = quote["quote_id"]
        return dict(status="succeeded", **quote)

    def get_quote(self, quote_id):
        quote = self.state["quotes"].get(quote_id)
        if not quote or quote_id != self.state.get("active_quote"):
            raise BusinessError("stale_quote", "报价不存在或不是当前计划")
        if quote["rules_hash"] != digest(self.rules) or quote["materials_hash"] != digest(
            self.state["materials"]
        ):
            raise BusinessError("stale_quote", "规则或素材已变更，请重新估算")
        return quote

    def generate_script(self, quote_id, deliverables):
        quote = self.get_quote(quote_id)
        if not quote["feasible"]:
            raise BusinessError("infeasible_quote", "报价不满足约束，不能生成")
        if quote["existing_hash"] != digest(self.state["results"]):
            raise BusinessError("stale_quote", "成功结果已变化，请重估剩余工作")
        if (
            not isinstance(deliverables, list)
            or not deliverables
            or len(set(deliverables)) != len(deliverables)
            or not set(deliverables) <= set(quote["plan"]["deliverables"])
        ):
            raise BusinessError("invalid_deliverables", "生成项目须属于当前报价且不重复")
        if any(k in self.state["results"] for k in deliverables):
            raise BusinessError("already_completed", "已成功交付物不得重复生成或收费")
        if self.state["spent"] + quote["remaining_cost"] > self.request["budget"] or not self.fits_time(
            quote["remaining_minutes"]
        ):
            raise BusinessError("constraint_changed", "剩余预算或时间已变化，请重估")
        completed, failures = [], []
        for key in deliverables:
            if (
                key == "channel_adaptation"
                and not {"video_script", "social_copy"} <= self.state["results"].keys()
            ):
                failures.append(dict(deliverable=key, error_code="dependency_missing", retryable=True))
                break
            if self.fault("generate:" + key) or (
                quote["plan"]["backend"] == "primary" and self.fault("primary")
            ):
                self.tick(self.rules["failure_minutes"])
                failures.append(
                    dict(
                        deliverable=key,
                        error_code="generator_unavailable",
                        retryable=self.faults.get("primary") != "always",
                    )
                )
                break
            try:
                rule = self.rules["deliverables"][key]
                content = (
                    self.generator(key, quote["plan"]["backend"], self)
                    if self.generator
                    else template(key, self)
                )
                validate_content(content, set(self.state["materials"]))
            except ExecutionLimit:
                raise
            except Exception as exc:
                self.tick(self.rules["failure_minutes"])
                failures.append(
                    dict(
                        deliverable=key,
                        error_code="generation_invalid",
                        message=type(exc).__name__,
                        retryable=True,
                    )
                )
                break
            if not self.fits_time(rule["minutes"] + 1):
                failures.append(dict(deliverable=key, error_code="deadline_infeasible", retryable=False))
                break
            result = dict(
                result_id=str(uuid4()),
                deliverable=key,
                content=content,
                cost=rule["cost"],
                minutes=rule["minutes"],
                backend=quote["plan"]["backend"],
                origin="model"
                if self.state["mode"] == "live" and quote["plan"]["backend"] == "primary"
                else "template",
                materials_hash=digest(self.state["materials"]),
            )
            self.state["results"][key] = result
            self.state["spent"] += rule["cost"]
            self.tick(rule["minutes"])
            self.persist()  # Every successful item and its charge commit together.
            completed.append(result)
        missing = [k for k in quote["plan"]["deliverables"] if k not in self.state["results"]]
        return dict(
            status="partial" if completed and failures else "failed" if failures else "succeeded",
            completed=completed,
            missing=missing,
            failures=failures,
            error_code=failures[0]["error_code"] if failures else None,
            message="保留成功项；补缺失项前重估；不得重复生成已成功项",
        )

    def save_plan(self, quote_id, campaign):
        quote = self.get_quote(quote_id)
        if not quote["feasible"]:
            raise BusinessError("infeasible_quote", "不可保存不满足约束的方案")
        required = set(quote["plan"]["deliverables"])
        if not required <= self.state["results"].keys():
            raise BusinessError(
                "dependency_missing",
                "当前计划有交付物尚未成功",
                missing=sorted(required - self.state["results"].keys()),
            )
        for key in required:
            if self.state["results"][key]["materials_hash"] != digest(self.state["materials"]):
                raise BusinessError("stale_results", "素材已变化，不能保存旧脚本")
        fields = ("goal", "audience", "message", "schedule", "roles", "suggested_metrics")
        if not isinstance(campaign, dict) or any(
            not isinstance(campaign.get(k), str) or not campaign[k].strip() for k in fields
        ):
            raise BusinessError("incomplete_campaign", "活动方案缺少必需运营字段", required_fields=fields)
        if self.state["spent"] > self.request["budget"] or not self.fits_time(1):
            raise BusinessError("constraint_changed", "保存时预算或截止时间不满足")
        if self.fault("save"):
            self.tick(1)
            raise BusinessError("save_failed", "模拟数据库提交前失败；脚本保留", retryable=True)
        previous = copy.deepcopy(self.state)
        self.tick(1)
        plan = dict(
            plan_id="plan-" + digest([self.request["request_id"], self.request["fingerprint"]])[:20],
            request=self.request,
            mode=self.state["mode"],
            campaign=campaign,
            task_plan=quote["plan"],
            results={k: self.state["results"][k] for k in quote["plan"]["deliverables"]},
            total_cost=self.state["spent"],
            elapsed_minutes=self.state["elapsed_minutes"],
            completed_at=self.current_time().isoformat(),
            channels=quote["plan"]["channels"],
        )
        plan["task_plan"] = copy.deepcopy(plan["task_plan"])
        for step in plan["task_plan"]["steps"]:
            step["status"] = "succeeded"
            if step["step_id"] in self.state["results"]:
                step["result_id"] = self.state["results"][step["step_id"]]["result_id"]
        self.state.update(status="completed", saved_plan_id=plan["plan_id"], reason=None)
        try:
            self.storage.save_plan(self.state, plan)
        except Exception as exc:
            # Preserve attempt object references so execute() can record failure.
            self.state.update(
                status=previous["status"],
                elapsed_minutes=previous["elapsed_minutes"],
                reason=previous.get("reason"),
            )
            self.state.pop("saved_plan_id", None)
            raise BusinessError("save_failed", "数据库事务未提交；脚本保留", retryable=True) from exc
        return dict(
            status="succeeded",
            plan_id=plan["plan_id"],
            total_cost=self.state["spent"],
            saved_store=str(self.storage.path),
            message="正式方案与完成状态已在同一事务提交",
        )


def validate_content(content, material_ids):
    if (
        not isinstance(content, dict)
        or not isinstance(content.get("text"), str)
        or len(content["text"].strip()) < 20
    ):
        raise ValueError("脚本正文不完整")
    citations = content.get("material_ids")
    if not isinstance(citations, list) or not citations or not set(citations) <= material_ids:
        raise ValueError("素材引用无效")


def template(key, engine):
    materials = list(engine.state["materials"].values())
    facts = "；".join(m["content"] for m in materials)
    theme = engine.request["theme"]
    channels = engine.state["quotes"][engine.state["active_quote"]]["plan"]["channels"]
    body = {
        "video_script": f"0—5秒｜画面：活动主题标题与相关场景特写；口播：‘一起关注{theme}。’\n"
        f"5—20秒｜画面：参与动作示意，字幕标注‘合成活动演示’；口播依据：{materials[0]['content']}\n"
        "20—30秒｜画面：规则卡与待补充的官方参与入口；口播：‘参与前请阅读完整规则，"
        "确认授权与参与条件。’\n审稿提示：具体地址、时间与入口未核实前不得补造。",
        "social_copy": f"标题：{theme}，让每一次参与都有清楚的指引\n"
        f"正文：{facts}\n行动引导：参与前先阅读运营发布的完整规则，"
        "确认授权与参与条件；具体入口由运营核实后补入。\n"
        "配图建议：使用已取得授权的主题场景素材，不使用未经授权的参与者肖像。",
        "channel_adaptation": "\n".join(
            f"渠道：{channel}\n标题：{theme}\n文案：{materials[0]['content']}\n"
            "行动引导：查看经运营确认的完整规则后参与；入口待确认。"
            for channel in channels
        ),
    }[key]
    return dict(
        text=f"主题：{engine.request['theme']}。{body}\n素材依据：{facts}\n以上为模板草稿，发布入口与具体排期由运营确认。",
        material_ids=[m["id"] for m in materials],
    )

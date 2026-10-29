"""Same Deep Agents graph for live and mock; middleware enforces all call limits."""

import json
from contextlib import nullcontext

from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from .schemas import ExecutionLimit, canonical, digest
from .subagents import has_current_review, load_subagents, review_fingerprint
from .tools import BUSINESS_TOOLS, PROJECT_ROOT


class AuditMiddleware(AgentMiddleware):
    def __init__(self, engine, *, actor="main", role="main", allowed_tools=None, delegates=None):
        self.engine = engine
        self.actor, self.role = actor, role
        self.allowed_tools = (
            set(allowed_tools) if allowed_tools is not None else BUSINESS_TOOLS | {"read_file", "write_todos"}
        )
        self.delegates = delegates or {}

    def wrap_model_call(self, request, handler):
        with self.engine.tool_lock:
            if self.engine.state["status"] == "completed":
                return ModelResponse(result=[AIMessage(content="正式方案已保存，任务完成。")])
            self.engine.count_model("decision" if self.role == "main" else f"subagent:{self.actor}")
        allowed = [t for t in request.tools if getattr(t, "name", None) in self.allowed_tools]
        if self.delegates:
            description = "subagent_type 必须使用以下完整名称，不能使用 writer/reviewer 角色标签。"
            description += "description 写明任务与依据：\n" + "\n".join(
                f"subagent_type={s.name} (role={s.role}): {s.description}" for s in self.delegates.values()
            )
            allowed = [
                t.model_copy(update={"description": description}) if t.name == "task" else t for t in allowed
            ]
        messages = request.messages
        if self.role != "main":
            with self.engine.tool_lock:
                state = self.engine.state
                quote = state["quotes"].get(state.get("active_quote"))
                context = dict(
                    agent_role=self.role,
                    request=self.engine.request,
                    quote=quote,
                    materials=state["materials"],
                    results=self.engine.current_results,
                    missing=self.engine.missing,
                    spent=state["spent"],
                    current_time=self.engine.current_time().isoformat(),
                )
                messages = [*messages, HumanMessage(content=canonical(dict(authoritative_context=context)))]
        result = handler(request.override(tools=allowed, messages=messages))
        for message in result.result:
            calls = getattr(message, "tool_calls", [])
            self.engine.trace.add(
                "model_decision",
                agent=self.actor,
                tool_calls=calls,
                public_reason=extract_text(message.content),
                usage=getattr(message, "usage_metadata", None),
            )
        return result

    def wrap_tool_call(self, request, handler):
        parent_lock = self.engine.dispatch_lock if self.role == "main" else nullcontext()
        with parent_lock:
            with self.engine.tool_lock:
                if self.engine.state["status"] == "completed":
                    return self._reject(request.tool_call, "request_completed")
            if request.tool_call["name"] == "task" and "task" in self.allowed_tools:
                return self._delegate(request, handler)
            with self.engine.tool_lock:
                return self._wrap_tool_call(request, handler)

    def _delegate(self, request, handler):
        call = request.tool_call
        with self.engine.tool_lock:
            self.engine.count_tool("task")
            spec = self.delegates.get(call["args"].get("subagent_type"))
            if spec is None:
                return self._reject(
                    call,
                    "subagent_not_allowed",
                    allowed_subagents={name: item.role for name, item in self.delegates.items()},
                    message="subagent_type 必须使用已配置名称，角色标签不是名称。"
                    "请从 allowed_subagents 的键中选择并重新调用 task。",
                )
            state = self.engine.state
            quote = state["quotes"].get(state.get("active_quote"))
            if spec.role == "reviewer" and (
                not quote or self.engine.missing
            ):
                return self._reject(call, "review_dependency_missing")
            record = dict(
                agent=spec.name,
                role=spec.role,
                status="running",
                run_id=state["active_run_id"],
                fingerprint=review_fingerprint(self.engine),
            )
            attempts_before = len(state["attempts"])
            state.setdefault("subagent_runs", []).append(record)
            self.engine.persist()
            self.engine.trace.add("subagent_start", **record, arguments=call["args"])
        # The framework dispatches child tools on a different thread: never hold tool_lock here.
        try:
            result = handler(request)
        except ExecutionLimit:
            record.update(status="failed", error_code="execution_limit")
            self.engine.persist()
            self.engine.trace.add("subagent_result", **record)
            raise
        except Exception as exc:
            record.update(status="failed", error_code="subagent_error")
            self.engine.persist()
            self.engine.trace.add("subagent_result", **record, exception_type=type(exc).__name__)
            return ToolMessage(
                content=canonical(
                    dict(
                        status="failed",
                        error_code="subagent_error",
                        message="子智能体执行失败，已成功业务结果保留，可重试或停止",
                        existing_results=self.engine.current_results,
                        observation=state.get("last_observation"),
                    )
                ),
                tool_call_id=call["id"],
                name="task",
                status="error",
            )
        update = getattr(result, "update", {})
        returned = update.get("messages", []) if isinstance(update, dict) else [result]
        text = "\n".join(extract_text(m.content) for m in returned if isinstance(m, ToolMessage))
        failed = any(getattr(m, "status", None) == "error" for m in returned) or not text.strip()
        with self.engine.tool_lock:
            status = "failed" if failed else "succeeded"
            if spec.role == "writer":
                attempts = [a for a in state["attempts"][attempts_before:] if a["tool"] == "generate_script"]
                observation = attempts[-1].get("result", {}) if attempts else {}
                status = observation.get("status", "failed")
                authoritative = dict(
                    status=status,
                    observation=observation,
                    existing_results=self.engine.current_results,
                    missing=self.engine.missing,
                    model_summary=text,
                    message="业务状态以 observation 为准；失败或部分成功需主智能体重规划",
                )
                if isinstance(update, dict):
                    for message in returned:
                        if isinstance(message, ToolMessage):
                            message.content = canonical(authoritative)
                            message.status = "error" if status == "failed" else "success"
            record.update(status=status, result=text)
            self.engine.persist()
            self.engine.trace.add("subagent_result", **record)
        return result

    def _reject(self, call, code="tool_not_allowed", **details):
        result = dict(status="failed", error_code=code, **details)
        self.engine.trace.add(
            "tool_rejected", agent=self.actor, tool=call["name"], arguments=call["args"], result=result
        )
        return ToolMessage(content=canonical(result), tool_call_id=call["id"], status="error")

    def _wrap_tool_call(self, request, handler):
        call = request.tool_call
        self.engine.count_tool(call["name"])
        if call["name"] not in self.allowed_tools:
            return self._reject(call)
        if (
            call["name"] == "save_plan"
            and self.engine.subagent_roles.get("reviewer")
            and not has_current_review(self.engine)
        ):
            return self._reject(call, "review_required")
        if call["name"] in BUSINESS_TOOLS:
            result = self.engine.execute(call["name"], call["args"], counted=True, agent=self.actor)
            return ToolMessage(
                content=canonical(result),
                tool_call_id=call["id"],
                name=call["name"],
                status="error" if result["status"] == "failed" else "success",
            )
        self.engine.trace.add("framework_tool_start", tool=call["name"], arguments=call["args"])
        result = handler(request)
        self.engine.trace.add("framework_tool_result", tool=call["name"], result=str(result)[:4000])
        return result


def extract_text(content):
    if isinstance(content, str):
        return content[:1000]
    return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")[
        :1000
    ]


def build_agent(engine, model):
    # Functions declare schemas only; calls execute in AuditMiddleware under shared state and limits.
    def search_materials(query: str, kinds: list[str] | None = None, reason: str = "") -> dict:
        """检索与原主题一致的本地合成素材，返回素材及缺失类型。"""
        return {}

    def estimate_plan(
        tier: str, backend: str = "primary", channels: list[str] | None = None, reason: str = ""
    ) -> dict:
        """登记计划并估算费用/耗时。tier=standard/economy，backend=primary/backup；超限时模型决定如何调整。"""
        return {}

    def generate_script(quote_id: str, deliverables: list[str], reason: str = "") -> dict:
        """按当前可行报价生成指定缺失项：video_script/social_copy/channel_adaptation；保留部分成功项。"""
        return {}

    def save_plan(quote_id: str, campaign: dict, reason: str = "") -> dict:
        """正式保存。campaign 必须含 goal/audience/message/schedule/roles/suggested_metrics 六个非空字符串。"""
        return {}

    tools = [
        StructuredTool.from_function(f) for f in (search_materials, estimate_plan, generate_script, save_plan)
    ]
    memory = (PROJECT_ROOT / "config/agent-memory.md").read_text(encoding="utf-8")
    skill = (PROJECT_ROOT / "skills/campaign-planning/SKILL.md").read_text(encoding="utf-8")
    specs = load_subagents()
    engine.state["subagents_config_sha256"] = digest([spec.model_dump() for spec in specs])
    registry = {tool.name: tool for tool in tools}
    delegates = {spec.name: spec for spec in specs}
    engine.subagent_roles = {spec.role: spec.name for spec in specs}
    subagents = []
    for spec in specs:
        from .models import OfflineModel

        child_model = (
            model.model_copy(update={"agent_role": spec.role}) if isinstance(model, OfflineModel) else model
        )
        subagents.append(
            dict(
                name=spec.name,
                description=spec.description,
                system_prompt=memory + "\n" + spec.system_prompt,
                # A writer delegation performs one business call, then returns
                # the actual observation to the parent for a new model decision.
                # End the child graph in the framework, rather than trusting a
                # prose-only instruction to stop retrying an invalidated quote.
                tools=[registry[name].model_copy(update={"return_direct": True}) for name in spec.tools],
                model=child_model,
                middleware=[
                    AuditMiddleware(engine, actor=spec.name, role=spec.role, allowed_tools=spec.tools)
                ],
            )
        )
    main_tools = BUSINESS_TOOLS | {"read_file", "write_todos"}
    if "writer" in engine.subagent_roles:
        main_tools = main_tools - {"generate_script"}
    if specs:
        main_tools = main_tools | {"task"}
    delegation_rules = "\n".join(
        f"role={s.role}, subagent_type={s.name}，{s.description}" for s in specs
    )
    # StateBackend is a virtual filesystem: no access to host SQLite, .env, or cost files.
    agent = create_deep_agent(
        model=model,
        tools=tools,
        middleware=[AuditMiddleware(engine, allowed_tools=main_tools, delegates=delegates)],
        memory=["/config/agent-memory.md"],
        skills=["/skills/"],
        subagents=subagents,
        system_prompt=memory + "\n只有四个业务工具可以改变业务状态。execute/文件写入不可用。"
        "逐个调用工具与 task，不并行调用。收到约束或错误后再决定动作。\n"
        "已启用的子智能体：\n" + delegation_rules + "\n"
        "task 的 subagent_type 必须使用上面的完整名称；writer/reviewer 仅为角色标签。"
        "若启用 writer，生成必须通过 task 委派给它；失败或部分成功后由你重新估算再委派。"
        "若启用 reviewer，所有内容成功后先通过 task 委派审查，再根据建议完善运营字段并保存。"
        "审查只是建议，不替代工具校验；子智能体调用也消耗全局调用额度。",
    )
    context = dict(
        request=engine.request,
        existing_results=engine.current_results,
        previous_error=engine.state.get("last_error"),
        previous_observation=engine.state.get("last_observation"),
        previous_plans=engine.state["plans"],
        previous_subagent_runs=engine.state.get("subagent_runs", []),
        current_content_reviewed=has_current_review(engine),
        mode=engine.state["mode"],
        current_time=engine.current_time().isoformat(),
        instruction="优先评估 preferred_tier；保持预算和必需渠道。先阅读 campaign-planning Skill。"
        "已有成功结果复用；无可行方案可直接结束并说明工具证据。",
    )
    inputs = dict(
        messages=[("user", json.dumps(context, ensure_ascii=False))],
        files={
            "/config/agent-memory.md": create_file_data(memory),
            "/skills/campaign-planning/SKILL.md": create_file_data(skill),
        },
    )
    return agent, inputs

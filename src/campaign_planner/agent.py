"""Same Deep Agents graph for live and mock; middleware enforces all call limits."""

import json

from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool

from .schemas import canonical
from .tools import BUSINESS_TOOLS, PROJECT_ROOT


class AuditMiddleware(AgentMiddleware):
    def __init__(self, engine):
        self.engine = engine

    def wrap_model_call(self, request, handler):
        self.engine.count_model("decision")
        allowed = [
            t
            for t in request.tools
            if getattr(t, "name", None) in BUSINESS_TOOLS | {"read_file", "write_todos"}
        ]
        result = handler(request.override(tools=allowed))
        for message in result.result:
            calls = getattr(message, "tool_calls", [])
            self.engine.trace.add(
                "model_decision",
                tool_calls=calls,
                public_reason=extract_text(message.content),
                usage=getattr(message, "usage_metadata", None),
            )
        return result

    def wrap_tool_call(self, request, handler):
        with self.engine.tool_lock:
            return self._wrap_tool_call(request, handler)

    def _wrap_tool_call(self, request, handler):
        call = request.tool_call
        self.engine.count_tool(call["name"])
        if call["name"] not in BUSINESS_TOOLS | {"read_file", "write_todos"}:
            result = dict(status="failed", error_code="tool_not_allowed")
            self.engine.trace.add("tool_rejected", tool=call["name"], arguments=call["args"], result=result)
            return ToolMessage(content=canonical(result), tool_call_id=call["id"], status="error")
        if call["name"] in BUSINESS_TOOLS:
            result = self.engine.execute(call["name"], call["args"], counted=True)
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
    # StateBackend is a virtual filesystem: no access to host SQLite, .env, or cost files.
    agent = create_deep_agent(
        model=model,
        tools=tools,
        middleware=[AuditMiddleware(engine)],
        memory=["/config/agent-memory.md"],
        skills=["/skills/"],
        subagents=[],
        system_prompt=memory + "\n只有四个业务工具可以改变业务状态。task/execute/文件写入不可用。"
        "逐个调用业务工具，不并行调用。收到约束或错误后再决定动作。",
    )
    context = dict(
        request=engine.request,
        existing_results=engine.state["results"],
        previous_error=engine.state.get("last_error"),
        previous_observation=engine.state.get("last_observation"),
        previous_plans=engine.state["plans"],
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

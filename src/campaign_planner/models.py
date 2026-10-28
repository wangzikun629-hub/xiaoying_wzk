"""Live OpenAI-compatible adapter and explicitly deterministic offline test model."""

import json
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from .schemas import canonical, digest
from .tools import template


def campaign_fields(theme):
    return dict(
        goal=f"围绕{theme}完成内容活动的准备与参与引导",
        audience="对该主题感兴趣的校园用户",
        message=f"用可核实素材清楚介绍{theme}的参与方式",
        schedule="相对排期：先核对素材与规则，再审稿，最后由运营确认并发布。",
        roles="运营负责规则确认与审稿，内容人员负责脚本与文案，发布人员负责渠道适配。",
        suggested_metrics="建议观察：有效投稿数、规则页阅读与互动；这些是建议指标，不是实际活动结果。",
    )


class OfflineModel(BaseChatModel):
    """Mock policy observes real tool state. It does not prove LLM reasoning."""

    engine: Any
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self):
        return "offline-deterministic-test-policy"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        e, s = self.engine, self.engine.state
        q = s["quotes"].get(s.get("active_quote"))
        observation = s.get("last_observation", {})
        action, args, reason = None, {}, ""
        if s["status"] == "completed":
            reason = "保存工具已经成功，结束。"
        elif not s["materials"]:
            if observation.get("error_code") == "no_materials":
                reason = "没有主题素材，不能生成有依据的活动方案。"
            elif observation.get("error_code") == "search_unavailable" and e.faults.get("search") == "always":
                reason = "检索持续不可用，停止并保留状态。"
            else:
                action, args = "search_materials", dict(query=e.request["theme"])
                reason = "先检索主题素材。"
        elif q is None:
            action, args = "estimate_plan", dict(tier=e.request["preferred_tier"], backend="primary")
            reason = "先评估偏好方案的费用和时间。"
        elif not q["feasible"]:
            economy = next((c for c in q["alternatives"] if c["tier"] == "economy"), None)
            if q["plan"]["tier"] == "standard" and economy and e.request["allow_simplification"]:
                action, args = "estimate_plan", dict(tier="economy", backend=q["plan"]["backend"])
                reason = "工具报告当前方案不可行，评估保留最低交付物的精简版。"
            else:
                reason = "已检查的完整内容包无法满足约束，停止并报告工具给出的缺口。"
        elif observation.get("error_code") in ("scope_violation", "no_materials"):
            reason = "无法满足硬约束，停止。"
        else:
            missing = [k for k in q["plan"]["deliverables"] if k not in s["results"]]
            failures = observation.get("failures", [])
            backend = q["plan"]["backend"]
            if failures:
                backend = "primary" if failures[0].get("retryable") else "backup"
            if missing and (failures or q["existing_hash"] != digest(s["results"])):
                action, args = (
                    "estimate_plan",
                    dict(tier=q["plan"]["tier"], backend=backend, channels=q["plan"]["channels"]),
                )
                reason = "保留成功交付物，根据错误重新估算剩余工作与后端。"
            elif missing:
                action, args = "generate_script", dict(quote_id=q["quote_id"], deliverables=missing)
                reason = "可行报价已确认，只生成缺少的交付物。"
            elif observation.get("error_code") == "save_failed" and e.faults.get("save") == "always":
                reason = "保存持续失败，保留脚本供续跑。"
            else:
                action, args = (
                    "save_plan",
                    dict(quote_id=q["quote_id"], campaign=campaign_fields(e.request["theme"])),
                )
                reason = "当前计划所需交付物均已成功，保存正式方案。"
        if action:
            args["reason"] = reason
            msg = AIMessage(
                content=reason,
                tool_calls=[dict(name=action, args=args, id=f"mock-{e.model_calls}", type="tool_call")],
            )
        else:
            msg = AIMessage(content=reason)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def live_model():
    from langchain_openai import ChatOpenAI

    key, name, url = (os.getenv(k, "").strip() for k in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"))
    if not key or not name:
        raise ValueError("请在 .env 配置 OPENAI_API_KEY、OPENAI_MODEL 和需要时的 OPENAI_BASE_URL")
    return ChatOpenAI(
        api_key=key,
        model=name,
        base_url=url or None,
        temperature=0,
        timeout=float(os.getenv("MODEL_TIMEOUT_SECONDS", "60")),
        max_retries=0,
        use_responses_api=False,
        model_kwargs={"parallel_tool_calls": False},
    )


def make_generator(mode, model):
    def generate(key, backend, engine):
        if mode == "mock" or backend == "backup":
            return template(key, engine)
        engine.count_model("script_generation:" + key)
        prompt = dict(
            theme=engine.request["theme"],
            deliverable=key,
            channels=engine.state["quotes"][engine.state["active_quote"]]["plan"]["channels"],
            materials=list(engine.state["materials"].values()),
            instruction="只返回 JSON 对象，字段 text 为至少100字的可用中文内容，material_ids 为引用素材ID列表。"
            "视频包含分镜和口播；图文包含标题正文CTA；改写包含各渠道内容。"
            "不得编造奖品、日期或已发生的效果；未知事实标记待运营确认。",
        )
        response = model.invoke([HumanMessage(content=canonical(prompt))])
        engine.trace.add(
            "content_generation", deliverable=key, usage=getattr(response, "usage_metadata", None)
        )
        text = response.content
        if not isinstance(text, str):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if text.strip().startswith("```"):
            text = text.strip().split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)

    return generate

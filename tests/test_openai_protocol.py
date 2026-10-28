"""No-network HTTP test: validates the adapter, never counted as live-model evidence."""

import json

import httpx
from langchain_openai import ChatOpenAI

from campaign_planner.models import campaign_fields
from campaign_planner.runner import run


def test_openai_compatible_round_trip_with_script_subcalls(tmp_path, request_data, monkeypatch):
    import campaign_planner.models as models

    requests = []

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        message = {"role": "assistant", "content": None}
        context = next(
            (
                json.loads(m["content"])["authoritative_context"]
                for m in reversed(body["messages"])
                if m["role"] == "user"
                and isinstance(m.get("content"), str)
                and m["content"].startswith('{"authoritative_context":')
            ),
            None,
        )
        if context and context["agent_role"] == "reviewer":
            assert not body.get("tools")
            assert set(context["results"]) == {"video_script", "social_copy"}
            message["content"] = json.dumps(
                {"summary": "协议测试审查", "issues": [], "suggested_changes": []}
            )
        elif not body.get("tools"):
            # This is a script-generation call, not a controller decision.
            message["content"] = json.dumps(
                {
                    "text": "协议测试合成脚本：" + "基于提供素材完成活动参与说明。" * 8,
                    "material_ids": ["campus-01"],
                },
                ensure_ascii=False,
            )
        else:
            last = next((m for m in reversed(body["messages"]) if m["role"] == "tool"), None)
            observation = json.loads(last["content"]) if last else {}
            if context and context["agent_role"] == "writer":
                offered = {t["function"]["name"] for t in body["tools"]}
                assert offered == {"generate_script"}
                if not last:
                    name, args = (
                        "generate_script",
                        {"quote_id": context["quote"]["quote_id"], "deliverables": context["missing"]},
                    )
                else:
                    name, args = None, {}
                    message["content"] = json.dumps(observation)
            elif not last:
                name, args = "search_materials", {"query": "毕业季校园影像征集"}
            elif "available_kinds" in observation:
                name, args = "estimate_plan", {"tier": "standard"}
            elif "budget_ok" in observation and not observation["budget_ok"]:
                name, args = "estimate_plan", {"tier": "economy"}
            elif "quote_id" in observation:
                name, args = (
                    "task",
                    {"subagent_type": "content-writer", "description": "生成当前报价缺失内容"},
                )
            elif "observation" in observation:
                assert observation["status"] == "succeeded"
                name, args = "task", {"subagent_type": "plan-reviewer", "description": "审查生成内容"}
            elif "summary" in observation:
                quote = next(
                    json.loads(m["content"])
                    for m in reversed(body["messages"])
                    if m["role"] == "tool" and "quote_id" in json.loads(m["content"])
                )
                name, args = (
                    "save_plan",
                    {"quote_id": quote["quote_id"], "campaign": campaign_fields("毕业季")},
                )
            else:
                name, args = None, {}
            if name:
                message["tool_calls"] = [
                    {
                        "id": f"protocol-{len(requests)}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ]
            elif message["content"] is None:
                message["content"] = "正式保存工具已经成功，结束。"
        payload = {
            "id": f"chatcmpl-{len(requests)}",
            "object": "chat.completion",
            "created": 1,
            "model": "protocol-test-double",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    model = ChatOpenAI(
        api_key="test-not-a-real-secret",
        model="protocol-test-double",
        base_url="https://protocol-test.invalid/v1",
        http_client=client,
        max_retries=0,
        use_responses_api=False,
    )
    monkeypatch.setattr(models, "live_model", lambda: model)
    result = run(
        request_data,
        mode="live",
        now="2030-06-01T10:00:00+08:00",
        db=tmp_path / "state.sqlite",
        output=tmp_path / "evidence",
    )
    client.close()
    assert result["status"] == "completed"
    assert result["total_cost"] == 8
    assert result["model_calls"] == len(requests) == 11
    assert len([r for r in requests if not r.get("tools")]) == 3  # two content calls and one reviewer
    assert [(r["role"], r["status"]) for r in result["subagent_runs"]] == [
        ("writer", "succeeded"),
        ("reviewer", "succeeded"),
    ]
    offered = {t["function"]["name"] for r in requests for t in r.get("tools", [])}
    assert "execute" not in offered and "task" in offered
    assert {"estimate_plan", "generate_script", "save_plan"} <= offered

# 内容任务规划 Agent

输入活动主题、预算和截止时间，生成一份带脚本、渠道、排期和费用明细的活动方案。预算不够时，模型可以缩减内容范围；工具失败时，可以重试缺失项或改用备用模板。方案只有写入 SQLite 后才算完成。

**题号：2。实际投入：4h。**

项目使用 Python、Deep Agents 和 CLI。内容创作与方案审查由两个可配置的子智能体完成，主 Agent 负责检索、估算、调整计划和保存。

## 验证结果

**121 项自动测试、19 个离线场景、19 个真实模型场景均通过，Ruff 和交付审计通过。**

测试与运行记录见[评估报告](docs/03-evaluation.md)。评审可先看[逐场景结果](examples/final-evaluation.md)和[真实模型动作记录](examples/final-decision-paths.md)，再查看对应目录中的输入、输出与 Trace。

- [需求与验收标准](docs/01-requirements.md)
- [实现与技术取舍](docs/02-solution.md)、[子智能体配置](docs/07-subagents.md)
- [运行记录索引](examples/README.md)、[验证边界](docs/04-ai-usage.md)
- [复盘](docs/05-retrospective.md)、[参考项目](docs/upstream.md)

## 安装

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)，本次验证使用 Python 3.12。在仓库根目录执行：

```powershell
uv --cache-dir .uv-cache sync --locked
```

依赖由 `uv.lock` 固定，主要版本为 Deep Agents 0.7.32、LangChain 1.4.7、LangGraph 1.2.18、langchain-openai 1.7.3。首次安装需要联网，离线模式不调用模型接口。运行时需要保留仓库内的配置和资料目录。

## 先用离线模式运行

```powershell
uv run python -m campaign_planner run --input examples/final-mock/C04-budget-replan/input.json --mode mock --now 2030-06-01T10:00:00+08:00
uv run pytest -q
uv run python scripts/run_examples.py --mode mock --output outputs/check-mock
```

第一条命令演示预算调整：标准版报价 12，超过预算 10，重新选择精简版后费用为 8。运行结果和 Trace 写入 `outputs/mock/` 下的本次运行目录，成功时同时导出 `plan.md`。相同请求再次执行会返回已保存方案，不重复生成或计费。

`mock` 使用确定性策略和模板，可以验证流程、计费和恢复逻辑，不能证明真实模型的决策效果。批量脚本覆盖 19 个场景，每个场景会保存输入、输出、Trace、元数据和验收断言。

## 使用真实模型

将 `.env.example` 复制为 `.env`，已有文件无需覆盖。填写支持 Chat Completions 工具调用的服务配置：

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://你的服务地址/v1
OPENAI_MODEL=你的模型名称
MODEL_TIMEOUT_SECONDS=60
```

`OPENAI_BASE_URL` 填服务根地址，不要附加 `/chat/completions`。DeepSeek 可用 `https://api.deepseek.com`。`.env` 已加入 Git 忽略规则，密钥不写入输入和 Trace。

```powershell
uv run python -m campaign_planner run --input examples/final-mock/C04-budget-replan/input.json --mode live --now 2030-06-01T10:00:00+08:00
uv run python scripts/run_examples.py --mode live --output outputs/check-live
```

真实运行会消耗模型 API 额度。每次运行默认最多 20 次模型请求、32 次工具调用，主模型、子模型和内容生成共用额度；达到上限返回 `incomplete/execution_limit`。接口不可用时会明确报错，不会自动改成 mock。

`--now` 固定评估时钟，便于复现实验；实际使用时省略它，并提供未来的截止时间。评估中的工具耗时按合成规则累计，不代表真实人工工期。

## 输入与输出

```json
{
  "theme": "毕业季校园影像征集",
  "budget": 10,
  "deadline": "2030-06-01T13:00:00+08:00",
  "preferred_tier": "standard",
  "allow_simplification": true
}
```

`theme`、`budget`、`deadline` 必填，预算为非负整数模拟单位。可选 `request_id` 和 `required_channels`；未提供 ID 时按输入生成。相同 ID 对应不同输入时返回冲突。

精简版包含视频脚本和图文文案，限一个渠道；标准版增加多渠道改写，至少两个渠道。用户指定的必需渠道必须保留，不能通过精简删除。

输出包含任务计划、步骤状态、工具尝试、成功结果、累计费用、耗时和保存 ID。状态为 `completed`、`needs_input`、`invalid_input` 或 `incomplete`，并发执行同一请求时可能返回 `in_progress`。CLI 成功退出码为 0，其余业务状态为 2，具体原因见输出 JSON。

`current_results` 是适用于当前渠道、素材版本和内容依赖的结果。`tool_results` 保留各交付物最近一次成功结果，替换下来的版本进入 `result_history`。切换计划不会清除已发生的费用；切回原范围时，可以复用仍然有效的历史内容。

## 故障与续跑

```powershell
uv run python -m campaign_planner run --input examples/final-mock/C03a-once-failure/input.json --mode mock --faults examples/faults/once.json --now 2030-06-01T10:00:00+08:00
uv run python -m campaign_planner show --request-id C03a-once-failure --mode mock
uv run python -m campaign_planner resume --request-id C03a-once-failure --mode mock
```

故障参数只用于测试，支持 `primary`、`generate:video_script`、`generate:social_copy`、`generate:channel_adaptation`、`search` 和 `save`，值为 `once` 或 `always`。续跑使用原数据库，保留成功结果、费用与时钟。重新试验请换请求 ID 或使用新的 `--db`，避免读到缓存。

## 已知限制与提交

资料、费用和工具耗时均为合成数据，不执行真实发布或支付。备用后端使用本地模板，并在结果中标记。代码会检查内容结构、素材引用和预算约束，事实是否准确、内容是否适合发布仍需人工审阅。

本次未实现界面、线上部署或生产级运行环境。第 04 份文档未统计 AI 辅助范围及个人修改明细，与最初的材料要求有差异。

仓库：[wangzikun629-hub/xiaoying_wzk](https://github.com/wangzikun629-hub/xiaoying_wzk)。最终提交 SHA 可在仓库根目录执行 `git rev-parse HEAD` 获取。

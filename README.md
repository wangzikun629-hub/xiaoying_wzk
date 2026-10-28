# 内容任务规划 Agent

基于 Deep Agents 的 CLI：输入主题、预算、截止时间，检索合成素材、估算成本、生成脚本、保存活动方案。模型根据工具观察选择精简、备用方式或停止；SQLite 保留成功结果、费用和失败历史。

**验证状态：当前已完成离线工程验证，真实模型决策证据待配置接口后生成。`mock` 是确定性测试策略，不能证明真实模型重规划效果。** 详见 [评估报告](docs/03-evaluation.md)。

## 评审入口

- [需求与验收映射](docs/01-requirements.md)、[实现与取舍](docs/02-solution.md)
- [实际评估结果](docs/03-evaluation.md)、[离线样例索引](examples/README.md)
- [AI 使用与个人贡献边界](docs/04-ai-usage.md)、[复盘](docs/05-retrospective.md)
- [参考项目与版本](docs/upstream.md)、[原始实施规划](docs/00-project-plan.md)

## 环境与安装

Python 3.11+、[uv](https://docs.astral.sh/uv/)；本次验证使用 Python 3.12。无需数据库服务和界面。请在仓库根目录执行：

```powershell
uv --cache-dir .uv-cache sync --locked
```

依赖由 `uv.lock` 固定。核心版本：Deep Agents 0.7.32、LangChain 1.4.7、LangGraph 1.2.18、langchain-openai 1.7.3。需联网安装依赖；安装后 mock 不访问模型接口。支持从源码检出目录运行，不承诺独立 wheel 脱离资料目录运行。

## 离线运行

```powershell
uv run python -m campaign_planner run --input examples/mock/C04-budget-replan/input.json --mode mock --now 2030-06-01T10:00:00+08:00
uv run pytest -q
uv run python scripts/run_examples.py --mode mock
```

第一条命令演示确定性策略从标准报价 12 改到精简报价 8；实际费用 8。结果 JSON、Trace 和成功方案 `plan.md` 保存到 `outputs/mock/` 下本次运行目录。相同请求默认返回已保存方案，不重复调用和收费。

批量样例会实际运行同一个 Deep Agents 图，生成输入、输出、Trace、元数据、断言文件；覆盖 17 个子场景，包括一次性错误、持续错误、部分成功、重复与续跑。同一输出目录重新生成会覆盖其中证据；需要保留历史实验时使用新的 `--output` 目录。

## 真实模型运行

将 `.env.example` 复制为 `.env`（已有文件不要覆盖），填入本地配置：

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://你的服务地址/v1
OPENAI_MODEL=你的模型名称
MODEL_TIMEOUT_SECONDS=60
```

服务必须支持 Chat Completions 工具调用。密钥不放入输入、Trace 或仓库。代码不会把 live 静默切为 mock。

```powershell
uv run python -m campaign_planner run --input examples/mock/C04-budget-replan/input.json --mode live --now 2030-06-01T10:00:00+08:00
uv run python scripts/run_examples.py --mode live --output examples/live
uv run python scripts/evaluate.py --mode live --repeats 3
```

第二条运行全部验收场景，第三条重复运行正常、一次性故障、持续故障和预算调整。它们会消耗模型 API 额度。每次运行最多 20 次模型请求（含脚本生成）、32 次工具调用；可通过 CLI 修改有限上限。

`--now` 是**固定评估时钟**，日期为可复现实验设置，不代表真实工期。实际业务运行应省略 `--now` 并使用未来截止时间。真实时钟检查包含墙钟流逝和累计模拟工作耗时。

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

前三个字段必填；预算为非负整数模拟单位。可选 `request_id`、`required_channels`。不提供 ID 时从规范化输入生成稳定 ID。相同 ID 不同输入返回冲突。默认 live/mock 数据库存储目录隔离。

输出包含状态、版本化任务计划、依赖、工具尝试与结果、实际费用、预计费用、累计耗时、保存 ID 或未完成原因。状态为 `completed/needs_input/invalid_input/incomplete`；并发请求可能返回 `in_progress`。CLI 成功退出码为 0，其他业务状态为 2，必须结合 JSON 判断原因。

## 故障注入、查看与续跑

故障 JSON 仅由测试运行器传入，例如：

```json
{"generate:social_copy": "once"}
```

支持 `primary`、`generate:video_script`、`generate:social_copy`、`generate:channel_adaptation`、`search`、`save`；值为 `once` 或 `always`。示例故障定义同时保存在各运行的元数据中。

```powershell
uv run python -m campaign_planner run --input examples/mock/C03a-once-failure/input.json --mode mock --faults examples/faults/once.json --now 2030-06-01T10:00:00+08:00
uv run python -m campaign_planner show --request-id C03a-once-failure --mode mock
uv run python -m campaign_planner resume --request-id C03a-once-failure --mode mock
```

续跑用相同数据库，复用已成功交付物、费用与时钟；开启新 run_id。已完成请求仍返回缓存。修改试验场景请使用新请求 ID 或新 `--db`，不要误把幂等缓存当作重新执行。

## 边界与提交

素材、费用和耗时均为合成规则；不执行内容发布、真实支付或外部运营任务。备用生成明确标为模板降级。模型内容的事实正确性不能只靠素材 ID 校验保证，需人工审阅；mock 内容评语见 [样例自评](examples/content-review.md)。

全部本地材料备齐后，仍需真实模型验证、候选人填写个人贡献与复盘、补充实际题号，以及 GitHub URL 和最终 commit SHA。当前不声称已满足真实模型决策验收。

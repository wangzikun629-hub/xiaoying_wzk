# 评估：已验证与待验证

当前：**离线工程验证已执行；真实模型决策未验证。** 下列样例由确定性Mock策略实际运行产生，没有伪造真实模型Trace。

自动测试命令：`uv run pytest -q`。实际结果存放 [examples/test-results.txt](../examples/test-results.txt)；覆盖输入校验、12→8重估算、部分成功计费、不可行缺口、幂等、保存失败、上限、续跑，以及旧报价、依赖和数据库异常。

当前完整测试为41项通过。另一个新建虚拟环境按锁文件离线安装并通过当时40项测试，实际记录见 [clean-environment.txt](../examples/clean-environment.txt)。随后增加的第41项用httpx.MockTransport验证OpenAI兼容HTTP工具调用和内部脚本请求往返，完全不联网，不算真实模型能力证据。Ruff代码检查通过。

最终复验在独立环境中运行当前41项测试，全部通过，见 [clean-final-test-results.txt](../examples/clean-final-test-results.txt)。`uv run --offline python scripts/audit_delivery.py` 检查交付链接和样例文件，通过。uv.toml将缓存放在项目目录，README中的uv run命令已实际执行验证。

场景命令：`uv run python scripts/run_examples.py --mode mock`。17个子场景实际结果见 [summary.json](../examples/mock/summary.json)，每个场景有输入、输出、Trace、元数据与程序断言。

| 场景 | 实际样例与核对重点 |
| --- | --- |
| 正常 | [C01](../examples/mock/C01-normal/output.json)：费用12，保存成功 |
| 缺信息 | [缺预算](../examples/mock/C02a-missing-budget/output.json)、[缺截止时间](../examples/mock/C02b-missing-deadline/output.json)：未调用模型/工具 |
| 一次错误 | [C03a Trace](../examples/mock/C03a-once-failure/trace.jsonl)：视频结果保留，仅补图文 |
| 持续错误 | [C03b Trace](../examples/mock/C03b-primary-unavailable/trace.jsonl)：主后端失败后选择备用 |
| 预算调整 | [C04 Trace](../examples/mock/C04-budget-replan/trace.jsonl)：报价12不可行，再报价8 |
| 无可行预算 | [C05](../examples/mock/C05-budget-infeasible/output.json)：缺口3，无生成费用 |
| 重复 | [首次](../examples/mock/C06-repeated-run/output.json)、[重复](../examples/mock/C06-repeated-run/second/output.json)：同方案、零新增调用 |
| 部分/无资料 | [部分素材](../examples/mock/C07a-partial-materials/output.json)、[部分生成](../examples/mock/C07b-partial-generation/output.json)、[零素材](../examples/mock/C07c-no-materials/output.json) |
| 上限 | [C08](../examples/mock/C08-execution-limit/output.json)：保留成功检索，明确未完成 |
| 时间不足 | [C09](../examples/mock/C09-deadline-infeasible/output.json)：不生成 |
| 输入冲突 | [C10](../examples/mock/C10-id-conflict/second/output.json)：原方案不覆盖 |
| 保存失败 | [C11](../examples/mock/C11-save-failure/output.json)：脚本保留，未标完成 |
| 续跑 | [生成续跑](../examples/mock/C12a-resume-generation/resume/output.json)、[保存续跑](../examples/mock/C12b-resume-save/resume/output.json)：复用成功结果，累计费用8 |

实际调试中发现并修复：LangGraph工具在线程池运行导致SQLite同线程限制错误；检索泛化“校园”标签引入不相关素材；保存事务失败时恢复状态对象可能使失败尝试记录丢失。修复分别是串行锁下跨线程连接、主题相关性优先匹配、仅恢复事务涉及字段且保留尝试对象。初轮测试出现2项失败，其中标准耗时预期应为1+1+120+1=123，已纠正测试；其余为检索问题，已修复实现并重新验证。

真实验证待配置接口：`uv run python scripts/run_examples.py --mode live --output examples/live`，然后 `uv run python scripts/evaluate.py --mode live --repeats 3`。必须保留所有结果，至少取得预算调整与工具失败的真实不同路径；直接选择8不能冒充已经观察12后改选。

关键限制：合成费用和工期没有验证真实运营成本；检索采用本地标签相关性，无语义向量；脚本只校验结构和素材ID，不能自动保证事实完全正确；备用是模板降级；SQLite不能保证真实外部API请求不被重复计token；17个Mock场景通过不等于真实模型有相同表现。自评见 [content-review.md](../examples/content-review.md)。

最终验收仍待真实模型记录、候选人自己的验证与贡献记录、题号、GitHub URL和最终SHA。没有把这些待完成项记为通过。

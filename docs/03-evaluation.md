# 评估：已验证与待验证

当前：**47项自动测试通过，最终17个真实子场景全部通过，四类关键场景各3次重复评估共12/12通过。** 模型为用户配置的deepseek-flash。下表保留初始离线证据，最终真实结果在后文单独记录；费用和时间仍为合成规则。

自动测试命令：`uv run pytest -q`。实际结果存放 [examples/test-results.txt](../examples/test-results.txt)；覆盖输入校验、12→8重估算、部分成功计费、不可行缺口、幂等、保存失败、上限、续跑，以及旧报价、依赖和数据库异常。

初版完整测试为41项通过。另一个新建虚拟环境按锁文件离线安装并通过当时40项测试，实际记录见 [clean-environment.txt](../examples/clean-environment.txt)。随后增加的第41项用httpx.MockTransport验证OpenAI兼容HTTP工具调用和内部脚本请求往返，完全不联网，不算真实模型能力证据。最终47项结果见后文，Ruff代码检查通过。

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

真实验证使用用户本地配置的deepseek-flash。最初接口根地址误填/chat/completions导致404，修正后成功；密钥未展示或入库。初始错误见[连接失败](../examples/live-initial/C04-budget-replan/output.json)、[404记录](../examples/live-network-check/C04-budget-replan/trace.jsonl)。

首轮真实全量：[examples/live/summary.json](../examples/live/summary.json)，17个子场景通过原有断言。其中[真实预算Trace](../examples/live/C04-budget-replan/trace.jsonl)、[一次错误Trace](../examples/live/C03a-once-failure/trace.jsonl)、[持续错误Trace](../examples/live/C03b-primary-unavailable/trace.jsonl)证明不同观察后的不同动作；[续跑](../examples/live/C12a-resume-generation/resume/output.json)保留已成功视频并补齐剩余项。

人工复查发现初始精简方案仍可能安排多个渠道。原费用表按交付物计价，数值没有超预算，但与单渠道精简的业务范围定义不一致。新增economy单渠道校验、保留必需渠道的替代报价、生成范围提示及接口根地址检查，补充4项回归测试，当前45项通过，见[test-results-live-update.txt](../examples/test-results-live-update.txt)。范围修复后的Mock17项通过，见[mock-scope-validated](../examples/mock-scope-validated/summary.json)。

中间复验live-validated为16/17通过，[C09失败记录](../examples/live-validated/C09-deadline-infeasible/output.json)显示模型合理停止、没有继续花费，但宿主误报current_plan_over_budget。实际预算可负担的替代方案同样超时，应返回deadline_infeasible。已修正候选判断，并分开返回最小时间缺口和当前报价时间缺口；回归测试验证33与93分钟。保存层同时检查排期、角色与核心信息中的已知渠道名，防止文字再次引入未选择渠道。新增2项回归后完整测试47项通过，见[test-results-live-final.txt](../examples/test-results-live-final.txt)。

最终代码重新执行的实际结果：

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 最终Mock | 17/17通过 | [mock-final](../examples/mock-final/summary.json) |
| 最终真实全量 | 17/17通过 | [live-final](../examples/live-final/summary.json) |
| 最终真实重复评估 | 四类各3次，12/12通过 | [evaluation-final](../examples/evaluation-final/live-summary.json) |
| 最终自动测试 | 47项通过 | [测试日志](../examples/test-results-live-final.txt) |

最终真实Trace重点入口：[预算12→8](../examples/live-final/C04-budget-replan/trace.jsonl)、[一次失败后补缺失项](../examples/live-final/C03a-once-failure/trace.jsonl)、[持续故障换备用](../examples/live-final/C03b-primary-unavailable/trace.jsonl)、[时间不足停止](../examples/live-final/C09-deadline-infeasible/output.json)、[重复执行](../examples/live-final/C06-repeated-run/second/output.json)、[生成续跑](../examples/live-final/C12a-resume-generation/resume/output.json)、[保存续跑](../examples/live-final/C12b-resume-save/resume/output.json)。完整场景对应关系与上表C01～C12相同。

最终执行命令：`uv run python scripts/run_examples.py --mode live --output examples/live-final`，以及`uv run python scripts/evaluate.py --mode live --repeats 3 --output examples/evaluation-final`。另一个中间版本的12项重复结果保存在evaluation，未与最终批次混为更大样本。小样本只说明本次固定配置表现，不外推普遍可靠性。

关键限制：合成费用和工期没有验证真实运营成本；检索采用本地标签相关性，无语义向量；脚本只校验结构和素材ID，不能自动保证事实完全正确；备用是模板降级；SQLite不能保证真实外部API请求不被重复计token；17个Mock场景通过不等于真实模型有相同表现。自评见 [content-review.md](../examples/content-review.md)。

用户要求暂不推送GitHub，本轮只保留本地提交。正式提交仍需候选人自己的验证与贡献记录、题号、GitHub URL和最终SHA。没有把这些待完成项记为通过。

最终交付核对见[final-delivery-check.json](../examples/final-delivery-check.json)：54份最终运行元数据的源码摘要与当前源码一致，实施与证据目录扫描未发现本地实际API密钥泄漏；.env保持Git忽略。该核对不代替候选人自己的材料审阅。

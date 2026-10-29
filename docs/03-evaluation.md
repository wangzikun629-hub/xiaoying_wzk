# 评估：已验证与待验证


本轮修复预算缺口与未执行步骤状态两个问题：预算10、必需双渠道时输出缺口2；未执行的图文保持pending、依赖未满足时为blocked，只有实际失败的项目标记failed。原有5项新增测试及原测试中的额外断言对旧提交共得到6项失败，在本轮实现上均通过。[修复前复现日志](../examples/review-before-fix-regressions.txt)保留了对旧提交执行这些检查的6项失败，不与本轮成功日志混算。

当前自动测试**84项通过**，见[测试日志](../examples/review-test-results.txt)；[Ruff检查](../examples/review-ruff-results.txt)通过；[离线19个场景](../examples/review-mock/summary.json)全部通过。新增C13覆盖必需渠道的预算缺口，C14覆盖首项失败后的后续步骤状态。C14不要求真实模型走固定序列：若模型单独完成图文则保留成功；未尝试项按当前可行性显示pending或blocked，不能仅因出现在批量请求中就标失败。

本轮真实模型证据使用提交者既有DeepSeek配置，仅包含合成场景、资料、规则和工具观察，最终结果见[本轮汇总](../examples/review-live/summary.json)。旧yaml-live/yaml-mock以及79项测试日志保留为历史，不当作本轮源码证据。

记录边界：题号2，实际投入3.5小时（提交者自报）。按提交者要求，第04份文档继续省略辅助范围和个人修改明细，因此**该文档内容仍未完全满足最初题面的材料要求**。不把这项记为达标，也不将自动执行结果写成提交者的个人经历。

本轮最终真实验证**19/19通过**，按各场景最终实际输出汇总；重跑不作为额外独立样本。预算调整、部分失败只补缺失项、持续故障换备用及新增C13/C14的实际步骤与公开依据见[动态路径](../examples/review-decision-paths.md)，全量输入输出与状态见[逐场景结果](../examples/review-evaluation.md)。C13返回budget_infeasible、缺口2、费用0；C14按实际失败与依赖区分failed/pending/blocked，未把未执行项目记成失败。本轮没有额外重复三轮评估，不将历史12/12计入当前样本。

本轮最终交付核对：[审计日志](../examples/review-delivery-audit.txt)为PASS；[核对报告](../examples/review-delivery-check.json)确认46份本轮运行元数据与源码摘要一致，84项自动测试、19个离线场景及19个真实场景通过。对1871个实施及证据文件和1162个历史文件对象进行本地已配置密钥的精确匹配检查，未发现匹配；这不等于保证能识别所有形式的凭据。第04份文档的原始材料缺口单独记录，不随技术审计PASS而标记通过。

## 历史记录（以下对应此前源码）

当前 YAML 子智能体版本：**79项自动测试通过，17个离线场景全部通过，Ruff检查通过**。当前日志见[自动测试](../examples/test-results-current.txt)、[代码检查](../examples/ruff-results-current.txt)、[离线汇总](../examples/yaml-mock/summary.json)。覆盖实际Deep Agents父子图执行、一次失败后的部分成功复用、全局额度与续跑、子智能体工具越权拒绝、未配置委派拒绝、子模型异常恢复、跳过审查拒绝、虚假成功摘要拒绝、新计划使旧审查失效、YAML配置校验、改名及启停。OpenAI兼容接口通过本地MockTransport验证主模型、创作子模型、审查子模型和内部生成请求，共11次请求且全部计入上限，该协议测试不证明真实模型效果。

最终当前实现的**17个真实场景全部通过**，见[真实汇总](../examples/yaml-live/summary.json)、[逐场景实际结果](../examples/current-evaluation.md)、[三条动态路径](../examples/current-decision-paths.md)。C07b部分成功后交回主Agent重估并只补缺失项；C12a首次因执行上限停止，费用4、视频保留，续跑后费用8；C12b保存失败后复用全部脚本完成保存。不同观察后的动作及公开依据可由原始Trace核对，未记录隐藏推理。

重现可执行`uv run python scripts/run_examples.py --mode live --output outputs/review-yaml-live`。本轮为缩短等待，将17个互不依赖场景分三批运行，使用`--scenario`选择互不重叠的场景，并用`--summary-name batch-N-summary.json`分别保存汇总；三份批次原始汇总保留在yaml-live中，summary.json从这三份实际记录合并并核对17个场景唯一性。各场景使用独立临时数据库，未共享账目。此次未对当前架构额外做三轮重复评估，不把旧版12/12混入本轮样本。

本轮先发生[模型连接失败](../examples/yaml-live-connection-failure/summary.json)，随后在可访问模型的环境实际运行。初始批次[已完成9个、通过7个](../examples/yaml-live-initial/summary.json)，C04与C07a失败：模型已选出可行方案，但task参数subagent_type填写角色writer而非配置名称content-writer，连续收到subagent_not_allowed后停止；没有生成或伪造完成。发现后停止批次，C07b只保留了中断时Trace。归档目录中的原始绝对路径指向搬移前位置，应读取归档内相邻trace.jsonl，不据此混用新批次Trace。

修复措施是明确工具描述与主提示中的名称参数，并在拒绝结果返回allowed_subagents名称到角色映射，让模型选择正确名称再次调用；没有放宽权限或自动把角色别名映射成配置对象。新增两项回归分别验证默认名称及改名配置下，错误名称被拒绝，模型读取工具反馈后修正并完成任务。

名称修复后的[真实批次](../examples/yaml-live-name-fixed/summary.json)完成14例、通过13例，C07b出现新的失败：writer在部分成功后反复使用旧报价，没有按指令交回主Agent，最后返回incomplete/execution_limit，费用4且已成功视频保留。发现后停止批次，C11保留中断Trace。修复为仅在writer子图的generate_script工具设置框架return_direct=True，一次工具调用结束后直接交回主Agent，模型仍负责父级重估算及再次委派，不自动替它选择重试或备用。新增回归让子模型在收到工具结果后试图继续调用时测试失败，验证该循环入口已被执行骨架切断；协议测试因不再请求writer总结由12次变为11次。当前完整验证与[动态路径摘要](../examples/current-decision-paths.md)对应最终代码，历史真实证据不作为当前架构的效果证明。

以下为此前单Agent版本的历史评估：**47项自动测试通过，最终17个真实子场景全部通过，四类关键场景各3次重复评估共12/12通过。** 模型为用户配置的deepseek-flash。下表保留初始离线证据，历史最终真实结果在后文单独记录；费用和时间仍为合成规则。

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

此前单Agent最终代码重新执行的实际结果：

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 最终Mock | 17/17通过 | [mock-final](../examples/mock-final/summary.json) |
| 最终真实全量 | 17/17通过 | [live-final](../examples/live-final/summary.json) |
| 最终真实重复评估 | 四类各3次，12/12通过 | [evaluation-final](../examples/evaluation-final/live-summary.json) |
| 最终自动测试 | 47项通过 | [测试日志](../examples/test-results-live-final.txt) |

最终真实Trace重点入口：[预算12→8](../examples/live-final/C04-budget-replan/trace.jsonl)、[一次失败后补缺失项](../examples/live-final/C03a-once-failure/trace.jsonl)、[持续故障换备用](../examples/live-final/C03b-primary-unavailable/trace.jsonl)、[时间不足停止](../examples/live-final/C09-deadline-infeasible/output.json)、[重复执行](../examples/live-final/C06-repeated-run/second/output.json)、[生成续跑](../examples/live-final/C12a-resume-generation/resume/output.json)、[保存续跑](../examples/live-final/C12b-resume-save/resume/output.json)。完整场景对应关系与上表C01～C12相同。

最终执行命令：`uv run python scripts/run_examples.py --mode live --output examples/live-final`，以及`uv run python scripts/evaluate.py --mode live --repeats 3 --output examples/evaluation-final`。另一个中间版本的12项重复结果保存在evaluation，未与最终批次混为更大样本。小样本只说明本次固定配置表现，不外推普遍可靠性。

关键限制：合成费用和工期没有验证真实运营成本；检索采用本地标签相关性，无语义向量；脚本只校验结构和素材ID，不能自动保证事实完全正确；备用是模板降级；SQLite不能保证真实外部API请求不被重复计token；17个Mock场景通过不等于真实模型有相同表现。自评见 [content-review.md](../examples/content-review.md)。

题号已确认2，实际投入3.5小时。正式提交仍需GitHub URL和最终SHA；仓库发布状态以README为准。

此前单Agent版本的交付核对见[final-delivery-check.json](../examples/final-delivery-check.json)，其源码一致性结果仅对当时版本成立。当前检查脚本已覆盖yaml-mock与yaml-live，并比对这两组全部元数据（含重复与续跑）的源码摘要；历史分组保留原摘要，不要求与当前实现相同。.env保持Git忽略。

当前最终核对见[current-delivery-check.json](../examples/current-delivery-check.json)：42份运行元数据与最终源码摘要一致，扫描的1613个实施及证据文件未匹配到本地配置中的实际密钥；新提交前还检查了851个历史文件对象，未匹配该密钥。该检查不保证发现所有可能的凭据格式。[交付检查日志](../examples/delivery-audit-current.txt)为PASS，检查当前场景完整性、文档链接和源码一致性。发布目标为用户指定的[GitHub仓库](https://github.com/wangzikun629-hub/xiaoying_wzk)，远程提交状态需另行核对。

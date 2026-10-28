# 实际运行证据

当前YAML子智能体版本的证据入口：[真实全量17/17](yaml-live/summary.json)、[离线全量17/17](yaml-mock/summary.json)、[79项自动测试](test-results-current.txt)、[Ruff检查](ruff-results-current.txt)、[逐场景实际结果](current-evaluation.md)、[三条真实动态路径](current-decision-paths.md)。当前版本应优先核对这两组的输入、输出、Trace、元数据、断言及成功方案。真实运行的具体结果与已知限制见[评估报告](../docs/03-evaluation.md)。

本轮失败记录：[连接失败批次](yaml-live-connection-failure/summary.json)、[委派名称错误初始批次](yaml-live-initial/summary.json)。初始批次完成9例、通过7例后停止，C07b保留中断Trace；C04和C07a因把writer角色误当配置名称而失败。归档中的绝对trace_path为运行时原始位置，应打开归档内相邻trace.jsonl核对，不与修复后新批次混用。yaml-mock-initial保留修复前17个离线场景。

名称修复后又发现[创作子智能体重复旧报价的失败](yaml-live-name-fixed/summary.json)：完成14例、通过13例，C07b达到20次模型上限而未完成，C11在停止批次时中断。随后用框架return_direct结束单次创作子图，将实际观察交回主Agent。yaml-mock-name-fixed保留该修复前17个离线场景；当前yaml-live/yaml-mock与这些历史批次分别保存。

以下为此前单Agent版本的历史记录：

`mock/` 为初始离线样例；每个目录含input.json、output.json、trace.jsonl、run-metadata.json、assertions.json，成功时含plan.md。复执行与续跑分别在second/、resume/。汇总见[mock/summary.json](mock/summary.json)。

mock Trace中的model_decision来自确定性测试模型经过实际Deep Agents图的运行，不是预先写入的Trace，也不证明真实LLM决策。live目录使用用户配置的deepseek-flash真实接口，所有文件标记mode。

证据分组：`live-initial/`为沙箱连接失败及连通性诊断，`live-network-check/`为错误根地址导致404，`live-pilot/`为首个真实预算成功路径；`live/`为首轮17个真实子场景；`mock-scope-validated/`为范围修复后的17个离线场景；`live-validated/`为范围修复后的真实全量；`evaluation/`为三轮独立关键场景重复评估。各组源码摘要可不同，原始结果保留，不覆盖成新版本成功。

此前单Agent最终批次：[live-final全量17/17](live-final/summary.json)、[evaluation-final三轮12/12](evaluation-final/live-summary.json)、[mock-final17/17](mock-final/summary.json)、[47项测试](test-results-live-final.txt)。中间live-validated为16/17，失败已修复且原证据保留。这些记录不冒充当前YAML子智能体版本的结果。

| 目录 | 场景 |
| --- | --- |
| C01-normal | 正常标准方案 |
| C02a/b | 缺预算、缺截止时间 |
| C03a/b | 一次性图文失败、持续主后端失败 |
| C04-budget-replan | 预算10、报价12→8 |
| C05-budget-infeasible | 预算5、缺口3 |
| C06-repeated-run | 重复执行 |
| C07a/b/c | 部分素材、部分生成、零素材 |
| C08-execution-limit | 达到运行上限 |
| C09-deadline-infeasible | 时间不足 |
| C10-id-conflict | 同ID不同输入 |
| C11-save-failure | 保存失败 |
| C12a/b | 生成/保存失败后的续跑 |

生成命令：`uv run python scripts/run_examples.py --mode mock`。批量运行使用临时数据库隔离场景，数据库执行结束后清理；Trace与结果包含完整业务证据，saved_store记录生成时路径，不承诺该临时数据库仍存在。需要实际查询数据库时用CLI默认outputs存储运行单个样例。

测试结果见[test-results.txt](test-results.txt)，内容评语见[content-review.md](content-review.md)。运行元数据使用源码内容摘要识别实际工作文件，不冒充最终Git commit。

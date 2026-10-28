# 实际运行证据

`mock/` 为已经执行的离线样例；每个目录含input.json、output.json、trace.jsonl、run-metadata.json、assertions.json，成功时含plan.md。复执行与续跑分别在second/、resume/。汇总见[mock/summary.json](mock/summary.json)。

Trace中的model_decision来自确定性Mock模型经过实际Deep Agents图的运行，不是预先写入的Trace，也不证明真实LLM决策。所有文件标记mode。真实模型证据应放live/；当前待配置接口，未放置假Trace或空成功报告。

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

# 当前版本场景实际结果

真实17/17通过；离线17/17通过。每个真实目录都含输入、输出、Trace、元数据和断言。重复与续跑见second/、resume/。

| 场景 | 首次实际状态 / 原因 | 实际费用 | 验收断言 | 证据 |
| --- | --- | --- | --- | --- |
| C01-normal | completed | 12 | 通过 | [输入](yaml-live/C01-normal/input.json) · [输出](yaml-live/C01-normal/output.json) · [Trace](yaml-live/C01-normal/trace.jsonl) · [断言](yaml-live/C01-normal/assertions.json) |
| C02a-missing-budget | needs_input / 请补充必填信息 | 未执行 | 通过 | [输入](yaml-live/C02a-missing-budget/input.json) · [输出](yaml-live/C02a-missing-budget/output.json) · [Trace](yaml-live/C02a-missing-budget/trace.jsonl) · [断言](yaml-live/C02a-missing-budget/assertions.json) |
| C02b-missing-deadline | needs_input / 请补充必填信息 | 未执行 | 通过 | [输入](yaml-live/C02b-missing-deadline/input.json) · [输出](yaml-live/C02b-missing-deadline/output.json) · [Trace](yaml-live/C02b-missing-deadline/trace.jsonl) · [断言](yaml-live/C02b-missing-deadline/assertions.json) |
| C03a-once-failure | completed | 8 | 通过 | [输入](yaml-live/C03a-once-failure/input.json) · [输出](yaml-live/C03a-once-failure/output.json) · [Trace](yaml-live/C03a-once-failure/trace.jsonl) · [断言](yaml-live/C03a-once-failure/assertions.json) |
| C03b-primary-unavailable | completed | 8 | 通过 | [输入](yaml-live/C03b-primary-unavailable/input.json) · [输出](yaml-live/C03b-primary-unavailable/output.json) · [Trace](yaml-live/C03b-primary-unavailable/trace.jsonl) · [断言](yaml-live/C03b-primary-unavailable/assertions.json) |
| C04-budget-replan | completed | 8 | 通过 | [输入](yaml-live/C04-budget-replan/input.json) · [输出](yaml-live/C04-budget-replan/output.json) · [Trace](yaml-live/C04-budget-replan/trace.jsonl) · [断言](yaml-live/C04-budget-replan/assertions.json) |
| C05-budget-infeasible | incomplete / budget_infeasible | 0 | 通过 | [输入](yaml-live/C05-budget-infeasible/input.json) · [输出](yaml-live/C05-budget-infeasible/output.json) · [Trace](yaml-live/C05-budget-infeasible/trace.jsonl) · [断言](yaml-live/C05-budget-infeasible/assertions.json) |
| C06-repeated-run | completed | 8 | 通过 | [输入](yaml-live/C06-repeated-run/input.json) · [输出](yaml-live/C06-repeated-run/output.json) · [Trace](yaml-live/C06-repeated-run/trace.jsonl) · [断言](yaml-live/C06-repeated-run/assertions.json) |
| C07a-partial-materials | completed | 8 | 通过 | [输入](yaml-live/C07a-partial-materials/input.json) · [输出](yaml-live/C07a-partial-materials/output.json) · [Trace](yaml-live/C07a-partial-materials/trace.jsonl) · [断言](yaml-live/C07a-partial-materials/assertions.json) |
| C07b-partial-generation | completed | 8 | 通过 | [输入](yaml-live/C07b-partial-generation/input.json) · [输出](yaml-live/C07b-partial-generation/output.json) · [Trace](yaml-live/C07b-partial-generation/trace.jsonl) · [断言](yaml-live/C07b-partial-generation/assertions.json) |
| C07c-no-materials | incomplete / no_materials | 0 | 通过 | [输入](yaml-live/C07c-no-materials/input.json) · [输出](yaml-live/C07c-no-materials/output.json) · [Trace](yaml-live/C07c-no-materials/trace.jsonl) · [断言](yaml-live/C07c-no-materials/assertions.json) |
| C08-execution-limit | incomplete / execution_limit | 0 | 通过 | [输入](yaml-live/C08-execution-limit/input.json) · [输出](yaml-live/C08-execution-limit/output.json) · [Trace](yaml-live/C08-execution-limit/trace.jsonl) · [断言](yaml-live/C08-execution-limit/assertions.json) |
| C09-deadline-infeasible | incomplete / deadline_infeasible | 0 | 通过 | [输入](yaml-live/C09-deadline-infeasible/input.json) · [输出](yaml-live/C09-deadline-infeasible/output.json) · [Trace](yaml-live/C09-deadline-infeasible/trace.jsonl) · [断言](yaml-live/C09-deadline-infeasible/assertions.json) |
| C10-id-conflict | completed | 8 | 通过 | [输入](yaml-live/C10-id-conflict/input.json) · [输出](yaml-live/C10-id-conflict/output.json) · [Trace](yaml-live/C10-id-conflict/trace.jsonl) · [断言](yaml-live/C10-id-conflict/assertions.json) |
| C11-save-failure | incomplete / save_failed | 8 | 通过 | [输入](yaml-live/C11-save-failure/input.json) · [输出](yaml-live/C11-save-failure/output.json) · [Trace](yaml-live/C11-save-failure/trace.jsonl) · [断言](yaml-live/C11-save-failure/assertions.json) |
| C12a-resume-generation | incomplete / execution_limit | 4 | 通过 | [输入](yaml-live/C12a-resume-generation/input.json) · [输出](yaml-live/C12a-resume-generation/output.json) · [Trace](yaml-live/C12a-resume-generation/trace.jsonl) · [断言](yaml-live/C12a-resume-generation/assertions.json) |
| C12b-resume-save | incomplete / save_failed | 8 | 通过 | [输入](yaml-live/C12b-resume-save/input.json) · [输出](yaml-live/C12b-resume-save/output.json) · [Trace](yaml-live/C12b-resume-save/trace.jsonl) · [断言](yaml-live/C12b-resume-save/assertions.json) |

# 运行记录

当前版本的评审入口：

- [121 项自动测试](submission-tests.txt)、[Ruff 检查](submission-ruff.txt)
- [19 个离线场景](final-mock/summary.json)、[19 个真实模型场景](final-live/summary.json)
- [逐场景结果](final-evaluation.md)、[模型动作记录](final-decision-paths.md)
- [源码与材料核对](submission-check.json)、[交付审计](submission-audit.txt)

每个场景目录都包含 input.json、output.json、trace.jsonl、run-metadata.json 和 assertions.json。完成的方案另有 plan.md；重复和续跑记录位于 second 或 resume 子目录。

final-mock 和 final-live 对应当前代码。review-* 是 84 项测试版本的记录，yaml-* 是此前子智能体版本，其他目录为更早的试验。历史记录保留运行时的源码摘要，与当前结果分开使用；过程和已知问题见[历史评估](../docs/history-evaluation.md)。

[本次初轮记录](final-live-initial/summary.json)为18/19；C14 在重新报价后尚未执行，旧断言误要求 failed。修正断言后重新运行全部场景，不改写初轮断言和 Trace。归档中的绝对 trace_path 为原始运行位置，请读取归档内相邻文件。

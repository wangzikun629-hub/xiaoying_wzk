# 本轮真实动态路径

依据实际输入、输出与Trace整理，仅列业务工具；task委派与所有模型动作见原始Trace。公开依据取自attempt.reason，不记录隐藏推理。费用为合成单位。

## C04-budget-replan

最终状态：completed；原因：None；费用：8；预算缺口：0。[输入](review-live/C04-budget-replan/input.json) · [输出](review-live/C04-budget-replan/output.json) · [Trace](review-live/C04-budget-replan/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：按用户偏好先评估 standard，双渠道满足最低要求且素材覆盖 |
| 2 / main | estimate_plan {"tier": "standard", "channels": ["校园公众号", "短视频平台"], "backend": "primary"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"minimum_budget_gap":0,"deadline_ok":true} | estimate_plan：在预算内尝试保留 standard 双渠道，仅换后端重新询价 |
| 3 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号", "短视频平台"], "tier": "standard"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"minimum_budget_gap":0,"deadline_ok":true} | estimate_plan：预算 10 无法覆盖标准版 12，按允许精简降为 economy 单渠道 |
| 4 / main | estimate_plan {"backend": "primary", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：按已批准 economy 报价，仅生成校园公众号所需的视频脚本与图文文案两项缺失交付物 |
| 5 / content-writer | generate_script {"quote_id": "4b605d34-ec3d-4ce2-b615-f6d3a6042338", "deliverables": ["video_script", "social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"video_script","result_id":"0425e2a0-66e3-417a-a904-8660c6f3f153"},{"deliverable":"social_copy","result_id":"7249f8f6-fe20-463b-bd35-1f6914a055a1"}],"failures":[]} | save_plan：economy 单渠道报价 8 在预算 10 内、03:05Z 可交付；内容已生成并通过审查 |
| 6 / main | save_plan {"quote_id": "4b605d34-ec3d-4ce2-b615-f6d3a6042338", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-b1caf5ec3ff1766ebd24"} | 运行结果 completed/None |

## C03a-once-failure

最终状态：completed；原因：None；费用：8；预算缺口：0。[输入](review-live/C03a-once-failure/input.json) · [输出](review-live/C03a-once-failure/output.json) · [Trace](review-live/C03a-once-failure/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：优先评估用户偏好的 economy，单选素材覆盖的校园公众号渠道，预算 10 硬约束下先看报价 |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号"]} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：按已批准的 economy 单渠道（校园公众号）报价补齐两项缺失交付物，不涉及渠道改写 |
| 3 / content-writer | generate_script {"quote_id": "f85d4ec8-b7c5-4567-8204-a78b2db2ba0b", "deliverables": ["video_script", "social_copy"]} | {"status":"partial","error_code":"generator_unavailable","missing":["social_copy"],"completed":[{"deliverable":"video_script","result_id":"427ad6e4-cfc2-406e-83b0-b868e408ca5c"}],"failures":[{"deliverable":"social_copy","error_code":"generator_unavailable","retryable":true}]} | estimate_plan：视频脚本已成功，仅需重估缺失的图文文案，避免重复计费 |
| 4 / main | estimate_plan {"backend": "primary", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：仅补缺失的公众号图文文案，视频脚本已成功复用，符合 economy 报价范围 |
| 5 / content-writer | generate_script {"quote_id": "ba43b414-099b-4727-a6f7-9593bbee6ccc", "deliverables": ["social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"social_copy","result_id":"db18223c-9280-4515-8156-5282ee5995df"}],"failures":[]} | save_plan：economy 单渠道报价 8 元、61 分钟均在硬约束内，视频脚本与图文文案已生成并经审查修订 |
| 6 / main | save_plan {"quote_id": "ba43b414-099b-4727-a6f7-9593bbee6ccc", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-c7e02bb1a208a63bcb5f"} | 运行结果 completed/None |

## C03b-primary-unavailable

最终状态：completed；原因：None；费用：8；预算缺口：0。[输入](review-live/C03b-primary-unavailable/input.json) · [输出](review-live/C03b-primary-unavailable/output.json) · [Trace](review-live/C03b-primary-unavailable/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：用户偏好 economy，先按单渠道校园公众号估算 |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号"]} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：economy 报价已批准且可行，仅缺 video_script 与 social_copy，单渠道校园公众号，按报价一次生成缺失项 |
| 3 / content-writer | generate_script {"quote_id": "340a6717-cdeb-4cc7-ab94-c0d64c31ca0d", "deliverables": ["video_script", "social_copy"]} | {"status":"failed","error_code":"generator_unavailable","missing":["video_script","social_copy"],"completed":[],"failures":[{"deliverable":"video_script","error_code":"generator_unavailable","retryable":false}]} | estimate_plan：primary 生成后端不可用且不可重试，改用备用后端并重估 |
| 4 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：新批准 economy 报价仅校园公众号单渠道，primary 后端失败后改用 backup，两项均缺失且无成功项可复用 |
| 5 / content-writer | generate_script {"quote_id": "394c3da3-e5f3-4bfc-9948-fa2692fe13aa", "deliverables": ["video_script", "social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"video_script","result_id":"0ddd22b6-4497-435c-a9f3-6bef1384a84a"},{"deliverable":"social_copy","result_id":"cd65aac1-f394-41ab-90bf-ff8b5b9a88bc"}],"failures":[]} | save_plan：economy 单渠道报价可行，两份交付物已在 backup 后端生成成功并通过审查，按审查建议完善运营字段后保存 |
| 6 / main | save_plan {"quote_id": "394c3da3-e5f3-4bfc-9948-fa2692fe13aa", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-77e043e80a5af30ed15d"} | 运行结果 completed/None |

## C13-required-channel-budget-gap

最终状态：incomplete；原因：budget_infeasible；费用：0；预算缺口：2。[输入](review-live/C13-required-channel-budget-gap/input.json) · [输出](review-live/C13-required-channel-budget-gap/output.json) · [Trace](review-live/C13-required-channel-budget-gap/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：优先评估用户偏好的 economy，同时必须保留两个必需渠道 |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号", "短视频平台"]} | {"status":"succeeded","total_cost":8,"feasible":false,"budget_ok":true,"minimum_budget_gap":2,"deadline_ok":true} | estimate_plan：保留两个必需渠道需升级为 standard，核对报价是否满足预算 10 |
| 3 / main | estimate_plan {"backend": "primary", "channels": ["校园公众号", "短视频平台"], "tier": "standard"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"minimum_budget_gap":2,"deadline_ok":true} | estimate_plan：主后端标准版超预算 2，核对备用后端报价是否满足预算 |
| 4 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号", "短视频平台"], "tier": "standard"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"minimum_budget_gap":2,"deadline_ok":true} | 运行结果 incomplete/budget_infeasible |

## C14-unattempted-steps

最终状态：incomplete；原因：execution_limit；费用：0；预算缺口：0。[输入](review-live/C14-unattempted-steps/input.json) · [输出](review-live/C14-unattempted-steps/output.json) · [Trace](review-live/C14-unattempted-steps/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：用户偏好 economy；单渠道满足 economy 限制，校园公众号可承载图文并配短视频脚本 |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号"]} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：economy 报价已批准，missing 为视频脚本与图文文案，仅生成这两项，渠道限校园公众号 |
| 3 / content-writer | generate_script {"quote_id": "e5b79cf7-9fd0-4c6d-b1df-1299fc6e2752", "deliverables": ["video_script", "social_copy"]} | {"status":"failed","error_code":"generator_unavailable","missing":["video_script","social_copy"],"completed":[],"failures":[{"deliverable":"video_script","error_code":"generator_unavailable","retryable":true}]} | generate_script：上次为 generator_unavailable 暂时性失败且 completed 为空，按已批准 economy 报价重试两项缺失交付物 |
| 4 / content-writer | generate_script {"deliverables": ["video_script", "social_copy"], "quote_id": "e5b79cf7-9fd0-4c6d-b1df-1299fc6e2752"} | {"status":"failed","error_code":"generator_unavailable","missing":["video_script","social_copy"],"completed":[],"failures":[{"deliverable":"video_script","error_code":"generator_unavailable","retryable":true}]} | estimate_plan：主后端持续 generator_unavailable，换备用后端需重新估算；仍保持 economy 单渠道与预算约束 |
| 5 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"minimum_budget_gap":0,"deadline_ok":true} | generate_script：v2 economy 报价可行（8/10，61分钟余量），completed 为空，两项均缺失，一次性补齐 |
| 6 / content-writer | generate_script {"quote_id": "1b9fa9ca-c4c6-4524-a81b-2d5bec1ee405", "deliverables": ["video_script", "social_copy"]} | {"status":"failed","error_code":"generator_unavailable","missing":["video_script","social_copy"],"completed":[],"failures":[{"deliverable":"video_script","error_code":"generator_unavailable","retryable":true}]} | 运行结果 incomplete/execution_limit |

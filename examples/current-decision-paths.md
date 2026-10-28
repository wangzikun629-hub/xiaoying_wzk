# 当前版本真实动态路径

根据最终真实输出整理，只列业务工具。依据为工具参数中的公开reason，不包含隐藏推理。完整委派、规则读取与模型动作见Trace；费用为合成单位。

## C04-budget-replan

最终状态：completed；费用：8。[输入](yaml-live/C04-budget-replan/input.json) · [输出](yaml-live/C04-budget-replan/output.json) · [Trace](yaml-live/C04-budget-replan/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：见完整Trace |
| 2 / main | estimate_plan {"tier": "standard", "channels": ["校园公众号", "短视频平台"], "backend": "primary"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"deadline_ok":true} | estimate_plan：见完整Trace |
| 3 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号", "短视频平台"], "tier": "standard"} | {"status":"succeeded","total_cost":12,"feasible":false,"budget_ok":false,"deadline_ok":true} | estimate_plan：见完整Trace |
| 4 / main | estimate_plan {"backend": "primary", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"deadline_ok":true} | generate_script：见完整Trace |
| 5 / content-writer | generate_script {"quote_id": "d9bf401c-b9a7-4347-af41-3a39f60f9bfc", "deliverables": ["video_script", "social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"video_script","result_id":"3930eb3f-5797-460a-8565-51dc970b769a"},{"deliverable":"social_copy","result_id":"a5e06fe5-126f-41e8-bfb2-b874b36d0d8f"}]} | save_plan：见完整Trace |
| 6 / main | save_plan {"quote_id": "d9bf401c-b9a7-4347-af41-3a39f60f9bfc", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-b1caf5ec3ff1766ebd24"} | 最终状态 completed |

## C03a-once-failure

最终状态：completed；费用：8。[输入](yaml-live/C03a-once-failure/input.json) · [输出](yaml-live/C03a-once-failure/output.json) · [Trace](yaml-live/C03a-once-failure/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：见完整Trace |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号"]} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"deadline_ok":true} | generate_script：见完整Trace |
| 3 / content-writer | generate_script {"quote_id": "cbb97a30-a852-4e61-875c-ef82461adaaf", "deliverables": ["video_script", "social_copy"]} | {"status":"partial","error_code":"generator_unavailable","missing":["social_copy"],"completed":[{"deliverable":"video_script","result_id":"1ee2c2fb-1a81-4707-abdf-4edf994295f4"}]} | estimate_plan：见完整Trace |
| 4 / main | estimate_plan {"backend": "primary", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"deadline_ok":true} | generate_script：见完整Trace |
| 5 / content-writer | generate_script {"quote_id": "a4252f38-b47f-4930-b6a7-7ea84d9a1650", "deliverables": ["social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"social_copy","result_id":"9d156408-9034-44f8-a415-271afd82f3a4"}]} | save_plan：见完整Trace |
| 6 / main | save_plan {"quote_id": "a4252f38-b47f-4930-b6a7-7ea84d9a1650", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-c7e02bb1a208a63bcb5f"} | 最终状态 completed |

## C03b-primary-unavailable

最终状态：completed；费用：8。[输入](yaml-live/C03b-primary-unavailable/input.json) · [输出](yaml-live/C03b-primary-unavailable/output.json) · [Trace](yaml-live/C03b-primary-unavailable/trace.jsonl)

| 步骤 / 执行者 | 动作与参数 | 返回摘要 | 后续动作与公开依据 |
| --- | --- | --- | --- |
| 1 / main | search_materials {"query": "毕业季校园影像征集"} | {"status":"succeeded","material_ids":["campus-01","campus-02"]} | estimate_plan：见完整Trace |
| 2 / main | estimate_plan {"tier": "economy", "backend": "primary", "channels": ["校园公众号"]} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"deadline_ok":true} | generate_script：见完整Trace |
| 3 / content-writer | generate_script {"quote_id": "991483b5-edf2-4288-b1ba-bba97d95a68f", "deliverables": ["video_script", "social_copy"]} | {"status":"failed","error_code":"generator_unavailable","missing":["video_script","social_copy"],"completed":[]} | estimate_plan：见完整Trace |
| 4 / main | estimate_plan {"backend": "backup", "channels": ["校园公众号"], "tier": "economy"} | {"status":"succeeded","total_cost":8,"feasible":true,"budget_ok":true,"deadline_ok":true} | generate_script：见完整Trace |
| 5 / content-writer | generate_script {"quote_id": "8ab20900-e4b8-47b2-8fcd-cf9f74c4c9f5", "deliverables": ["video_script", "social_copy"]} | {"status":"succeeded","missing":[],"completed":[{"deliverable":"video_script","result_id":"98434f7c-579e-42ab-8462-a265f7197537"},{"deliverable":"social_copy","result_id":"88c83678-867f-4b95-a171-61225ead6f15"}]} | save_plan：见完整Trace |
| 6 / main | save_plan {"quote_id": "8ab20900-e4b8-47b2-8fcd-cf9f74c4c9f5", "campaign": "六项运营字段，完整内容见Trace"} | {"status":"succeeded","total_cost":8,"plan_id":"plan-77e043e80a5af30ed15d"} | 最终状态 completed |

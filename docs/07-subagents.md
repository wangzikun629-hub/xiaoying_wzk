# YAML 子智能体配置

当前架构使用一个主Agent和两个可配置子智能体。[config/subagents.yaml](../config/subagents.yaml) 在每次非缓存运行装配Agent时加载，无需额外CLI参数。主Agent根据工具反馈选择委派、重估算、备用方式或停止。

| 角色 | 默认名称 | 工具权限 | 职责 |
| --- | --- | --- | --- |
| 主Agent | main | 检索、估算、保存、受控task；规则读取与TODO | 预算与截止时间判断、重规划、汇总与正式保存 |
| writer | content-writer | generate_script | 按当前可行报价生成缺失项；失败或部分成功后交回主Agent |
| reviewer | plan-reviewer | 无 | 审查已生成内容的主题、引用、渠道表达及完整性，返回建议 |

配置示例：

```yaml
subagents:
  - name: content-writer
    role: writer
    enabled: true
    description: 生成已批准报价中的缺失内容
    tools: [generate_script]
    system_prompt: |
      只生成缺失项，保留成功结果。
      失败后交回主Agent，不自行修改报价或保存。
```

`name` 是主Agent通过task调用时使用的标识，可修改为小写字母、数字和连字符组成的名称，以字母开头，最长64字符。`role` 为writer或reviewer，用于权限及离线策略；每种角色至多启用一个，名称不能重复。`enabled` 默认为true。`description` 描述何时委派，`system_prompt` 为子智能体指令。writer工具必须为`[generate_script]`，reviewer必须为`[]`；未知字段、工具和角色会被拒绝。配置经安全YAML解析与严格结构校验，不支持在配置中执行Python或定义任意导入。

把某项设为`enabled: false`可停用。writer停用后主Agent恢复直接生成；reviewer停用后不要求执行审查；两者均停用或`subagents: []`恢复单Agent流程。只有YAML启用名单可以被委派，框架默认通用子智能体也不能绕过名单。配置错误返回`incomplete / invalid_subagent_config`，在模型或工具调用前停止。

`task`的`subagent_type`必须使用完整配置名称，例如`content-writer`或`plan-reviewer`；`writer`和`reviewer`只是角色标签。传入未知名称时，工具返回`subagent_not_allowed`及`allowed_subagents`名称到角色的映射，供模型自行修正下一次调用；宿主不会把错误名称静默改成其他智能体。改名配置同样通过该反馈列出实际可用名称。

两个子智能体继承当前运行的模型连接，使用同一套OPENAI_API_KEY、OPENAI_BASE_URL及OPENAI_MODEL环境配置。当前YAML不提供模型覆盖或密钥字段。mock使用确定性父子策略；live使用真实模型父子循环。宿主在每次子模型请求中补充authoritative_context，包含实际请求、报价、素材、成功结果和缺失项，避免只依赖主模型转述状态。

主Agent和所有子智能体共用默认20次模型、32次工具调用上限；task本身也算一次工具调用，内部脚本生成请求也算模型调用。新增审查不额外收费或增加模拟分钟数，因为当前模拟费用表仅对内容交付物计价；真实API请求会增加token消耗，实际墙钟等待仍影响真实截止时间校验。不是将审查API调用视作免费外部服务。

启用writer时主Agent不能直接调用generate_script。writer选定一次生成动作后，框架通过该工具的return_direct=True直接结束子图，将实际观察交回主Agent，不再请求子模型继续重试或总结。writer的成功、部分成功和失败状态由实际工具记录决定，模型自然语言不能覆盖。已成功内容在SQLite中保留，主Agent重新估算后再次委派只补缺失项。writer没有估算或保存权限；reviewer没有任何工具，也不能继续委派。启用reviewer时保存前检查当前计划与内容已执行成功审查；审查的成功只表示获得建议，不代表事实正确或正式完成。保存工具继续校验依赖、费用、素材和截止时间。

输出JSON增加subagent_runs，每次记录名称、角色、所属run_id、状态及返回摘要。Trace增加subagent_start/subagent_result，模型和业务工具记录agent归属；模型用途区分decision与subagent:名称。运行元数据的源码摘要包含YAML，并记录启用配置摘要。中断后续跑会把未结束委派标为失败，保留其已提交的业务结果；正式完成的相同请求仍返回缓存，修改配置后需新请求ID或新数据库才能重新执行。

离线验证：

```powershell
uv run pytest -q
uv run python scripts/run_examples.py --mode mock --output outputs/review-yaml-mock
```

当前证据见[离线汇总](../examples/final-mock/summary.json)和[真实模型汇总](../examples/final-live/summary.json)。C04-budget-replan 的 subagent_runs 和 Trace 记录了主 Agent 的12→8重估算、创作委派和审查委派；C03a 记录了部分成功后的补生成，视频 result_id 保留、累计费用为8。真实模型的具体动作见[动态路径](../examples/final-decision-paths.md)。此前版本保留在历史目录中，不计入当前结果。

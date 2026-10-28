---
name: campaign-planning
description: Plan content campaigns within a budget and deadline, adapt to tool failures and partial results, and save a verified campaign.
---

活动方案包含目标、受众、核心信息、渠道、视频脚本、图文文案、角色与相对排期、建议指标、费用及素材引用。
先检查主题素材；当前样例最低交付为视频脚本和图文文案。标准版增加多渠道改写。
estimate_plan 接收 tier、backend、channels、reason，负责形成可核对的步骤及报价。
只有可行报价可生成。遇到超预算、时间不足、素材不足，基于观察选择调整或停止，不预设所有输入相同路径。
generate_script 部分成功时，读取 completed/missing；只生成 missing，成功项不得重新计费。
备用后端是明确标记的模板降级方案；不能冒充模型生成。
save_plan 接收运营方案字段，实际脚本、金额、依赖和完成状态由执行层核验。

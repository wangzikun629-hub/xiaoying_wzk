# 来源、复用与版本

参考：[langchain-ai/deepagents / Content Builder Agent](https://github.com/langchain-ai/deepagents/tree/main/examples/content-builder-agent)。借鉴其通过create_deep_agent组织规则、Skills、工具和消息处理的方式。当前业务代码重新编写，没有将上游应用源文件复制进src；上游研究子Agent、图像生成、网络搜索与品牌内容未直接移植。

来源commit与文件摘要由`scripts/capture_upstream.py`记录在`upstream-source.json`，下载时只读查询GitHub，不执行上游代码。若网络导致记录未完成，不能编造SHA。上游MIT许可证在`upstream-LICENSE.txt`保留；本项目不将开源框架功能列为候选人个人实现。

首次准确SHA获取遇到匿名API限流403及只读Git查询超时；后续通过GitHub连接器读取main及指定提交文件，已核实参考提交为`4ff926659cfb1281b01d6821052135cef151dde3`，5个参考文件的Git blob摘要保存在`upstream-source.json`。框架安装版本另由锁文件固定，不将示例提交与PyPI包版本混为一谈。许可证正文从官方LICENSE核对保留。

运行版本以`uv.lock`与每次run-metadata.json为准。当前安装：Deep Agents0.7.32负责工具循环、虚拟文件后端与规则/Skills；LangChain1.4.7负责模型/工具消息和中间件；LangGraph1.2.18负责图执行；langchain-openai1.7.3接入兼容Chat Completions。

本项目实现：确定性费用时间规则、报价有效性、最小交付约束、交付物级成功保留、SQLite事务与幂等、失败续跑、调用上限与脱敏Trace、验收脚本及材料。离线Mock策略亦为本项目测试代码，不是上游或真实模型能力。

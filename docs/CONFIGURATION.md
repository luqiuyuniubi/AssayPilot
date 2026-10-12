# 模型配置与数据流

默认本地模式：解析、质控、拟合和导出不调用外部模型。

推荐在页面模型设置中填服务、地址、模型与 Key，先测试连接和工具往返。仅会话配置保留在进程内存；勾选记住时 Key 使用 Windows DPAPI 加密保存在 `pharma_agent/.local/`。

也可在启动前设置环境变量。以下示例没有真实密钥：

```powershell
$env:PHARMA_LLM_BASE_URL = "https://你的兼容服务地址/v1"
$env:PHARMA_LLM_MODEL = "你的账户可用模型"
$env:PHARMA_LLM_API_KEY = "在本机填写"
.\.venv\Scripts\python.exe pharma_agent\launch.py
```

环境变量模式按自定义兼容接口处理；OpenAI 原生 Responses 等供应商专用适配应在页面选择对应供应商。API账户与聊天订阅不必然共享额度。

可选搜索环境变量：`PHARMA_SEARCH_PROVIDER`（public/tavily/brave）、`PHARMA_SEARCH_API_KEY`。搜索密钥独立于模型密钥。

`PHARMA_PORT` 可指定本地端口，例如 8875。访问令牌每次启动随机生成，由启动器经 URL fragment 交给页面，页面移除 fragment 后用请求头访问 API。不要复制带令牌的网址到截图或仓库。

实验模型路径发送结构化分析结果、必要记录文本和问题，不发送CSV/XLSX二进制附件；工具可返回原始孔RLU。通用路径不自动附加实验结果，但用户主动输入和历史通用对话仍可能发送给所选服务。

公网网页工具只读，密钥不进入模型上下文。网页和搜索摘要是不可信外部内容，工具返回后限制追加调用。需要进一步阅读时由用户明确发起下一次请求。

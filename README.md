# LLM 请求记录工具

这个工具用于在本机拦截并记录 `codex`、`claude code`、`glm`、`gpt` 等 CLI/脚本发出的 HTTP/HTTPS 接口请求。

它不是直接读取“聊天历史数据库”，而是从网络层记录：

- 请求地址
- 请求头
- 请求体
- 响应状态码
- 响应头
- 响应体

## 适用场景

适合这些情况：

- 你本地运行的是命令行工具或脚本
- 这些工具走标准 HTTP/HTTPS 请求
- 这些工具支持读取 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`

不适合这些情况：

- 工具把对话只保存在本地数据库，但不发网络请求
- 客户端使用证书锁定（certificate pinning）
- 桌面应用完全不走系统代理

## 目录

- `capture_llm_requests.py`
  负责启动 `mitmproxy` 代理并通过代理运行目标命令
- `llm_proxy_logger.py`
  `mitmproxy` 插件，负责将请求/响应写入 `logs/records.jsonl`
- `requirements.txt`
  依赖列表

## 安装

建议先创建独立虚拟环境，避免影响你当前 Python 依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

再安装依赖：

```powershell
pip install -r requirements.txt
```

说明：

- `mitmproxy` 依赖对 `h11`、`bcrypt` 等包版本比较敏感
- 如果你直接装到全局 Python，可能影响其他项目
- 当前 `requirements.txt` 已额外固定 `bcrypt<4.1`，用于兼容 `mitmproxy 11`

## 查看代理地址

如果你只想拿到代理地址，手动配置给其他程序：

```powershell
python .\capture_llm_requests.py --print-proxy-only
```

## 直接包装命令运行

### 1. 包装 `codex`

```powershell
python .\capture_llm_requests.py -- codex
```

### 2. 包装 `claude`

```powershell
python .\capture_llm_requests.py -- claude
```

默认情况下，代理运行日志不会打印到当前终端，避免污染 `claude` 对话界面；日志会写到：

```text
.\logs\proxy-runtime.log
```

如果你需要排查代理本身，可以显式打开：

```powershell
python .\capture_llm_requests.py --verbose-proxy -- claude
```

如果 `claude` 实际走的是第三方 Anthropic 兼容网关，例如 `GLM/open.bigmodel.cn`，推荐这样传：

```powershell
$env:ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
$env:ANTHROPIC_API_KEY="你的 key"
python .\capture_llm_requests.py -- claude
```

也可以直接使用命令行参数：

```powershell
python .\capture_llm_requests.py --anthropic-base-url "https://open.bigmodel.cn/api/anthropic" --anthropic-api-key "你的 key" -- claude
```

如果你需要保留 `claude` 的完整能力，例如：

- `/skills`
- `CLAUDE.md` 自动发现
- 更完整的 slash 命令/插件能力

现在这是默认行为，直接这样启动即可：

```powershell
python .\capture_llm_requests.py --anthropic-base-url "https://open.bigmodel.cn/api/anthropic" --anthropic-api-key "你的 key" -- claude
```

说明：

- 启动器会自动把这两个变量传给 `claude`
- 检测到第三方 Anthropic 网关时，默认保留完整模式，因此 `/skills`、`CLAUDE.md` 自动发现等能力可正常使用
- 默认仍会设置 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
- 如果你只想要更精简的抓取模式，可以显式加 `--claude-bare-mode`

精简模式示例：

```powershell
python .\capture_llm_requests.py --claude-bare-mode --anthropic-base-url "https://open.bigmodel.cn/api/anthropic" --anthropic-api-key "你的 key" -- claude
```

### 3. 包装 Python 脚本

```powershell
python .\capture_llm_requests.py -- python .\demo.py
```

## 指定只抓某些域名

默认已内置常见域名：

- `api.openai.com`
- `api.anthropic.com`
- `open.bigmodel.cn`
- `api.bigmodel.cn`
- `openrouter.ai`
- `generativelanguage.googleapis.com`
- `api.mistral.ai`
- `api.deepseek.com`
- `dashscope.aliyuncs.com`

如果你要自定义：

```powershell
python .\capture_llm_requests.py --hosts "api.openai.com,api.anthropic.com" -- codex
```

## 输出格式

记录文件默认在：

```text
.\logs\records.jsonl
```

每一行是一条完整记录，包含：

- `request.method`
- `request.pretty_url`
- `request.headers`
- `request.body_text`
- `response.status_code`
- `response.headers`
- `response.body_text`

二进制内容会写到 `body_base64` 字段。

## HTTPS 证书

很多大模型接口走 HTTPS。要看到明文请求/响应，你需要信任 `mitmproxy` 证书。

首次运行后，证书通常在：

```text
%USERPROFILE%\.mitmproxy
```

常见文件：

- `mitmproxy-ca-cert.cer`
- `mitmproxy-ca-cert.pem`

在 Windows 中可双击 `mitmproxy-ca-cert.cer`，安装到“受信任的根证书颁发机构”。

如果不安装证书，很多 HTTPS 请求会失败，或者只能看到连接失败记录。

## 查看结果

PowerShell 示例：

```powershell
Get-Content .\logs\records.jsonl -Encoding UTF8
```

筛选 OpenAI 请求：

```powershell
Get-Content .\logs\records.jsonl -Encoding UTF8 | Select-String "api.openai.com"
```

## 前端可视化页面

项目已包含一个本地日志查看页面：

- 服务端: `serve_viewer.py`
- 页面: `viewer/index.html`

启动：

```powershell
python .\serve_viewer.py
```

然后打开：

```text
http://127.0.0.1:8765
```

页面特性：

- 直接读取 `logs/records.jsonl`
- 按 `host`、`status_code`、关键字筛选
- 展示请求头、请求体、响应头、响应体
- 自动兼容 JSON 文本和 Base64 响应体

如果你日志文件不在默认位置，可以在页面左上角直接修改路径，例如：

```text
logs/records.jsonl
logs/claude.jsonl
```

## 重要说明

1. 这个工具抓的是“接口请求记录”，不是现成 App 的“本地聊天历史导出器”。
2. 如果你要抓桌面应用，需要先确认该应用是否会读取系统代理。
3. 某些官方客户端可能有额外校验，无法被常规 MITM 代理解密。

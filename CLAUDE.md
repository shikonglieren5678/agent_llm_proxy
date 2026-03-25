# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLM Request Logger - A tool for intercepting and recording HTTP/HTTPS requests from LLM CLI tools (codex, claude code, glm, gpt, etc.) via mitmproxy.

## Common Commands

```powershell
# Setup (recommended: use virtual environment)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run with target command
python .\capture_llm_requests.py -- claude
python .\capture_llm_requests.py -- codex
python .\capture_llm_requests.py -- python .\demo.py

# Get proxy address only (for manual configuration)
python .\capture_llm_requests.py --print-proxy-only

# Start web viewer
python .\serve_viewer.py
# Opens at http://127.0.0.1:8765
```

## Architecture

**Two-component proxy system:**

1. `capture_llm_requests.py` - Entry point launcher
   - Starts mitmproxy subprocess with `llm_proxy_logger.py` as addon
   - Auto-selects available port if default (8080) is occupied
   - Injects proxy environment variables (HTTP_PROXY, HTTPS_PROXY) into child process
   - Handles certificate env vars for TLS interception (NODE_EXTRA_CA_CERTS, SSL_CERT_FILE, etc.)
   - Special handling for `claude` command with third-party Anthropic-compatible gateways (injects `--bare`, sets CLAUDE_CODE_SIMPLE=1)

2. `llm_proxy_logger.py` - mitmproxy addon
   - Filters requests by host whitelist (configurable via `LLM_PROXY_HOSTS` env var)
   - Captures request/response headers, body (text or base64), timestamps
   - Writes to `logs/records.jsonl` in JSONL format
   - Handles flow errors and incomplete requests

**Web viewer:** `serve_viewer.py` serves static files from `viewer/` and provides `/api/logs` endpoint to read JSONL records.

## Environment Variables

- `LLM_PROXY_OUTPUT_DIR` - Output directory (default: `logs`)
- `LLM_PROXY_HOSTS` - Comma-separated host whitelist (default: built-in LLM API domains)
- `LLM_PROXY_MAX_BODY_BYTES` - Max body size to capture (default: 1MB)

## HTTPS Certificate

First-time HTTPS capture requires trusting mitmproxy CA certificate at `%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer` (Windows: install to "Trusted Root Certification Authorities").

## Output Format

Records are written to `logs/records.jsonl`, each line containing:
- `id`, `captured_at`, `server_conn_ip`
- `request`: method, host, path, pretty_url, headers, body_text/body_base64
- `response`: status_code, headers, body_text/body_base64
- `error` (if request failed)

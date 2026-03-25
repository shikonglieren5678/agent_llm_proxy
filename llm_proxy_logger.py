import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mitmproxy import ctx, http


DEFAULT_HOSTS = [
    "api.openai.com",
    "chat.openai.com",
    "api.anthropic.com",
    "claude.ai",
    "open.bigmodel.cn",
    "api.bigmodel.cn",
    "openrouter.ai",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_bytes(data: bytes | None, content_type: str) -> str | None:
    if not data:
        return None
    if any(
        token in content_type.lower()
        for token in ("json", "text", "xml", "javascript", "x-www-form-urlencoded", "html")
    ):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")
    return None


def _encode_base64(data: bytes | None) -> str | None:
    if not data:
        return None
    return base64.b64encode(data).decode("ascii")


class LLMProxyLogger:
    def __init__(self) -> None:
        self.output_dir = Path(os.getenv("LLM_PROXY_OUTPUT_DIR", "logs")).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_file = self.output_dir / os.getenv("LLM_PROXY_OUTPUT_FILE", "records.jsonl")
        self.max_body_bytes = int(os.getenv("LLM_PROXY_MAX_BODY_BYTES", str(1024 * 1024)))
        raw_hosts = os.getenv("LLM_PROXY_HOSTS", ",".join(DEFAULT_HOSTS))
        self.host_filters = {item.strip().lower() for item in raw_hosts.split(",") if item.strip()}
        self._flows: dict[str, dict[str, Any]] = {}

    def load(self, loader) -> None:
        ctx.log.info(f"LLM proxy logger output: {self.output_file}")
        if self.host_filters:
            ctx.log.info(f"LLM proxy host filters: {', '.join(sorted(self.host_filters))}")
        else:
            ctx.log.info("LLM proxy host filters: <all hosts>")

    def request(self, flow: http.HTTPFlow) -> None:
        host = (flow.request.pretty_host or flow.request.host or "").lower()
        if self.host_filters and host not in self.host_filters:
            return

        record_id = str(uuid.uuid4())
        flow.metadata["record_id"] = record_id
        content = flow.request.raw_content or b""
        truncated = len(content) > self.max_body_bytes
        if truncated:
            content = content[: self.max_body_bytes]

        request_headers = dict(flow.request.headers.items(multi=True))
        request_text = _decode_bytes(content, request_headers.get("content-type", ""))

        self._flows[record_id] = {
            "id": record_id,
            "captured_at": _utc_now(),
            "server_conn_ip": (
                str(getattr(flow.server_conn, "ip_address", None))
                if getattr(flow.server_conn, "ip_address", None)
                else None
            ),
            "request": {
                "method": flow.request.method,
                "scheme": flow.request.scheme,
                "host": flow.request.host,
                "port": flow.request.port,
                "path": flow.request.path,
                "pretty_url": flow.request.pretty_url,
                "headers": request_headers,
                "query": list(flow.request.query.items(multi=True)),
                "http_version": flow.request.http_version,
                "body_text": request_text,
                "body_base64": None if request_text is not None else _encode_base64(content),
                "body_size": len(flow.request.raw_content or b""),
                "body_truncated": truncated,
            },
        }

    def response(self, flow: http.HTTPFlow) -> None:
        record_id = flow.metadata.get("record_id")
        if not record_id or record_id not in self._flows:
            return

        content = flow.response.raw_content or b""
        truncated = len(content) > self.max_body_bytes
        if truncated:
            content = content[: self.max_body_bytes]

        response_headers = dict(flow.response.headers.items(multi=True))
        response_text = _decode_bytes(content, response_headers.get("content-type", ""))

        record = self._flows.pop(record_id)
        record["response"] = {
            "status_code": flow.response.status_code,
            "reason": flow.response.reason,
            "headers": response_headers,
            "http_version": flow.response.http_version,
            "body_text": response_text,
            "body_base64": None if response_text is not None else _encode_base64(content),
            "body_size": len(flow.response.raw_content or b""),
            "body_truncated": truncated,
        }
        self._write_record(record)

    def error(self, flow: http.HTTPFlow) -> None:
        record_id = flow.metadata.get("record_id")
        if not record_id or record_id not in self._flows:
            return

        record = self._flows.pop(record_id)
        record["error"] = str(flow.error)
        self._write_record(record)

    def done(self) -> None:
        for record in list(self._flows.values()):
            record["error"] = "flow closed before response"
            self._write_record(record)
        self._flows.clear()

    def _write_record(self, record: dict[str, Any]) -> None:
        with self.output_file.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")


addons = [LLMProxyLogger()]

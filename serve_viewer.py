import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
VIEWER_DIR = ROOT / "viewer"
DEFAULT_LOG = ROOT / "logs" / "records.jsonl"
LOGS_DIR = ROOT / "logs"


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                records.append(
                    {
                        "id": f"invalid-{line_number}",
                        "captured_at": None,
                        "error": f"JSON 解析失败: 第 {line_number} 行, {exc}",
                        "raw_line": line,
                    }
                )
    return records


def list_log_files() -> list[str]:
    if not LOGS_DIR.exists():
        return []
    files = [path.relative_to(ROOT).as_posix() for path in LOGS_DIR.glob("*.jsonl") if path.is_file()]
    return sorted(files)


class ViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/files":
            self.handle_files()
            return
        if parsed.path == "/api/logs":
            self.handle_logs(parsed)
            return
        self.handle_static(parsed.path)

    def handle_files(self) -> None:
        files = list_log_files()
        default_file = DEFAULT_LOG.relative_to(ROOT).as_posix()
        self.send_json(
            {
                "files": files,
                "default_file": default_file,
            }
        )

    def handle_logs(self, parsed) -> None:
        params = parse_qs(parsed.query)
        requested = params.get("file", [])
        default_file = DEFAULT_LOG.relative_to(ROOT).as_posix()
        selected = default_file if not requested else requested[0]
        log_path = (ROOT / selected).resolve()

        try:
            log_path.relative_to(ROOT)
        except ValueError:
            self.send_json({"error": "非法路径"}, status=400)
            return

        records = load_jsonl(log_path)
        self.send_json(
            {
                "selected_file": selected,
                "file": str(log_path),
                "count": len(records),
                "records": records,
            }
        )

    def handle_static(self, path: str) -> None:
        relative = "index.html" if path in {"/", ""} else path.lstrip("/")
        target = (VIEWER_DIR / relative).resolve()

        try:
            target.relative_to(VIEWER_DIR)
        except ValueError:
            self.send_error(404)
            return

        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        content_type, _ = mimetypes.guess_type(target.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.end_headers()
        self.wfile.write(target.read_bytes())

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="启动日志可视化页面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"Viewer running at http://{args.host}:{args.port}")
    print(f"Default log file: {DEFAULT_LOG}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

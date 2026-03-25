import argparse
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse


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


class ResolvedCommand(NamedTuple):
    command: list[str]
    resolved_entry: str


def merge_host_filters(*host_sets: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for host_set in host_sets:
        for item in host_set:
            host = item.strip().lower()
            if not host or host in seen:
                continue
            seen.add(host)
            merged.append(host)
    return merged


def parse_hosts_csv(raw_hosts: str) -> list[str]:
    return [item.strip() for item in raw_hosts.split(",") if item.strip()]


def extract_host_from_url(raw_url: str) -> str | None:
    if not raw_url:
        return None
    candidate = raw_url.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    return parsed.hostname.lower() if parsed.hostname else None


def collect_runtime_hosts(env: dict[str, str], args: argparse.Namespace) -> list[str]:
    dynamic_hosts: list[str] = []
    for value in (
        args.anthropic_base_url,
        env.get("OPENAI_BASE_URL", ""),
        env.get("OPENAI_API_BASE", ""),
        env.get("ANTHROPIC_BASE_URL", ""),
    ):
        host = extract_host_from_url(value)
        if host:
            dynamic_hosts.append(host)
    return dynamic_hosts


def choose_output_file(command: list[str]) -> str:
    if not command:
        return "records.jsonl"
    executable_name = Path(command[0]).stem.lower()
    if "codex" in executable_name:
        return "codex-records.jsonl"
    if "claude" in executable_name:
        return "claude-records.jsonl"
    return "records.jsonl"


def build_cert_env() -> dict[str, str]:
    cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    if not cert_path.exists():
        return {}
    cert = str(cert_path)
    return {
        "NODE_EXTRA_CA_CERTS": cert,
        "SSL_CERT_FILE": cert,
        "REQUESTS_CA_BUNDLE": cert,
        "CURL_CA_BUNDLE": cert,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动本地代理并记录大模型接口请求，然后通过该代理运行目标命令。"
    )
    parser.add_argument("--listen-host", default="127.0.0.1", help="代理监听地址，默认 127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8080, help="代理监听端口，默认 8080")
    parser.add_argument("--output-dir", default="logs", help="记录输出目录，默认 logs")
    parser.add_argument(
        "--hosts",
        default="",
        help="逗号分隔的 host 白名单；为空时使用内置常见大模型域名集合",
    )
    parser.add_argument(
        "--max-body-bytes",
        type=int,
        default=1024 * 1024,
        help="请求和响应最多保留多少字节，默认 1MB",
    )
    parser.add_argument(
        "--print-proxy-only",
        action="store_true",
        help="只输出代理环境变量，不启动目标命令",
    )
    parser.add_argument(
        "--anthropic-base-url",
        default=os.getenv("ANTHROPIC_BASE_URL", ""),
        help="Claude/Anthropic 兼容接口的 Base URL，例如 https://open.bigmodel.cn/api/anthropic",
    )
    parser.add_argument(
        "--anthropic-api-key",
        default=os.getenv("ANTHROPIC_API_KEY", ""),
        help="Claude/Anthropic 兼容接口的 API Key；建议通过环境变量传入，避免写进命令历史",
    )
    parser.add_argument(
        "--verbose-proxy",
        action="store_true",
        help="在当前终端显示 mitmproxy 运行日志；默认静默并写入 logs/proxy-runtime.log",
    )
    parser.add_argument(
        "--claude-full-mode",
        action="store_true",
        help="Claude 保留完整模式。该行为现已是默认值，保留此参数仅为兼容旧命令",
    )
    parser.add_argument(
        "--claude-bare-mode",
        action="store_true",
        help="Claude 使用精简模式，自动附加 --bare / CLAUDE_CODE_SIMPLE；适合只关心接口抓取的场景",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="要通过代理运行的命令。示例：python capture_llm_requests.py -- codex",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    mitmdump = shutil.which("mitmdump")
    if not mitmdump:
        print("未找到 mitmdump，请先执行: pip install -r requirements.txt", file=sys.stderr)
        return 2

    script_path = Path(__file__).with_name("llm_proxy_logger.py")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    proxy_runtime_log = output_dir / "proxy-runtime.log"

    env = os.environ.copy()
    env["LLM_PROXY_OUTPUT_DIR"] = str(output_dir)
    env["LLM_PROXY_MAX_BODY_BYTES"] = str(args.max_body_bytes)
    env.update(build_cert_env())

    listen_port = choose_listen_port(args.listen_host, args.listen_port)
    proxy_url = f"http://{args.listen_host}:{listen_port}"
    if args.print_proxy_only:
        print(f"HTTP_PROXY={proxy_url}")
        print(f"HTTPS_PROXY={proxy_url}")
        print("NO_PROXY=localhost,127.0.0.1")
        print(f"日志目录: {output_dir}")
        return 0

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("缺少目标命令。示例: python capture_llm_requests.py -- codex")

    resolved = resolve_command(command)
    command = resolved.command
    merged_hosts = merge_host_filters(
        DEFAULT_HOSTS,
        parse_hosts_csv(args.hosts),
        collect_runtime_hosts(env, args),
    )
    env["LLM_PROXY_HOSTS"] = ",".join(merged_hosts)
    env["LLM_PROXY_OUTPUT_FILE"] = choose_output_file(command)

    mitm_args = [
        mitmdump,
        "--listen-host",
        args.listen_host,
        "--listen-port",
        str(listen_port),
        "-s",
        str(script_path),
        "--set",
        "block_global=false",
    ]

    print(f"启动代理: {proxy_url}")
    print(f"日志文件: {output_dir / env['LLM_PROXY_OUTPUT_FILE']}")
    if listen_port != args.listen_port:
        print(f"提示: 端口 {args.listen_port} 已占用，已自动切换到 {listen_port}")
    if args.hosts:
        print(f"附加白名单: {args.hosts}")

    proxy_stdout = None
    proxy_stderr = None
    proxy_log_fp = None
    if not args.verbose_proxy:
        proxy_log_fp = proxy_runtime_log.open("a", encoding="utf-8")
        proxy_stdout = proxy_log_fp
        proxy_stderr = subprocess.STDOUT
        print(f"代理运行日志: {proxy_runtime_log}")

    proxy_process = subprocess.Popen(
        mitm_args,
        env=env,
        stdout=proxy_stdout,
        stderr=proxy_stderr,
    )

    try:
        time.sleep(2)
        if proxy_process.poll() is not None:
            print("代理启动失败，请检查运行日志。", file=sys.stderr)
            if not args.verbose_proxy:
                print(f"查看文件: {proxy_runtime_log}", file=sys.stderr)
            return proxy_process.returncode or 1

        child_env = env.copy()
        child_env["HTTP_PROXY"] = proxy_url
        child_env["HTTPS_PROXY"] = proxy_url
        child_env["NO_PROXY"] = "localhost,127.0.0.1"
        child_env.update(build_cert_env())
        if should_disable_node_tls_verify(resolved.resolved_entry):
            child_env.setdefault("NODE_TLS_REJECT_UNAUTHORIZED", "0")
        command, provider_mode = apply_provider_overrides(command, child_env, args)

        print(f"运行命令: {format_command(command)}")
        print("首次抓 HTTPS 时，需要信任 mitmproxy 证书，位置通常在 %USERPROFILE%\\.mitmproxy")
        if child_env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0":
            print("提示: 已为 Node 类客户端临时关闭 TLS 证书校验，便于代理抓取 HTTPS 明文。")
        if provider_mode == "anthropic_compatible":
            print("提示: 已为 Claude 注入第三方 Anthropic 兼容网关配置，并禁用非必要官方流量。")
        if provider_mode == "anthropic_compatible_full":
            print("提示: 已为 Claude 注入第三方 Anthropic 兼容网关配置，并保留完整模式。")
        result = subprocess.run(command, env=child_env)
        return result.returncode
    finally:
        proxy_process.terminate()
        try:
            proxy_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proxy_process.kill()
            proxy_process.wait(timeout=5)
        if proxy_log_fp:
            proxy_log_fp.close()

def resolve_command(command: list[str]) -> ResolvedCommand:
    executable = command[0]
    resolved = shutil.which(executable)
    if not resolved:
        raise FileNotFoundError(f"找不到命令: {executable}")

    suffix = Path(resolved).suffix.lower()
    if suffix == ".ps1":
        return ResolvedCommand(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                resolved,
                *command[1:],
            ],
            resolved,
        )
    if suffix in {".cmd", ".bat"}:
        return ResolvedCommand([resolved, *command[1:]], resolved)
    return ResolvedCommand([resolved, *command[1:]], resolved)


def should_disable_node_tls_verify(resolved_entry: str) -> bool:
    path = resolved_entry.lower()
    name = Path(path).name
    return (
        "node_modules" in path
        or "appdata\\roaming\\npm" in path
        or name in {"node.exe", "node", "npm.cmd", "npx.cmd", "pnpm.cmd", "yarn.cmd"}
        or name.endswith(".cmd")
        or name.endswith(".ps1")
    )


def apply_provider_overrides(
    command: list[str], env: dict[str, str], args: argparse.Namespace
) -> tuple[list[str], str | None]:
    if not command:
        return command, None

    executable_name = Path(command[0]).name.lower()
    if "claude" not in executable_name:
        return command, None

    if not args.anthropic_base_url and not args.anthropic_api_key:
        return command, None

    if args.anthropic_base_url:
        env["ANTHROPIC_BASE_URL"] = args.anthropic_base_url.rstrip("/")
    if args.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = args.anthropic_api_key

    env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")

    if args.claude_bare_mode:
        env.setdefault("CLAUDE_CODE_SIMPLE", "1")
    else:
        env.pop("CLAUDE_CODE_SIMPLE", None)

    if args.claude_bare_mode and "--bare" not in command:
        command = insert_global_option(command, "--bare")

    return command, "anthropic_compatible" if args.claude_bare_mode else "anthropic_compatible_full"


def insert_global_option(command: list[str], option: str) -> list[str]:
    if len(command) <= 1:
        return [*command, option]
    return [command[0], option, *command[1:]]


def choose_listen_port(host: str, preferred_port: int) -> int:
    if is_port_available(host, preferred_port):
        return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def format_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


if __name__ == "__main__":
    raise SystemExit(main())

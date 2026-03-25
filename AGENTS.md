# Repository Guidelines

## Project Structure & Module Organization

This repository is a small Python utility for capturing and viewing LLM HTTP/HTTPS traffic.

- `capture_llm_requests.py`: entry point that starts `mitmdump`, configures proxy variables, and launches the target command.
- `llm_proxy_logger.py`: mitmproxy addon that filters hosts and writes request/response data to `logs/records.jsonl`.
- `serve_viewer.py`: lightweight local web server for browsing captured records.
- `viewer/`: static frontend assets (`index.html`, `app.js`, `styles.css`).
- `logs/`: runtime output only; treat JSONL logs and proxy logs as generated files, not source.
- `.venv/`, `__pycache__/`, `.idea/`: local environment artifacts and should stay out of feature changes.

## Build, Test, and Development Commands

Use a local virtual environment before changing dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Common development commands:

```powershell
python .\capture_llm_requests.py --print-proxy-only
python .\capture_llm_requests.py -- codex
python .\serve_viewer.py
```

The first prints proxy settings, the second runs a command through the logger, and the third starts the viewer at `http://127.0.0.1:8765`.

## Coding Style & Naming Conventions

Follow existing Python style:

- 4-space indentation, UTF-8 text files, and standard library first.
- Prefer `Path` over raw string paths when editing Python code.
- Use `snake_case` for functions, variables, and file names.
- Keep modules focused: launcher logic in `capture_llm_requests.py`, logging in `llm_proxy_logger.py`, viewer serving in `serve_viewer.py`.
- Preserve concise Chinese user-facing messages already used in CLI output.

No formatter or linter config is currently committed, so keep changes consistent with the surrounding file style.

## Testing Guidelines

There is no formal test suite yet. Before submitting changes:

- run `python .\capture_llm_requests.py --print-proxy-only` to verify argument parsing;
- run `python .\serve_viewer.py` and load the viewer in a browser;
- if touching logging behavior, inspect `logs/records.jsonl` with a small manual capture.

When adding tests, place them under `tests/` and name files `test_*.py`.

## Commit & Pull Request Guidelines

This workspace snapshot does not include `.git`, so local Git history is unavailable. Use short, imperative commit messages such as `Add host whitelist validation`.

Pull requests should include:

- a brief problem statement and the approach taken;
- commands used for manual verification;
- screenshots when `viewer/` UI behavior changes;
- notes about certificate, proxy, or environment-variable impacts.

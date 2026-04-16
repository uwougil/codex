#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Template

from prl_recent_condmat_downloader import CONDMAT_SECTION, SOURCE_LABELS


ROOT_DIR = Path(__file__).resolve().parent
DOWNLOADER_SCRIPT = ROOT_DIR / "prl_recent_condmat_downloader.py"
HTML_TEMPLATE_PATH = ROOT_DIR / "prl_downloader_webui.html"


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat()


def default_output_dir() -> str:
    return str((Path.home() / "Desktop" / "condmat-downloads").resolve())


def default_user_data_dir() -> str:
    return str((Path(tempfile.gettempdir()) / "prl_scrapling_profile").resolve())


def build_default_config() -> dict[str, Any]:
    return {
        "days": 3,
        "today": "",
        "section": CONDMAT_SECTION,
        "sources": ["aps", "acs"],
        "parallel_sites": True,
        "output_dir": default_output_dir(),
        "user_data_dir": default_user_data_dir(),
        "headless": False,
        "overwrite": False,
        "list_only": False,
        "max_pages": 20,
        "retries": 4,
        "timeout_ms": 120_000,
    }


def ensure_date_string(value: str) -> str:
    if not value:
        return ""
    dt.datetime.strptime(value, "%Y-%m-%d")
    return value


def validate_config(payload: dict[str, Any]) -> dict[str, Any]:
    defaults = build_default_config()
    merged = {**defaults, **(payload or {})}
    raw_sources = merged.get("sources", defaults["sources"])
    if isinstance(raw_sources, str):
        source_list = [part.strip().lower() for part in raw_sources.split(",") if part.strip()]
    else:
        source_list = [str(item).strip().lower() for item in list(raw_sources or []) if str(item).strip()]
    source_list = list(dict.fromkeys(source_list))

    config = {
        "days": int(merged["days"]),
        "today": ensure_date_string(str(merged.get("today", "")).strip()),
        "section": str(merged.get("section", CONDMAT_SECTION)).strip() or CONDMAT_SECTION,
        "sources": source_list,
        "parallel_sites": bool(merged.get("parallel_sites", True)),
        "output_dir": str(Path(str(merged["output_dir"])).expanduser().resolve()),
        "user_data_dir": str(Path(str(merged["user_data_dir"])).expanduser().resolve()),
        "headless": bool(merged.get("headless", False)),
        "overwrite": bool(merged.get("overwrite", False)),
        "list_only": bool(merged.get("list_only", False)),
        "max_pages": int(merged["max_pages"]),
        "retries": int(merged["retries"]),
        "timeout_ms": int(merged["timeout_ms"]),
    }

    if not config["sources"]:
        raise ValueError("至少要选择一个来源站点。")
    invalid_sources = [item for item in config["sources"] if item not in SOURCE_LABELS]
    if invalid_sources:
        raise ValueError(f"不支持的来源站点: {', '.join(invalid_sources)}")

    if config["days"] < 1:
        raise ValueError("最近天数必须大于等于 1。")
    if config["max_pages"] < 1:
        raise ValueError("最大扫描页数必须大于等于 1。")
    if config["retries"] < 1:
        raise ValueError("重试次数必须大于等于 1。")
    if config["timeout_ms"] < 1000:
        raise ValueError("超时时间至少需要 1000 毫秒。")

    Path(config["output_dir"]).mkdir(parents=True, exist_ok=True)
    Path(config["user_data_dir"]).mkdir(parents=True, exist_ok=True)
    return config


def build_command(config: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(DOWNLOADER_SCRIPT),
        "--days",
        str(config["days"]),
        "--output-dir",
        config["output_dir"],
        "--user-data-dir",
        config["user_data_dir"],
        "--section",
        config["section"],
        "--sources",
        ",".join(config["sources"]),
        "--max-pages",
        str(config["max_pages"]),
        "--retries",
        str(config["retries"]),
        "--timeout-ms",
        str(config["timeout_ms"]),
    ]
    if config["today"]:
        command.extend(["--today", config["today"]])
    if config["headless"]:
        command.append("--headless")
    if config["parallel_sites"]:
        command.append("--parallel-sites")
    if config["overwrite"]:
        command.append("--overwrite")
    if config["list_only"]:
        command.append("--list-only")
    return command


def scan_output_dir(path_text: str | None) -> list[dict[str, Any]]:
    if not path_text:
        return []
    output_dir = Path(path_text)
    if not output_dir.exists() or not output_dir.is_dir():
        return []

    files: list[dict[str, Any]] = []
    for file in sorted(output_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file():
            continue
        stat = file.stat()
        files.append(
            {
                "name": file.name,
                "path": str(file),
                "size": stat.st_size,
                "modified_at": dt.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
            }
        )
    return files


@dataclass
class JobState:
    job_id: int
    config: dict[str, Any]
    command: list[str]
    status: str = "running"
    started_at: str = field(default_factory=iso_now)
    ended_at: str | None = None
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    output_dir: str | None = None
    error: str | None = None
    progress: dict[str, Any] | None = None
    stop_requested: bool = False
    pid: int | None = None
    process: subprocess.Popen[str] | None = field(default=None, repr=False, compare=False)

    def append_log(self, line: str) -> None:
        self.logs.append(line)
        if len(self.logs) > 4000:
            self.logs = self.logs[-4000:]

    def ingest_output_line(self, line: str) -> None:
        prefix = "@@PROGRESS "
        if line.startswith(prefix):
            try:
                self.progress = json.loads(line[len(prefix):].strip())
            except json.JSONDecodeError:
                self.append_log(line)
            return
        self.append_log(line)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "returncode": self.returncode,
            "logs": "".join(self.logs),
            "files": self.files,
            "output_dir": self.output_dir or self.config.get("output_dir"),
            "error": self.error,
            "progress": self.progress,
            "pid": self.pid,
            "command": subprocess.list2cmdline(self.command),
            "config": self.config,
        }


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_job: JobState | None = None
        self._next_id = 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._current_job is None:
                return {
                    "job_id": None,
                    "status": "idle",
                    "started_at": None,
                    "ended_at": None,
                    "returncode": None,
                    "logs": "",
                    "files": [],
                    "output_dir": None,
                    "error": None,
                    "progress": None,
                    "pid": None,
                    "command": "",
                    "config": None,
                }
            return self._current_job.to_dict()

    def start_job(self, config: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._current_job and self._current_job.status in {"running", "stopping"}:
                raise RuntimeError("已有任务正在运行，请先等待完成或手动终止。")

            job = JobState(
                job_id=self._next_id,
                config=config,
                command=build_command(config),
                output_dir=config["output_dir"],
            )
            self._next_id += 1
            self._current_job = job

        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()
        return job.to_dict()

    def stop_job(self) -> dict[str, Any]:
        with self._lock:
            if self._current_job is None or self._current_job.status not in {"running", "stopping"}:
                raise RuntimeError("当前没有可终止的任务。")
            job = self._current_job
            job.stop_requested = True
            job.status = "stopping"
            process = job.process

        if process and process.poll() is None:
            threading.Thread(target=self._kill_process_tree, args=(process,), daemon=True).start()
        return job.to_dict()

    def _kill_process_tree(self, process: subprocess.Popen[str]) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _run_job(self, job: JobState) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                job.command,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as error:
            with self._lock:
                job.status = "failed"
                job.error = str(error)
                job.ended_at = iso_now()
                job.append_log(f"启动失败：{error}\n")
            return

        with self._lock:
            job.process = process
            job.pid = process.pid
            job.append_log(f"Started job #{job.job_id}\n")
            job.append_log(f"Command: {subprocess.list2cmdline(job.command)}\n\n")

        assert process.stdout is not None
        for line in process.stdout:
            with self._lock:
                job.ingest_output_line(line)

        process.wait()
        with self._lock:
            job.returncode = process.returncode
            job.ended_at = iso_now()
            job.files = scan_output_dir(job.output_dir)
            if job.stop_requested:
                job.status = "stopped"
            elif process.returncode == 0:
                job.status = "completed"
            else:
                job.status = "failed"
            job.process = None
            job.pid = None


JOB_MANAGER = JobManager()


def render_html() -> bytes:
    template = Template(HTML_TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload = {
        "defaults": build_default_config(),
        "currentDate": dt.date.today().isoformat(),
        "sourceOptions": [{"value": value, "label": label} for value, label in SOURCE_LABELS.items()],
        "pythonExecutable": sys.executable,
        "downloaderScript": str(DOWNLOADER_SCRIPT),
    }
    html = template.render(app_json=json.dumps(payload, ensure_ascii=False))
    return html.encode("utf-8")


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "JournalCondmatDownloaderUI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        length = int(raw_length or "0")
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_html())
            return
        if parsed.path == "/api/state":
            self._send_json(JOB_MANAGER.snapshot())
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/start":
                config = validate_config(payload)
                snapshot = JOB_MANAGER.start_job(config)
                self._send_json(snapshot)
                return
            if parsed.path == "/api/stop":
                snapshot = JOB_MANAGER.stop_job()
                self._send_json(snapshot)
                return
            if parsed.path == "/api/open-folder":
                folder = str(Path(str(payload.get("path", ""))).expanduser().resolve())
                path = Path(folder)
                path.mkdir(parents=True, exist_ok=True)
                if hasattr(os, "startfile"):
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", str(path)])
                self._send_json({"ok": True, "path": str(path)})
                return
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.CONFLICT)
            return
        except Exception as error:  # pragma: no cover - unexpected runtime failures
            self._send_json({"error": str(error)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local web UI for the multi-publisher condensed-matter downloader.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Default: 8765")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the system browser.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"多出版商凝聚态下载面板已启动：{url}", flush=True)
    print("按 Ctrl+C 可以关闭服务。", flush=True)

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭服务…", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

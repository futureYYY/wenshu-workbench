"""自检（07 第 5.4 节）：WenShu.exe --selftest 不打开界面、不显示托盘，检查后退出。

- 使用独立的数据目录 {程序目录}\\data-selftest（启动前清空），端口由系统分配；
- 每项检查在 data-selftest\\logs\\selftest.log 里写一行“PASS / FAIL 项目 原因”；
- 全部通过：删除 data-selftest，退出码 0；有失败：保留目录和日志，退出码 1。
打包流程（scripts\\build.bat）用 start "" /wait 拿到退出码。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import __version__
from app.config import load_config, resolve_app_dir, setup_logging
from app.launcher import localhttp, ports

logger = logging.getLogger(__name__)

SAMPLE_TEXT = "我的快递三天没动了，能帮我查一下吗"
PASTE_TEXT = "我想查一下退款进度\n会员自动续费怎么关\n建议你们增加夜间模式"


class CheckFailed(Exception):
    """某一项检查没有通过，消息是给人看的原因。"""


class _Context:
    def __init__(self, port: int, db_path: Path) -> None:
        self.port = port
        self.db_path = db_path

    def get(self, path: str) -> Any:
        return localhttp.get_json(self.port, path)

    def post(self, path: str, body: Any = None) -> Any:
        return localhttp.post_json(self.port, path, body)

    def demo_model_id(self) -> int:
        data = self.get("/api/models?include_demo=true")
        for item in data.get("items", []):
            if item.get("provider_kind") == "demo":
                return int(item["id"])
        raise CheckFailed("模型列表里没有演示模型")

    def builtin_prompt(self, task_type: str) -> dict[str, Any]:
        data = self.get(f"/api/prompts?task_type={task_type}")
        for item in data.get("items", []):
            if item.get("builtin_key") == f"{task_type}.default":
                return item
        raise CheckFailed(f"没有找到内置提示词 {task_type}.default")


def _check_health(ctx: _Context) -> None:
    data = ctx.get("/api/health")
    if data.get("status") != "ok":
        raise CheckFailed(f"/api/health 返回 {data}")
    if data.get("version") != __version__:
        raise CheckFailed(f"版本号不一致：接口 {data.get('version')}，程序 {__version__}")


def _check_frontend(ctx: _Context) -> None:
    html = localhttp.get_text(ctx.port, "/")
    if '<div id="app">' not in html:
        raise CheckFailed('首页里没有前端挂载点 <div id="app">，前端资源可能没有打包进来')


def _check_database(ctx: _Context) -> None:
    if not ctx.db_path.is_file():
        raise CheckFailed(f"没有找到数据库 {ctx.db_path}")
    uri = ctx.db_path.resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        builtins = conn.execute(
            "SELECT COUNT(*) FROM prompt_templates WHERE builtin_key IN ('classify.default', 'summarize.default')"
        ).fetchone()[0]
        demos = conn.execute("SELECT COUNT(*) FROM model_configs WHERE provider_kind = 'demo'").fetchone()[0]
    if version < 1:
        raise CheckFailed(f"数据库 user_version = {version}，迁移没有执行")
    if builtins != 2:
        raise CheckFailed(f"内置提示词应有 2 套，实际 {builtins} 套")
    if demos < 1:
        raise CheckFailed("数据库里没有演示模型")


def _check_demo_model(ctx: _Context) -> None:
    model_id = ctx.demo_model_id()
    result = ctx.post(f"/api/models/{model_id}/test")
    if not result or result.get("ok") is not True:
        raise CheckFailed(f"演示模型测试连接失败：{(result or {}).get('message')}")


def _check_playground(ctx: _Context) -> None:
    prompt = ctx.builtin_prompt("classify")
    draft = {
        key: prompt.get(key)
        for key in (
            "task_type", "system_prompt", "user_template", "chunk_template", "merge_template",
            "output_mode", "field_map", "temperature", "max_output_tokens",
        )
    }
    body = {"prompt": draft, "model_id": ctx.demo_model_id(), "sample": {"kind": "text", "text": SAMPLE_TEXT}}
    for event, data in localhttp.post_sse(ctx.port, "/api/playground/run", body, timeout=60):
        if event == "error":
            raise CheckFailed(f"试运行返回错误：{data}")
        if event == "done":
            done = json.loads(data)
            parsed = done.get("parsed") or {}
            if not parsed.get("label"):
                raise CheckFailed(f"试运行没有解析出类别：{done.get('parse_error') or data[:200]}")
            return
    raise CheckFailed("试运行的流结束了，但没有收到 done 事件")


def _check_estimate(ctx: _Context) -> None:
    file_info = ctx.post("/api/files/paste", {"text": PASTE_TEXT, "name": "自检样本"})
    body = {
        "task_type": "classify",
        "file_id": file_info["id"],
        "source": {
            "sheet": None,
            "header_row": 0,
            "text_columns": ["text"],
            "join_mode": "labeled",
            "start_row": None,
            "limit": None,
            "split_mode": "line",
        },
        "prompt_id": ctx.builtin_prompt("classify")["id"],
        "model_id": ctx.demo_model_id(),
        "concurrency": 5,
    }
    estimate = ctx.post("/api/jobs/estimate", body)
    if estimate.get("item_count") != 3:
        raise CheckFailed(f"预估条数应为 3，实际 {estimate.get('item_count')}")


CHECKS: list[tuple[str, Callable[[_Context], None]]] = [
    ("health", _check_health),
    ("frontend", _check_frontend),
    ("database", _check_database),
    ("demo-model", _check_demo_model),
    ("playground", _check_playground),
    ("estimate", _check_estimate),
]


def _reset_dir(path: Path) -> None:
    for attempt in range(5):
        try:
            if path.exists():
                shutil.rmtree(path)
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.5)
    path.mkdir(parents=True, exist_ok=True)


def _close_log_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_wenshu", False):
            root.removeHandler(handler)
            handler.close()


def _remove_dir(path: Path) -> bool:
    for _ in range(10):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(0.5)  # SQLite 的 -wal、-shm 文件可能还没释放
    return False


def _write_report(log_dir: Path, lines: list[str]) -> None:
    for line in lines:
        logger.info(line)
    with contextlib.suppress(OSError):
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "selftest.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_checks(port: int, ready: bool, db_path: Path) -> list[tuple[bool, str, str]]:
    results: list[tuple[bool, str, str]] = []
    ctx = _Context(port, db_path)
    for name, check in CHECKS:
        if not ready:
            reason = "后端 15 秒内没有就绪，详见 logs\\app.log" if name == "health" else "后端没有启动"
            results.append((False, name, reason))
            continue
        try:
            check(ctx)
        except CheckFailed as exc:
            results.append((False, name, str(exc)))
        except localhttp.ERRORS as exc:
            results.append((False, name, f"请求失败：{exc}"))
        except Exception as exc:
            logger.exception("自检项 %s 出现异常", name)
            results.append((False, name, f"{type(exc).__name__}：{exc}"))
        else:
            results.append((True, name, ""))
    return results


def run_selftest() -> int:
    data_dir = resolve_app_dir() / "data-selftest"
    try:
        _reset_dir(data_dir)
    except OSError:
        return 1
    os.environ["WENSHU_DATA_DIR"] = str(data_dir)
    os.environ["WENSHU_MOCK_FAIL_RATE"] = "0"
    # 自检只用演示模型，不导入本机的 models.local.json（避免把真实密钥写进自检数据库）
    os.environ["WENSHU_MODELS_FILE"] = str(data_dir / "models-selftest-none.json")
    cfg = load_config(data_dir=data_dir)
    cfg.ensure_dirs()
    setup_logging(cfg)
    logger.info("开始自检：%s，数据目录 %s", __version__, data_dir)
    header = f"文枢 {__version__} 自检"

    from app.launcher.entry import start_backend, stop_backend, wait_until_ready

    sock = ports.bind_socket(0)
    port = ports.socket_port(sock)
    try:
        app, server, thread = start_backend(cfg, sock)
    except Exception as exc:
        logger.exception("后端启动失败")
        _write_report(cfg.logs_dir, [header, f"FAIL health 后端启动失败：{type(exc).__name__}：{exc}"])
        return 1
    try:
        results = _run_checks(port, wait_until_ready(port, thread), cfg.db_path)
    finally:
        # 没有托盘，但退出顺序与托盘模式相同（07 第 5.1 节第 9 步）：暂停任务 → 结束事件流 → 停 Uvicorn
        stop_backend(app, server, thread)

    lines = [f"{header}，端口 {port}"]
    lines += [f"{'PASS' if ok else 'FAIL'} {name} {reason}".rstrip() for ok, name, reason in results]
    _write_report(cfg.logs_dir, lines)
    if not all(ok for ok, _name, _reason in results):
        return 1
    # 全部通过：删除 data-selftest。暂时删不掉（文件还没释放）也不影响结果
    _close_log_handlers()
    _remove_dir(data_dir)
    return 0

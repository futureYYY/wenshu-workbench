"""测试基础设施（02 第 11.1 节）：真正在监听端口的本机服务、临时数据目录、测试客户端、测试数据。

任务引擎通过真实的 HTTP 调用演示模型（http://127.0.0.1:{端口}/mock/v1），SSE 和试运行是长连接的流，Host 检查还要
知道端口，所以接口和引擎测试统一请求一个在后台线程里运行的真实 uvicorn 服务，不用 httpx.ASGITransport。

- 会话级服务：临时数据目录，WENSHU_MOCK_FAIL_RATE=0、WENSHU_DEV=1；像启动器一样先绑定 127.0.0.1:0 拿到空闲端口，
  设 WENSHU_PORT，再把 socket 交给 uvicorn；轮询 /api/health 直到就绪；结束时按 02 第 5.7 节的顺序关闭；
- 每个用例开始前调用 POST /api/_dev/reset 和 POST /mock/v1/_reset，用例之间互不影响；
- client：httpx.AsyncClient；api：同步的小客户端（带一些建模型、建任务、等待的辅助方法）；
- 测试数据：根目录 testdata/ 缺文件时先运行 scripts/make_testdata.py 生成（08 第 10.2 节）；
- 纯函数模块（渲染、输出解析、切分、编码识别、导出的单元格清理）直接调用函数测试，不经过服务。
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import sys
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import uvicorn

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
TESTDATA = ROOT / "testdata"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# app.main 在导入时会创建模块级的 app（读取环境变量决定数据目录）；先指向临时目录，避免在源码目录里建 data
os.environ.setdefault("WENSHU_DATA_DIR", tempfile.mkdtemp(prefix="wenshu-import-"))

from app.main import create_app  # noqa: E402

HEADERS = {"X-WenShu-Client": "1"}
# 写入协程每 300 毫秒提交一次：暂停后进度连续这么久不变，说明收尾的结果都已落库（见 Api.wait_job）
SETTLE_SECONDS = 1.0
# 测试客户端的空闲连接 1 秒后就不再复用：Uvicorn 在连接空闲 5 秒时关闭它，httpx 默认也是 5 秒，
# 两边同时到点时请求会发到正在关闭的连接上（Windows 上表现为 httpx.ReadError）
CLIENT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=1.0)


def _load_make_testdata() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_testdata", ROOT / "scripts" / "make_testdata.py")
    assert spec is not None and spec.loader is not None, "找不到 scripts/make_testdata.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def fixture_files() -> dict[str, Path]:
    """08 第 10.2 节的测试数据，在项目根目录的 testdata/（不提交）；缺文件时先生成，已有的不重建。"""
    return _load_make_testdata().generate(TESTDATA)


class LiveServer:
    """在后台线程里运行的真实服务。数据目录、端口都是独立的，WENSHU_MOCK_FAIL_RATE=0。
    dev=True（默认）时 WENSHU_DEV=1：注册 /api/_dev/reset，/api/system/shutdown 只暂停任务不退出。"""

    def __init__(self, data_dir: Path, *, dev: bool = True, models_file: Path | None = None,
                 cors_origins: str | None = None) -> None:
        self.data_dir = data_dir
        self.dev = dev
        self.cors_origins = cors_origins
        self.models_file = models_file or data_dir.parent / f"{data_dir.name}-models-none.json"
        # 像启动器一样：先绑定 127.0.0.1:0 拿到空闲端口，再把 socket 交给 uvicorn
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = int(self.sock.getsockname()[1])
        self.thread: threading.Thread | None = None
        self.server: uvicorn.Server | None = None
        self.app: Any = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> LiveServer:
        os.environ["WENSHU_DATA_DIR"] = str(self.data_dir)
        os.environ["WENSHU_MOCK_FAIL_RATE"] = "0"
        os.environ["WENSHU_MODELS_FILE"] = str(self.models_file)  # 不读开发者本机的 models.local.json
        os.environ["WENSHU_PORT"] = str(self.port)
        if self.dev:
            os.environ["WENSHU_DEV"] = "1"
        else:
            os.environ.pop("WENSHU_DEV", None)
        if self.cors_origins:
            os.environ["WENSHU_CORS_ORIGINS"] = self.cors_origins
        else:
            os.environ.pop("WENSHU_CORS_ORIGINS", None)
        try:
            self.app = create_app(data_dir=self.data_dir, port=self.port)
        finally:
            os.environ.pop("WENSHU_CORS_ORIGINS", None)
        config = uvicorn.Config(self.app, log_config=None, access_log=False, lifespan="on",
                                timeout_graceful_shutdown=5)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 30
        with httpx.Client(base_url=self.base_url, timeout=2, trust_env=False) as probe:
            while time.monotonic() < deadline:
                if not self.thread.is_alive():
                    raise RuntimeError("测试服务启动失败，详见数据目录里的 logs/app.log")
                try:
                    if probe.get("/api/health").status_code == 200:
                        return self
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
        raise RuntimeError("测试服务 30 秒内没有就绪")

    def stop(self) -> None:
        """02 第 5.7 节的顺序：暂停任务并提交写入 → 结束所有事件流 → 停 uvicorn → 等线程结束。"""
        from sse_starlette.sse import AppStatus

        app_state = getattr(self.app, "state", None)
        loop = getattr(app_state, "loop", None)
        manager = getattr(app_state, "job_manager", None)
        if loop is not None and manager is not None and self.thread is not None and self.thread.is_alive():
            try:
                asyncio.run_coroutine_threadsafe(manager.shutdown(), loop).result(timeout=10)
            except Exception:  # noqa: BLE001 - 关闭流程尽力而为
                pass
        AppStatus.should_exit = True
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=30)
        AppStatus.should_exit = False   # 进程级的标志：后面的测试还要起新服务
        try:
            self.sock.close()
        except OSError:
            pass

    def reset(self) -> None:
        """每个用例开始前：清空数据、重跑启动初始化，并清零演示模型的统计和“首次请求”记录。"""
        with httpx.Client(base_url=self.base_url, headers=HEADERS, timeout=30, trust_env=False) as client:
            for path in ("/api/_dev/reset", "/mock/v1/_reset"):
                resp = client.post(path)
                assert resp.status_code == 204, f"{path} → {resp.status_code}: {resp.text}"

    @property
    def ctx(self) -> Any:
        return self.app.state.ctx


class Api:
    """测试用的小客户端，自动带上 X-WenShu-Client。"""

    def __init__(self, server: LiveServer) -> None:
        self.server = server
        self.client = httpx.Client(base_url=server.base_url, headers=HEADERS, timeout=120, trust_env=False,
                                   limits=CLIENT_LIMITS)

    # ---- 基础 ----
    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.client.get(path, **kw)

    def post(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return self.client.post(path, json=json, **kw)

    def patch(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return self.client.patch(path, json=json, **kw)

    def put(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return self.client.put(path, json=json, **kw)

    def delete(self, path: str, **kw: Any) -> httpx.Response:
        return self.client.delete(path, **kw)

    @staticmethod
    def ok(resp: httpx.Response, status: int | tuple[int, ...] = (200, 201)) -> Any:
        expected = (status,) if isinstance(status, int) else status
        assert resp.status_code in expected, f"{resp.request.method} {resp.request.url} → {resp.status_code}: {resp.text}"
        return resp.json() if resp.content else None

    @staticmethod
    def error(resp: httpx.Response, status: int, code: str) -> dict[str, Any]:
        assert resp.status_code == status, f"期望 {status}，实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["error"]["code"] == code, body
        assert body["error"]["message"], body
        return body["error"]

    # ---- 文件 ----
    def upload(self, path: Path, name: str | None = None) -> dict[str, Any]:
        with path.open("rb") as fh:
            resp = self.client.post("/api/files", files={"file": (name or path.name, fh)})
        return self.ok(resp)

    def paste(self, text: str, name: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if name:
            body["name"] = name
        return self.ok(self.post("/api/files/paste", body))

    # ---- 模型、提示词 ----
    def demo_model_id(self) -> int:
        models = self.ok(self.get("/api/models", params={"include_demo": True}))["items"]
        return next(m["id"] for m in models if m["provider_kind"] == "demo")

    def mock_model(self, name: str, behavior: str | None = None, **fields: Any) -> dict[str, Any]:
        """接入一个指向演示模型接口的“真实模型”，用自定义请求头控制故障模拟。"""
        body: dict[str, Any] = {
            "name": name,
            "base_url": f"{self.server.base_url}/mock/v1",
            "model": "wenshu-demo",
            "extra_headers": {"X-Mock-Behavior": behavior} if behavior else {},
            **fields,
        }
        return self.ok(self.post("/api/models", body), 201)

    def builtin_prompt(self, task_type: str) -> dict[str, Any]:
        items = self.ok(self.get("/api/prompts", params={"task_type": task_type}))["items"]
        return next(p for p in items if p["builtin_key"] == f"{task_type}.default")

    # ---- 任务 ----
    def job_body(
        self,
        file: dict[str, Any],
        *,
        task_type: str = "classify",
        model_id: int,
        text_columns: list[str] | None = None,
        sheet: str | None = None,
        header_row: int | None = None,
        concurrency: int = 5,
        limit: int | None = 100,
        prompt_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        lines = file["kind"] == "lines"
        source = {
            "sheet": None if lines else (sheet or file["sheets"][0]["name"]),
            "header_row": 0 if lines else (1 if header_row is None else header_row),
            "text_columns": ["text"] if lines else (text_columns or []),
            "join_mode": extra.pop("join_mode", "labeled"),
            "start_row": extra.pop("start_row", None),
            "limit": limit,
            "split_mode": "line",
        }
        return {
            "task_type": task_type,
            "file_id": file["id"],
            "source": source,
            "prompt_id": prompt_id or self.builtin_prompt(task_type)["id"],
            "model_id": model_id,
            "concurrency": concurrency,
            **extra,
        }

    def create_job(self, file: dict[str, Any], **kw: Any) -> dict[str, Any]:
        return self.ok(self.post("/api/jobs", self.job_body(file, **kw)), 201)

    def job(self, job_id: int) -> dict[str, Any]:
        return self.ok(self.get(f"/api/jobs/{job_id}"))

    def wait_job(self, job_id: int, statuses: tuple[str, ...] = ("completed",), timeout: float = 90,
                 idle: bool = True) -> dict[str, Any]:
        """等任务进入指定状态；idle=True 时还要等进行中的条目归零、结果也都已落库（暂停后正在跑完的）。

        progress.running 是引擎内存里正在处理的条数（03 第 7 节）：一条处理完就不再计入，结果却要等写入协程下一次
        提交（最多 300 毫秒）才计入 succeeded、failed，这一小段时间里它被算进 pending。completed 由执行器在全部
        结果落库后才写，读到时计数一定一致；暂停、取消没有这一步，所以 running 归零后再等进度连续 SETTLE_SECONDS
        秒不变。"""
        deadline = time.monotonic() + timeout
        job: dict[str, Any] = {}
        steady: tuple[dict[str, Any], float] | None = None      # (进度, 从何时起没再变)
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] in statuses and (not idle or job["progress"]["running"] == 0):
                if not idle or job["status"] == "completed":
                    return job
                now = time.monotonic()
                if steady is None or steady[0] != job["progress"]:
                    steady = (job["progress"], now)
                elif now - steady[1] >= SETTLE_SECONDS:
                    return job
            else:
                steady = None
            time.sleep(0.2)
        raise AssertionError(f"任务 {job_id} 在 {timeout} 秒内没有进入 {statuses}：{job.get('status')} {job.get('progress')}")

    def items(self, job_id: int, **params: Any) -> list[dict[str, Any]]:
        params.setdefault("limit", 500)
        return self.ok(self.get(f"/api/jobs/{job_id}/items", params=params))["items"]

    def mock_stats(self) -> dict[str, Any]:
        """GET /mock/v1/_stats：inflight、max_inflight、total、by_status（04 第 11 节）。"""
        return self.ok(self.client.get("/mock/v1/_stats"))

    def mock_reset(self) -> None:
        assert self.client.post("/mock/v1/_reset").status_code == 204


@pytest.fixture(scope="session")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    live = LiveServer(tmp_path_factory.mktemp("data")).start()
    yield live
    live.stop()


@pytest.fixture(scope="session")
def _session_api(server: LiveServer) -> Iterator[Api]:
    client = Api(server)
    yield client
    client.client.close()


@pytest.fixture
def api(server: LiveServer, _session_api: Api) -> Api:
    """每个用例开始前重置服务的数据（POST /api/_dev/reset、POST /mock/v1/_reset）。"""
    server.reset()
    return _session_api


@pytest.fixture
async def client(server: LiveServer, api: Api) -> AsyncIterator[httpx.AsyncClient]:
    """02 第 11.1 节的 client：httpx.AsyncClient，自动带上 X-WenShu-Client。依赖 api，所以同样先重置。"""
    async with httpx.AsyncClient(base_url=server.base_url, headers=HEADERS, timeout=120, trust_env=False,
                                 limits=CLIENT_LIMITS) as c:
        yield c


@pytest.fixture
def fresh_server(tmp_path: Path) -> Iterator[LiveServer]:
    """每个测试一个全新的数据目录和服务（测首次启动的初始化、重启恢复等需要干净数据库的场景）。"""
    live = LiveServer(tmp_path / "data").start()
    yield live
    live.stop()


@pytest.fixture
def fresh_api(fresh_server: LiveServer) -> Iterator[Api]:
    client = Api(fresh_server)
    yield client
    client.client.close()


@pytest.fixture
def fast_model(api: Api) -> dict[str, Any]:
    """延迟 0–5 毫秒的演示模型（大量条目的测试用）。"""
    return api.mock_model("测试-快速", "fast")


def unique_lines(prefix: str, count: int) -> str:
    return "\n".join(f"{prefix} 第 {i} 条：请问我的快递到哪了 {i * 7919 % 10007}" for i in range(1, count + 1))

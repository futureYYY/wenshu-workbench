"""源码版启动前检查（07 第 5.5 节），由 启动文枢.bat 用 backend\\.venv 里的 Python 运行。只用标准库。

0. 已经在运行时什么都不做：%WENSHU_DATA_DIR%\\runtime.json 存在、且它记录的端口上 /api/health 能连上
   （超时 1 秒）时直接以退出码 0 结束，不安装、不构建，随后启动器因单实例检查直接打开已有界面。
   这时源码有改动就提示一句。原因：运行中的进程占用着虚拟环境里已加载的 .pyd 文件，pip 会安装失败；
   删除 backend/app/static 会让正在使用的界面资源 404。runtime.json 存在但连不上（上次异常退出）时照常往下执行；
1. 后端依赖：backend/requirements.txt 的 SHA-256 与 backend/.venv/.wenshu-deps 里记录的不同（或没有记录）时，
   执行 pip install -r backend/requirements.txt，成功后写入新的哈希；
2. 前端构建：前端指纹（frontend/src、frontend/public 下全部文件，以及 index.html、package.json、
   package-lock.json、vite.config.ts、tsconfig*.json、.env* 的相对路径、修改时间、大小）与
   backend/app/static/.wenshu-build 里记录的不同时，重新构建并复制到 backend/app/static；
3. 参数 --write-stamp：只计算并写入前端指纹，不构建（build-web.bat 构建完成后调用）；
4. 参数 --check-running：只做第 0 步的检查，正在运行时退出码 1，否则 0（build-web.bat 构建前调用）。

没有变化时一秒内结束。退出码 0 表示可以启动，1 表示失败（启动文枢.bat 会停下来显示上面的输出）。
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

REQUIREMENTS = BACKEND / "requirements.txt"
DEPS_STAMP = BACKEND / ".venv" / ".wenshu-deps"
STATIC = BACKEND / "app" / "static"
BUILD_STAMP = STATIC / ".wenshu-build"
DIST = FRONTEND / "dist"
NODE_MODULES = FRONTEND / "node_modules"
LOCK_FILE = FRONTEND / "package-lock.json"
LOCK_STAMP = NODE_MODULES / ".wenshu-lock"

DEFAULT_DATA_DIR = ROOT / "data"   # 启动文枢.bat、build-web.bat 没有设置 WENSHU_DATA_DIR 时的默认值
HEALTH_TIMEOUT_S = 1.0
RUNNING_HINT = "文枢正在运行，从托盘退出后再启动才会用上新的改动。"

FINGERPRINT_DIRS = ("src", "public")
FINGERPRINT_FILES = ("index.html", "package.json", "package-lock.json", "vite.config.ts")
FINGERPRINT_GLOBS = ("tsconfig*.json", ".env*")


def say(message: str) -> None:
    print(message, flush=True)


def sha256_file(path: Path) -> str:
    """文件不存在时返回空字符串。"""
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def read_stamp(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_stamp_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 第 0 步：是否已经在运行


def data_dir() -> Path:
    env = os.environ.get("WENSHU_DATA_DIR", "").strip()
    return Path(env).expanduser() if env else DEFAULT_DATA_DIR


def running_port() -> int | None:
    """这个数据目录的文枢正在运行时返回它的端口：runtime.json 存在，且 /api/health 能连上。"""
    try:
        data = json.loads((data_dir() / "runtime.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port = data.get("port") if isinstance(data, dict) else None
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        return None
    # 不走系统代理：开着代理软件时，发往 127.0.0.1 的请求也可能被转发出去
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=HEALTH_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        return None  # 连不上：上次异常退出留下的 runtime.json
    return port if isinstance(body, dict) and body.get("status") == "ok" else None


def sources_changed() -> bool:
    """后端依赖或前端源码相对上一次安装、构建有没有变化（只比较，不安装、不构建）。"""
    if read_stamp(DEPS_STAMP) != sha256_file(REQUIREMENTS):
        return True
    if not (STATIC / "index.html").is_file():
        return True
    return read_stamp(BUILD_STAMP) != frontend_fingerprint()


# ---------------------------------------------------------------- 后端依赖


def ensure_backend_deps() -> bool:
    if not REQUIREMENTS.is_file():
        say("没有找到 backend/requirements.txt，源码目录不完整。")
        return False
    want = sha256_file(REQUIREMENTS)
    if read_stamp(DEPS_STAMP) == want:
        return True
    say("正在安装后端依赖（第一次启动、或 backend/requirements.txt 有变化时才需要）……")
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)]
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        say("后端依赖安装失败。检查网络或 pip 源后重新双击 启动文枢.bat。")
        say("如果提示找不到某个版本，可能是镜像还没同步，见 docs/07-packaging.md 第 2.1 节。")
        return False
    write_stamp_file(DEPS_STAMP, want)
    say("后端依赖已安装。")
    return True


# ---------------------------------------------------------------- 前端构建


def frontend_inputs() -> list[Path]:
    files: dict[str, Path] = {}
    for name in FINGERPRINT_DIRS:
        base = FRONTEND / name
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                files[path.relative_to(FRONTEND).as_posix()] = path
    for name in FINGERPRINT_FILES:
        path = FRONTEND / name
        if path.is_file():
            files[name] = path
    for pattern in FINGERPRINT_GLOBS:
        for path in FRONTEND.glob(pattern):
            if path.is_file():
                files[path.relative_to(FRONTEND).as_posix()] = path
    return [files[key] for key in sorted(files)]


def frontend_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in frontend_inputs():
        stat = path.stat()
        rel = path.relative_to(FRONTEND).as_posix()
        digest.update(f"{rel}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
    return digest.hexdigest()


def run_npm(*args: str) -> bool:
    npm = shutil.which("npm")
    if npm is None:
        return False
    command = ["cmd", "/c", "npm", *args] if os.name == "nt" else [npm, *args]
    say("> npm " + " ".join(args))
    return subprocess.run(command, cwd=FRONTEND).returncode == 0


def ensure_node_modules() -> bool:
    """node_modules 不存在、或 package-lock.json 变了时安装前端依赖。"""
    lock_hash = sha256_file(LOCK_FILE)
    if NODE_MODULES.is_dir():
        recorded = read_stamp(LOCK_STAMP)
        if not recorded:
            # 开发者自己执行过 npm install：认为依赖是最新的，记下当前的锁文件
            write_stamp_file(LOCK_STAMP, lock_hash)
            return True
        if recorded == lock_hash:
            return True
    # npm ci 需要 package-lock.json；第一次安装还没有锁文件时用 npm install 生成它
    ok = run_npm("ci") if LOCK_FILE.is_file() else run_npm("install")
    if ok:
        write_stamp_file(LOCK_STAMP, sha256_file(LOCK_FILE))
    return ok


def copy_dist() -> None:
    if STATIC.exists():
        shutil.rmtree(STATIC)
    shutil.copytree(DIST, STATIC)


def write_build_stamp() -> None:
    # 构建完成后再计算：npm install 可能刚生成了 package-lock.json
    write_stamp_file(BUILD_STAMP, frontend_fingerprint())


def ensure_frontend() -> bool:
    built = (STATIC / "index.html").is_file()
    if built and read_stamp(BUILD_STAMP) == frontend_fingerprint():
        return True
    if shutil.which("npm") is None:
        if built:
            say("前端源码有变化，但没有找到 Node.js，继续使用上一次构建的界面。")
            return True
        say("第一次启动需要 Node.js 24 来构建界面。安装 Node.js 24 后重新双击 启动文枢.bat。")
        return False
    say("正在构建界面（第一次启动、或前端源码有变化时才需要）……")
    if not ensure_node_modules():
        say("前端依赖安装失败。检查网络或 npm 源后重试。")
        return False
    if not run_npm("run", "build"):
        say("前端构建失败，详见上面的输出。")
        return False
    if not (DIST / "index.html").is_file():
        say("构建结束了，但没有找到 frontend/dist/index.html。")
        return False
    try:
        copy_dist()
    except OSError as exc:
        say(f"复制构建产物到 backend/app/static 失败：{exc}")
        say("如果文枢正在运行，先从托盘退出再重试。")
        return False
    write_build_stamp()
    say("界面已构建。")
    return True


def main(argv: list[str]) -> int:
    if "--write-stamp" in argv:
        if not (STATIC / "index.html").is_file():
            say("backend/app/static 里还没有构建产物，没有写入前端指纹。")
            return 1
        write_build_stamp()
        return 0
    port = running_port()
    if "--check-running" in argv:
        return 1 if port is not None else 0
    if port is not None:
        if sources_changed():
            say(RUNNING_HINT)
        return 0
    if not ensure_backend_deps():
        return 1
    if not ensure_frontend():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

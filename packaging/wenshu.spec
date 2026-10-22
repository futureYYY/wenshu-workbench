# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 配置（07 第 6 节）。由 scripts\build.bat 第 5 步在项目根目录执行：
#   backend\.venv\Scripts\python.exe -m PyInstaller packaging\wenshu.spec --noconfirm --clean --distpath build\dist --workpath build\pyinstaller
# 目录模式（onedir）：产物是 build\dist\WenShu\WenShu.exe 加 _internal\，build.bat 自检、压缩后再同步到
# release\WenShu（保留那里的 data）。不要把 --distpath 改成 release：PyInstaller 重建输出目录时会先整个删掉它。
# 不用单文件模式、不开 UPX：单文件每次启动都要解压到临时目录，慢好几秒，也更容易被杀毒软件误报。
from pathlib import Path

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"

a = Analysis(
    # 入口只有一行 from app.launcher.entry import main; main()。不直接用 entry.py：PyInstaller 把入口当作
    # 没有父包的顶层脚本运行，包内的相对导入要到打包后才报错
    [str(ROOT / "packaging" / "wenshu_main.py")],
    pathex=[str(BACKEND)],
    datas=[
        # 前端构建产物（scripts\build-web.bat 复制进来），运行时位于 _internal\app\static
        (str(BACKEND / "app" / "static"), "app/static"),
        # 数据库迁移文件，运行时位于 _internal\app\db\migrations
        (str(BACKEND / "app" / "db" / "migrations"), "app/db/migrations"),
        # /docs 用的 Swagger UI 静态文件（02 第 2.2 节），运行时位于 _internal\app\vendor\swagger-ui
        (str(BACKEND / "app" / "vendor" / "swagger-ui"), "app/vendor/swagger-ui"),
        # exe 和托盘图标，运行时位于 _internal\icon.ico
        (str(ROOT / "packaging" / "icon.ico"), "."),
    ],
    hiddenimports=[
        # SQLAlchemy 按 URL 里的名字动态加载方言；asyncio 扩展依赖 greenlet
        "aiosqlite",
        "sqlalchemy.dialects.sqlite.aiosqlite",
        "greenlet",
        # Uvicorn 按字符串名字加载日志、事件循环、协议和 lifespan 实现
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # anyio 按名字加载 asyncio 后端（Starlette、openai 的 HTTP 客户端都用到）
        "anyio._backends._asyncio",
        # FastAPI、Starlette 解析上传表单时才导入
        "python_multipart",
        "multipart",
        # 托盘：pystray 按平台动态导入后端实现
        "pystray._win32",
        # 编译扩展与延迟导入，静态分析偶尔漏掉
        "python_calamine",
        "sse_starlette",
        "json_repair",
        # charset-normalizer 3.5.x 的 Windows 版只带 md、cd 两个编译模块（没有 md__mypyc），经包内的普通 import 收集；
        # 它在 UTF-8、GB18030 都解不开时才延迟导入（file_parser/detect.py），自检碰不到；发布前用一个 Windows-1252
        # （西欧）编码的 csv 试一次，判据是打包版和源码版识别结果一致（Big5 的字节大多能按 GB18030 解开，走不到这一步）
        "charset_normalizer",
        # 识别文件编码时按名字查找的编解码器
        "encodings.gb18030",
        "encodings.gbk",
        "encodings.utf_16",
        "encodings.utf_8_sig",
    ],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WenShu",
    icon=str(ROOT / "packaging" / "icon.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="WenShu", upx=False)

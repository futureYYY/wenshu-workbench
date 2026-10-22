# 07 环境搭建、开发、打包与启动

> 文枢开发文档 · 第 7 篇。本文针对这台开发机（ROG Strix G834JY，Windows）的实测环境编写。

## 1. 本机环境

| 项 | 实测状态 | 本项目的用法 |
|---|---|---|
| Node.js 24.12.0、npm 11.6.2 | 已在 PATH，npm 源为 npmmirror | 前端直接使用 |
| Python 3.13.9 | 示例：`C:\Python313\python.exe` | 用它在项目里创建 venv |
| pip 26.0.1 | 源为华为云（用户级配置） | venv 里的 pip 同样使用这个源 |
| uv 0.12.23 | 不在 PATH | 不依赖 |
| Git 2.52.0 | 已装 | |
| Playwright 1.64.1、Chrome、Edge | 已装 | 端到端测试用 Edge 通道，不额外下载浏览器 |
| JDK 8、Maven、Docker、PostgreSQL | 已装或未运行 | 本项目都不用 |

注意：Git Bash 里的 `python`、`python3` 是坏掉的别名，没有输出。所有命令一律写 venv 里 Python 的完整路径，并在 cmd 中执行。

## 2. 首次搭建

### 2.1 后端

在项目根目录打开 cmd：

```bat
"C:\Python313\python.exe" -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe -c "import fastapi, openai, python_calamine, sqlalchemy; print('ok')"
```

如果华为云镜像还没同步到某个刚发布的版本，安装会报“找不到版本”：等一会儿再装，或者这一次加 `-i https://pypi.org/simple`。

以上是开发用的完整环境（含测试和打包工具）。只想用源码版一键启动、不做开发的话，不需要手动执行这些命令，双击 `启动文枢.bat` 会自动完成（第 5.5 节）。两者使用同一个 `backend\.venv`。

把本机 Python 的路径写进 `scripts\local.env.cmd`（从 `scripts\local.env.cmd.example` 复制，不提交），批处理脚本创建虚拟环境时会用它：

```bat
set "WENSHU_PYTHON=C:\Python313\python.exe"
```

### 2.2 前端

```bat
cd frontend
npm install
```

端到端测试使用本机已安装的 Edge（`playwright.config.ts` 里 `use: { channel: "msedge" }`），不需要 `npx playwright install`。

### 2.3 字体

默认方案全部来自 npm，随 `npm install` 安装，OFL 许可，可以自由打包：

```ts
// frontend/src/main.ts
import "@fontsource-variable/noto-sans-sc"   // 界面字体，按字符范围分成多个小文件，只加载用到的部分
import "@fontsource-variable/overpass"       // 导视数字
import "@fontsource/overpass-mono/400.css"   // 等宽
```

构建后字体文件位于 `dist/assets`，由本机服务提供，断网也能显示。

**可选：换成 HarmonyOS Sans SC。** 它的许可协议允许把**未经修改**的字体文件随软件免费分发，但要求附带许可协议并在软件中做出声明，而且不允许修改字体；子集化或转成 woff2 是否算修改，协议里没有写清楚。所以如果要换：

1. 从华为开发者网站的设计资源页面下载官方字体包（npm 上的非官方打包版本没有授权，不要用）；
2. 取 SC 的 Regular、Medium、Bold 三个 ttf，**原样**放进 `frontend/src/assets/fonts/harmonyos/`，许可协议文件放在同一目录，构建时一并复制到发布目录；
3. 用 `@font-face` 声明（`format("truetype")`），在 `--font-sans` 最前面加 `"HarmonyOS Sans SC"`；
4. 在设置页“数据”分组下加一行“本软件使用了 HarmonyOS Sans 字体”。

### 2.4 图标

- `packaging/icon.svg`：按 06 第 2 节的 Logo 规格绘制；同一份 SVG 复制为 `frontend/public/favicon.svg`（独立窗口的任务栏图标取自网页图标）；
- `packaging/make_icon.py`：用 Pillow 的基本图形（圆角矩形、线段）按 4 倍尺寸绘制后缩小，生成 16、24、32、48、64、128、256 px 的 `packaging/icon.ico`。Pillow 不能渲染 SVG，所以这里按同样的几何参数直接画，不读 SVG；
- 托盘图标用 Pillow 读取 `icon.ico` 中 64 px 的那一张。

## 3. 开发：`scripts\dev.bat`

批处理文件只写 ASCII 字符（提示文字用英文），避免 cmd 的编码问题。

```bat
@echo off
setlocal
cd /d "%~dp0.."

if not exist "backend\.venv\Scripts\python.exe" (
  echo Backend venv not found. See docs\07-packaging.md section 2.1.
  exit /b 1
)

set "WENSHU_DEV=1"
set "WENSHU_PORT=18765"
set "WENSHU_DATA_DIR=%CD%\.devdata"
set "WENSHU_MOCK_FAIL_RATE=0.02"

netstat -ano | findstr /r /c:":%WENSHU_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Port %WENSHU_PORT% is already in use, probably by a running WenShu.
  echo Quit it from the tray icon, then run dev.bat again.
  exit /b 1
)

start "WenShu API" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %WENSHU_PORT% --reload --reload-dir app"
start "WenShu Web" cmd /k "cd /d frontend && npm run dev"

echo API:  http://127.0.0.1:%WENSHU_PORT%/docs
echo Web:  http://127.0.0.1:5173
timeout /t 4 >nul
start "" http://127.0.0.1:5173
```

- `app/main.py` 在模块级提供 `app = create_app()`，供 `uvicorn app.main:app` 使用；
- 开发数据放在项目下的 `.devdata`，不会和正式数据混在一起，也不提交；
- 启动前检查端口：打包版或源码版正在用 18765 时直接提示退出。启动器绑定端口时用了独占模式（第 5.1 节第 3 步），但开发用的 uvicorn 绑定端口时开了 `SO_REUSEADDR`，先检查能给出更明白的提示。

`frontend/vite.config.ts` 的开发服务器设置：

```ts
const apiTarget = process.env.WENSHU_API_TARGET ?? "http://127.0.0.1:18765"

server: {
  host: "127.0.0.1",
  port: 5173,
  strictPort: true,
  proxy: {
    "/api": { target: apiTarget, changeOrigin: true },
    "/mock": { target: apiTarget, changeOrigin: true },
    "/docs": { target: apiTarget, changeOrigin: true },
    "/docs-assets": { target: apiTarget, changeOrigin: true },
    "/openapi.json": { target: apiTarget, changeOrigin: true },
  },
},
```

`changeOrigin: true` 让转发后的 `Host` 变成后端的地址（如 `127.0.0.1:18765`），才能通过后端的 Host 检查（02 第 10 节）。SSE 经过这个代理可以正常推送。端到端测试把 `WENSHU_API_TARGET` 指向它自己启动的后端（08 第 10.4 节）。

## 4. 构建：`scripts\build.bat`

```bat
@echo off
setlocal
cd /d "%~dp0.."
set "PY=backend\.venv\Scripts\python.exe"

tasklist /fi "imagename eq WenShu.exe" | find /i "WenShu.exe" >nul
if not errorlevel 1 (
  echo WenShu.exe is running. Quit it from the tray icon, then build again.
  goto :fail
)

echo [1/7] Backend tests
"%PY%" -m pytest backend\tests -q || goto :fail

echo [2/7] Frontend typecheck
pushd frontend
call npm run typecheck || (popd & goto :fail)
popd

echo [3/7] Frontend build into backend\app\static
call "scripts\build-web.bat" || goto :fail

echo [4/7] Version info
"%PY%" packaging\make_version_info.py || goto :fail

echo [5/7] PyInstaller into build\dist
"%PY%" -m PyInstaller packaging\wenshu.spec --noconfirm --clean --distpath build\dist --workpath build\pyinstaller || goto :fail

echo [6/7] Self test
start "" /wait "build\dist\WenShu\WenShu.exe" --selftest
if errorlevel 1 (
  echo Self test failed. See build\dist\WenShu\data-selftest\logs\selftest.log
  goto :fail
)

echo [7/7] Zip, then update release\WenShu and keep its data folder
if not exist "release" mkdir "release"
powershell -NoProfile -Command "Compress-Archive -Path 'build\dist\WenShu' -DestinationPath 'release\WenShu.zip' -Force" || goto :fail
if exist "release\WenShu" (
  for /d %%D in ("release\WenShu\*") do if /i not "%%~nxD"=="data" rmdir /s /q "%%D"
  del /q "release\WenShu\*" 2>nul
)
xcopy /e /i /q /y "build\dist\WenShu" "release\WenShu" >nul || goto :fail
echo Done: release\WenShu\WenShu.exe and release\WenShu.zip
exit /b 0

:fail
echo Build failed.
exit /b 1
```

- **不要让 PyInstaller 直接输出到 `release`**：它重建输出目录时会先整个删掉 `release\WenShu`，打包版在那里用过的 `data`（任务、设置、`secret.key` 和已保存的 API Key）会一起消失。所以先输出到 `build\dist`，自检、压缩都在那里做，最后只替换 `release\WenShu` 里 `data` 以外的内容；
- 压缩包从 `build\dist\WenShu` 生成，保证发布物里没有任何人的数据；
- `WenShu.exe` 是窗口程序，必须用 `start "" /wait` 才能拿到退出码；
- 版本号只有一个来源：`backend/app/__init__.py` 的 `__version__`。`packaging/make_version_info.py` 据此生成 `packaging/version_info.txt`（exe 文件属性），前端从 `/api/system/info` 读取版本号显示在设置页；
- 打包前先跑测试和类型检查，任何一步失败都停止。

## 5. 启动器

启动流程写在 `backend/app/launcher/entry.py` 的 `main()` 里，打包版和源码版共用：打包版的入口脚本是 `packaging/wenshu_main.py`（第 6 节），源码版是 `pythonw.exe -m app.launcher`（`app/launcher/__main__.py`，第 5.5 节），两者都只调用 `main()`。`app/launcher/` 下只用绝对导入。命令行参数：`--selftest`（自检）、`--browser`（这一次强制用默认浏览器）、`--no-open`（不打开界面）。

### 5.1 启动流程

1. 调用 `multiprocessing.freeze_support()`；解析路径并确定数据目录（02 第 9.1 节）；初始化日志。窗口程序没有控制台，`sys.stdout` 为 `None`，所有输出只走日志文件。
2. **单实例**：通过 ctypes 调用 `CreateMutexW(None, False, 名称)`，名称为 `"Local\\WenShu." + sha1(数据目录绝对路径转小写)[:12]`，即同一个数据目录只能有一个实例（打包版和源码版默认数据目录不同，可以同时运行）。`GetLastError()` 为 183 表示已有实例：
   - 读取 `data/runtime.json` 中的端口，请求 `/api/health`（超时 2 秒，最多 5 次，间隔 1 秒）；
   - 成功：按打开方式打开界面，退出码 0；
   - 失败：用 `MessageBoxW` 提示“文枢已在运行但没有响应。请在任务栏右下角的文枢图标上右键选择退出，然后重新打开。”，退出码 1。
3. **端口**：读取设置 `preferred_port`（数据库还不存在时用 18765）。自己创建 socket，**绑定前**设置 `sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)`，再绑定 `127.0.0.1:端口`，失败则绑定端口 0 取系统分配的空闲端口。把这个已绑定的 socket 交给 Uvicorn，避免“检查空闲”和“真正绑定”之间被其他程序抢占。独占模式是 Windows 上必须的：不设的话，之后启动的开发用 uvicorn（开了 `SO_REUSEADDR`）还能绑定同一个端口，请求会随机落到两个进程上。
4. **启动后端**：设置环境变量 `WENSHU_PORT`；`uvicorn.Config(app=create_app(), log_config=None, access_log=False, timeout_graceful_shutdown=5)`；在后台线程中执行 `server.run(sockets=[sock])`。应用生命周期启动时，把后端线程的事件循环（`asyncio.get_running_loop()`）和 `JobManager` 交给启动器保存，第 9 步要用。
5. **等待就绪**：轮询 `/api/health`，最多 15 秒；超时则弹窗“文枢启动失败，详情见 data\logs\app.log”，退出码 1。
6. 写 `data/runtime.json`：`{"port": 18765, "pid": 1234, "version": "1.0.0", "started_at": "…"}`。
7. **打开界面**（第 5.2 节），`--no-open` 时跳过。
8. **托盘**：主线程运行托盘图标（第 5.3 节），直到用户选择退出。
9. **退出**。两个入口最后都让主线程的托盘循环结束：托盘“退出”菜单直接调用 `icon.stop()`；`POST /api/system/shutdown` 先返回 202，再调用启动器注册在 `app.state` 上的退出回调，回调里调用 `icon.stop()`（pystray 的 `stop()` 可以在其他线程调用）。托盘循环结束后，主线程按顺序执行：
   1. `asyncio.run_coroutine_threadsafe(job_manager.shutdown(), loop).result(timeout=10)`：在后端的事件循环里执行 02 第 5.7 节第 1–3 步（暂停任务、等进行中的请求、写入协程全部提交），等它完成；
   2. 设置 `sse_starlette.sse.AppStatus.should_exit = True`，结束所有事件流（02 第 5.7 节第 4 步）；
   3. `server.should_exit = True`；
   4. 等后端线程结束，最多 15 秒；
   5. 删除 `runtime.json`，释放互斥量，退出码 0。

   第 2 步必须在第 3 步之前：界面开着时事件流一直连着，后端在非主线程里收不到退出信号，不先结束事件流，uvicorn 会一直等下去。没有托盘的自检模式（第 5.4 节）结束时同样按第 1–5 步退出。

### 5.2 打开界面

设置 `open_mode = "app"`（默认）时，按顺序查找浏览器：

1. 注册表 `HKLM` / `HKCU` 下 `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe`；
2. `%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe`、`%ProgramFiles%\Microsoft\Edge\Application\msedge.exe`；
3. 同样方式查找 `chrome.exe`（另加 `%LocalAppData%\Google\Chrome\Application\chrome.exe`）。

找到后以独立进程启动：

```text
msedge.exe --app=http://127.0.0.1:{端口}/ --user-data-dir="{数据目录}\browser" --no-first-run --no-default-browser-check --window-size=1600,1000
```

- `--app` 打开没有标签栏和地址栏的独立窗口；
- 使用专用的 `--user-data-dir`，保证总是启动一个独立的浏览器实例，`--window-size` 等参数才会生效，窗口位置和大小也会被这个目录记住，不影响用户日常使用的浏览器；
- 用 `subprocess.Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True)` 启动，不等待；
- 一个浏览器都找不到时，改用 `webbrowser.open(url)`，并在日志里记一条警告。

`open_mode = "browser"` 或带 `--browser` 参数时，直接 `webbrowser.open(url)`。

### 5.3 托盘图标

- `pystray.Icon("WenShu", 图标, "文枢", 菜单)`；
- 菜单：“打开文枢”（默认项，左键单击也执行它）、“打开数据目录”、分隔线、“退出”；
- 悬停提示每 5 秒更新：没有运行中的任务时为“文枢”，否则为“文枢：2 个任务运行中”。数据取自 `JobManager` 维护的运行中任务数（一个只在事件循环线程里写、托盘线程只读的整数）；
- **首次关闭提示**：`EventBus` 统计全局 SSE 连接数。连接数从 1 以上降到 0 并持续 3 秒（说明界面窗口被关掉了），且设置 `first_close_hint_shown` 为 false 时，托盘弹出气泡“文枢仍在后台运行，可以从这里重新打开或退出”，然后把设置改为 true；
- P1：任务完成时托盘气泡通知。

### 5.4 自检（`--selftest`）

- 使用独立的数据目录 `{程序目录}\data-selftest`（启动前清空），不显示托盘，不打开界面，端口取系统分配的空闲端口；启动后端前设 `WENSHU_MOCK_FAIL_RATE=0`，避免演示模型的随机故障让自检无故失败；
- 依次检查，每项在 `data-selftest\logs\selftest.log` 中写一行“PASS / FAIL 项目 原因”：
  1. `GET /api/health` 返回 ok；
  2. `GET /` 返回的 HTML 中有前端挂载点；
  3. 数据库 `user_version ≥ 1`，两个内置提示词和演示模型都存在；
  4. 对演示模型执行测试连接，`ok` 为 true；
  5. 用内置意图识别提示词对演示模型试运行一次，`done` 事件里有解析出的类别；
  6. 粘贴一段三行文本建文件，对它调用预估接口，`item_count = 3`；
- 全部通过：删除 `data-selftest`，退出码 0；有失败：保留目录和日志，退出码 1。

### 5.5 源码一键启动：`启动文枢.bat`

源码版运行的是和 exe 同一套启动器（`python -m app.launcher` 调用 `entry.py`），所以界面、功能、托盘、单实例都和打包版一样。区别：用项目里的 `backend\.venv` 代替打包进去的运行时，用 `backend\app\static` 代替打包进去的前端；每次启动用的都是当前源码。用 `pythonw.exe` 运行，没有命令行窗口。

**前提**：第一次启动需要本机有 Python 3.13（创建虚拟环境）和 Node.js 24（构建前端）。之后只要前端源码不变，就不再需要 Node.js。

| 文件 | 作用 |
|---|---|
| `启动文枢.bat`（项目根目录） | 一键启动入口 |
| `scripts\setup.bat` | 只在第一次运行：创建 `backend\.venv` |
| `scripts\prestart.py` | 每次启动前运行（只用标准库）：依赖或前端源码有变化才安装、构建，否则一秒内结束 |
| `scripts\build-web.bat` | 构建前端并复制到 `backend\app\static`；也可以手动运行，`build.bat` 也调用它 |
| `scripts\local.env.cmd.example` | 本机配置示例，复制为 `local.env.cmd`（不提交） |

`启动文枢.bat`（批处理只写 ASCII，提示用英文；文件名可以是中文）：

```bat
@echo off
setlocal
cd /d "%~dp0"
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"
if not defined WENSHU_DATA_DIR set "WENSHU_DATA_DIR=%CD%\data"

if not exist "backend\.venv\Scripts\pythonw.exe" (
  call "scripts\setup.bat" || goto :fail
)

"backend\.venv\Scripts\python.exe" "scripts\prestart.py" || goto :fail

start "" /d "%CD%\backend" "%CD%\backend\.venv\Scripts\pythonw.exe" -m app.launcher
exit /b 0

:fail
echo.
echo WenShu could not start. Read the messages above, then press any key to close.
pause >nul
exit /b 1
```

`scripts\setup.bat`：

```bat
@echo off
setlocal
cd /d "%~dp0.."
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"

set "PYEXE="
if defined WENSHU_PYTHON if exist "%WENSHU_PYTHON%" set PYEXE="%WENSHU_PYTHON%"
if not defined PYEXE py -3.13 -c "import sys" >nul 2>nul && set "PYEXE=py -3.13"
if not defined PYEXE python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo Python 3.13 was not found.
  echo Copy scripts\local.env.cmd.example to scripts\local.env.cmd and set WENSHU_PYTHON.
  exit /b 1
)

echo Creating backend\.venv ...
%PYEXE% -m venv "backend\.venv" || exit /b 1
exit /b 0
```

`scripts\prestart.py` 的逻辑（只用标准库，输出可以用中文，Python 会正确显示在控制台里）：

0. **已经在运行时什么都不做**：读取 `%WENSHU_DATA_DIR%\runtime.json`，存在则请求 `http://127.0.0.1:{port}/api/health`（超时 1 秒）。能连上说明这个数据目录的文枢已经在运行，直接以退出码 0 结束，不安装、不构建，随后启动器会因单实例检查直接打开已有界面。这时如果源码有改动，打印“文枢正在运行，从托盘退出后再启动才会用上新的改动”。原因：运行中的进程占用着虚拟环境里已加载的 `.pyd` 文件，pip 会安装失败；删除 `backend\app\static` 会让正在使用的界面资源 404。`runtime.json` 存在但连不上时（上次异常退出），照常往下执行。
1. **后端依赖**：计算 `backend/requirements.txt` 的 SHA-256，与 `backend/.venv/.wenshu-deps` 里记录的比较。不同或没有记录时，执行 `python -m pip install -r backend/requirements.txt`（输出直接显示），成功后写入新的哈希；失败则提示并以退出码 1 结束。
2. **前端构建**：计算前端指纹，即以下文件的相对路径、修改时间、大小拼起来的 SHA-256：`frontend/src/`、`frontend/public/` 下的全部文件，以及 `index.html`、`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig*.json`、`.env*`。与 `backend/app/static/.wenshu-build` 里记录的比较：
   - 一致且 `backend/app/static/index.html` 存在：跳过；
   - 需要构建但找不到 Node.js（`shutil.which("npm")` 为空）：已有旧的构建产物时，打印“前端源码有变化，但没有找到 Node.js，继续使用上一次构建的界面”并继续；没有构建产物时提示“第一次启动需要 Node.js 24 来构建界面”，退出码 1；
   - 需要构建：`node_modules` 不存在或 `package-lock.json` 变了时先执行 `cmd /c npm ci`，再执行 `cmd /c npm run build`（工作目录 `frontend`）；成功后删除旧的 `backend/app/static`，把 `frontend/dist` 复制过去，写入新指纹。失败则退出码 1。
3. 支持参数 `--write-stamp`：只计算并写入前端指纹，不构建（`build-web.bat` 构建完成后调用，避免下次启动重复构建）。
4. 支持参数 `--check-running`：只做第 0 步的检查，正在运行时退出码 1，否则 0（`build-web.bat` 构建前调用）。

`scripts\build-web.bat`：

```bat
@echo off
setlocal
cd /d "%~dp0.."
if exist "scripts\local.env.cmd" call "scripts\local.env.cmd"
if not defined WENSHU_DATA_DIR set "WENSHU_DATA_DIR=%CD%\data"
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "scripts\prestart.py" --check-running
  if errorlevel 1 (
    echo WenShu is running from this folder. Quit it from the tray icon, then run build-web.bat again.
    exit /b 1
  )
)
pushd frontend
if not exist "node_modules" (call npm ci || (popd & exit /b 1))
call npm run build || (popd & exit /b 1)
popd
if exist "backend\app\static" rmdir /s /q "backend\app\static"
xcopy /e /i /q /y "frontend\dist" "backend\app\static" >nul || exit /b 1
if exist "backend\.venv\Scripts\python.exe" "backend\.venv\Scripts\python.exe" "scripts\prestart.py" --write-stamp
echo Frontend built into backend\app\static
exit /b 0
```

`scripts\local.env.cmd.example`：

```bat
rem Copy this file to scripts\local.env.cmd and edit it. local.env.cmd is not committed.
rem Python 3.13 used to create backend\.venv (this machine: Miniconda base)
set "WENSHU_PYTHON=C:\Python313\python.exe"
rem Uncomment to share data with the packaged exe, or to keep data somewhere else
rem set "WENSHU_DATA_DIR=D:\Apps\WenShu\data"
```

**数据目录**：源码版默认用项目根目录的 `data`，打包版默认用 exe 旁边的 `data`，两者互不影响，也可以同时运行。想共用数据，在 `local.env.cmd` 里把 `WENSHU_DATA_DIR` 指向同一个文件夹；这时同一时间只能运行其中一个（单实例按数据目录判断，第 5.1 节）。

## 6. PyInstaller 配置

`packaging/wenshu.spec`：

```python
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"

a = Analysis(
    [str(ROOT / "packaging" / "wenshu_main.py")],     # 只有一行：from app.launcher.entry import main; main()
    pathex=[str(BACKEND)],
    datas=[
        (str(BACKEND / "app" / "static"), "app/static"),
        (str(BACKEND / "app" / "db" / "migrations"), "app/db/migrations"),
        (str(BACKEND / "app" / "vendor" / "swagger-ui"), "app/vendor/swagger-ui"),
        (str(ROOT / "packaging" / "icon.ico"), "."),
    ],
    hiddenimports=[
        "aiosqlite",
        "sqlalchemy.dialects.sqlite.aiosqlite",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan.on",
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
```

- **入口**：用 `packaging/wenshu_main.py`，不直接用 `app/launcher/entry.py`。PyInstaller 把入口当作顶层脚本运行，它没有父包，里面的相对导入会在打包后才报错，源码版用 `-m app.launcher` 时却正常，问题要到打包才暴露；
- **目录模式**（onedir）：产物是 `build/dist/WenShu/WenShu.exe` 加 `_internal/` 目录，`build.bat` 再同步到 `release/WenShu`（第 4 节）。不用单文件模式：单文件每次启动都要解压到临时目录，慢好几秒，也更容易被杀毒软件误报；
- 不开 UPX 压缩，原因同上；
- 运行时 `sys._MEIPASS` 指向 `_internal`，静态文件和迁移文件的位置与 02 第 9.1 节一致；
- 打包后若运行时报找不到某个模块（常见于带编译扩展的包），在 `hiddenimports` 里补上，或对该包使用 `collect_all`，并把原因写进注释。

## 7. 发布与升级

| 事项 | 做法 |
|---|---|
| 发布物 | `release/WenShu.zip`，内容是 `WenShu` 文件夹，不含 `data` |
| 安装 | 解压到任意可写目录（例如 `D:\Apps\WenShu`），不要放进 `C:\Program Files`（不可写时数据会落到 `%LOCALAPPDATA%\WenShu\data`，迁移时容易遗漏）。需要的话给 `WenShu.exe` 建桌面快捷方式 |
| 升级 | 从托盘退出 → 把新版本的 zip 解压覆盖到原文件夹（`data` 不受影响）→ 重新打开。数据库升级由迁移自动完成 |
| 备份 | 退出程序后复制整个 `data` 文件夹 |
| 迁移到另一台电脑 | 退出程序，拷走整个 `WenShu` 文件夹（含 `data`）。`secret.key` 随之一起走，已保存的 API Key 仍然可用 |
| 源码版更新 | 替换或拉取新源码后照常双击 `启动文枢.bat`：后端依赖、前端源码有变化时会自动重新安装和构建。打包版不会跟着变，需要重新运行 `build.bat` |
| 在开发机上重新打包 | 先从托盘退出 `release\WenShu` 里正在运行的文枢，再运行 `build.bat`。`release\WenShu\data` 会保留，任务和已保存的 API Key 都还在 |

## 8. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 双击没有反应 | 查看 `data\logs\app.log`。常见原因：数据目录没有写权限（放在了 Program Files 下），换个目录 |
| 窗口打开但一片空白 | 前端产物没有复制进去（构建第 3 步失败），重新构建 |
| 再次双击提示“已在运行但没有响应” | 后台进程卡住：任务管理器里结束 `WenShu.exe`，再打开 |
| 没有弹出独立窗口，而是打开了默认浏览器 | 没找到 Edge 或 Chrome。可以在设置里把打开方式改为“默认浏览器” |
| pip 装不上刚发布的版本 | 华为云镜像同步有延迟，见第 2.1 节 |
| 连接公司内网模型报证书错误 | 先把网关的根证书安装到 Windows“受信任的根证书颁发机构”；仍不行再在模型配置里关闭“校验证书” |
| 杀毒软件误报 | 把程序目录加入白名单；不要改成单文件模式或开启 UPX |
| 双击 `启动文枢.bat` 提示找不到 Python 3.13 | 复制 `scripts\local.env.cmd.example` 为 `scripts\local.env.cmd`，填上 Python 路径（本机是 `C:\Python313\python.exe`） |
| 源码版第一次启动很慢 | 正在安装后端依赖和构建前端，窗口里能看到进度。只有第一次、以及依赖或前端源码变化后才需要 |
| 源码版提示需要 Node.js | 第一次启动、或前端源码变化后需要 Node.js 24 构建界面；装好后再双击 |
| 源码版和打包版的任务不一样 | 两者默认用不同的数据目录，见第 5.5 节“数据目录” |

## 9. 发布前检查清单

### 9.1 源码版（在开发机上）

- [ ] 删除 `backend\.venv` 和 `backend\app\static` 后双击 `启动文枢.bat`：自动创建环境、安装依赖、构建前端，然后弹出独立窗口
- [ ] 不做任何修改再次双击：5 秒内打开，不重新安装、不重新构建，没有残留的命令行窗口
- [ ] 改一个前端源文件（例如一句文案）后双击：自动重新构建，界面里能看到修改
- [ ] 在 `backend\requirements.txt` 里调整一个依赖后双击：自动重新安装
- [ ] 源码版和打包版同时运行：各自使用自己的数据目录和端口，互不影响；设置页显示的运行方式分别为“源码版”和“打包版”
- [ ] 前后端分离：后端单独运行（`uvicorn`），`/docs` 可用，`GET /` 在没有前端构建产物时返回说明文字；前端用 `VITE_API_BASE=http://127.0.0.1:18765` 构建并用 `npm run preview` 打开，后端设置 `WENSHU_CORS_ORIGINS=http://127.0.0.1:4173`，界面功能正常
- [ ] 根目录、`backend`、`frontend` 的 README 按 08 第 8 节检查过，照着 README 能从零跑起来

### 9.2 打包版（在 Windows 沙盒或另一台没有 Python、Node 的电脑上）

Windows 沙盒是 Windows 专业版和企业版自带的功能。

- [ ] `scripts\build.bat` 全部步骤通过，包括测试和自检
- [ ] 在开发机上用 `release\WenShu\WenShu.exe` 建一个任务、接入一个模型，退出后再运行一次 `build.bat`：任务和模型（含 API Key）都还在
- [ ] 解压 `WenShu.zip`：里面没有 `data`、`data-selftest` 文件夹
- [ ] 双击 `WenShu.exe`：5 秒内弹出独立窗口，全程没有黑色命令行窗口
- [ ] 界面开着时从托盘退出：3 秒内进程消失（任务管理器里看不到 `WenShu.exe`）
- [ ] 再次双击：没有启动第二个后端，界面直接打开
- [ ] 关闭界面窗口：托盘弹出一次提示；从托盘“打开文枢”能重新打开
- [ ] 先用其他程序占住 18765 端口再启动：自动换端口，界面正常
- [ ] 用演示模型跑完一个 100 条的意图识别任务，导出的 xlsx 用 Excel 打开正常
- [ ] 任务运行中从托盘退出，再打开：任务为“已暂停”，原因“程序退出时任务未完成，可以继续”；点继续后完成
- [ ] 断开网络后打开：界面和字体显示正常
- [ ] 设置里把打开方式改为“默认浏览器”，重启后生效
- [ ] 用文本编辑器在 `data` 目录里搜索接入模型时用过的 API Key 片段，搜不到
- [ ] 解压到带中文和空格的路径（如 `D:\我的 工具\文枢`）也能正常运行
- [ ] exe 文件属性、设置页、`/api/health` 显示的版本号一致

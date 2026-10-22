"""PyInstaller 的入口脚本（07 第 6 节）：只调用启动器的 main()，退出码原样交给系统。

不直接用 app/launcher/entry.py 做入口：PyInstaller 把入口当作没有父包的顶层脚本运行，
包内的相对导入要到打包后才报错。build.bat 用 start "" /wait WenShu.exe --selftest 读取退出码，
所以这里用 SystemExit 把 main() 的返回值传出去。
"""

from app.launcher.entry import main

raise SystemExit(main())

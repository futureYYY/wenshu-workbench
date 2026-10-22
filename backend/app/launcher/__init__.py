"""启动器：打包版（WenShu.exe）和源码版（python -m app.launcher）共用的启动流程（07 第 5 节）。

两个入口都只调用 entry.main()：打包版是 packaging/wenshu_main.py，源码版是本包的 __main__.py。
本包只用绝对导入（from app.launcher import …）。开发模式（scripts\\dev.bat）直接运行 uvicorn，不经过这里。
"""

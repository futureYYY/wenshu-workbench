"""源码版入口：python -m app.launcher（启动文枢.bat 用 pythonw.exe 调用，工作目录为 backend）。"""

import sys

from app.launcher.entry import main

if __name__ == "__main__":
    sys.exit(main())

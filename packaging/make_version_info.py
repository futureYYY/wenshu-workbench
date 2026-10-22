"""生成 packaging/version_info.txt：WenShu.exe 文件属性里的版本信息（07 第 4 节）。

版本号只有一个来源：backend/app/__init__.py 的 __version__。这里用正则读取，不导入后端代码。
运行：backend\\.venv\\Scripts\\python.exe packaging\\make_version_info.py（build.bat 第 4 步）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INIT_FILE = HERE.parent / "backend" / "app" / "__init__.py"
OUT_FILE = HERE / "version_info.txt"

TEMPLATE = """# UTF-8
# 由 packaging/make_version_info.py 生成，不要手改，也不提交
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', '{app_id}'),
         StringStruct('FileDescription', '{app_name}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', '{app_id}'),
         StringStruct('LegalCopyright', ''),
         StringStruct('OriginalFilename', '{app_id}.exe'),
         StringStruct('ProductName', '{app_name}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def read_constant(text: str, name: str) -> str:
    match = re.search(rf"^{name}\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"在 {INIT_FILE} 里没有找到 {name}")
    return match.group(1)


def version_numbers(version: str) -> tuple[int, int, int, int]:
    """'1.2.3' → (1, 2, 3, 0)；每段只取开头的数字（'0rc1' → 0）。"""
    parts: list[int] = []
    for piece in version.split(".")[:4]:
        digits = re.match(r"\d+", piece)
        parts.append(int(digits.group(0)) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def main() -> int:
    text = INIT_FILE.read_text(encoding="utf-8")
    version = read_constant(text, "__version__")
    content = TEMPLATE.format(
        numbers=version_numbers(version),
        version=version,
        app_id=read_constant(text, "APP_ID"),
        app_name=read_constant(text, "APP_NAME"),
    )
    OUT_FILE.write_text(content, encoding="utf-8")
    print(f"已生成 {OUT_FILE}（版本 {version}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

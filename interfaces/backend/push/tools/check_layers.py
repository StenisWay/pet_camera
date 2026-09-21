#!/usr/bin/env python3
"""檢查 Clean Architecture 分層依賴是否被破壞。

用法:
    python check_layers.py [--root 專案根目錄] [--package app]

預期結構:
    app/shared_kernel/          純 Python 共用核心（錯誤分類、值物件、共用 port）
    app/core/                   框架與基礎設施（config、database、http 錯誤轉換、security）
    app/domains/<d>/domain/
    app/domains/<d>/application/
    app/domains/<d>/infrastructure/
    app/domains/<d>/presentation/
    app/domains/<d>/api.py      （選用）對其他領域公開的唯一入口

規則:
    1. 同領域內依賴只能由外向內：
       domain          → domain
       application     → domain, application
       infrastructure  → domain, application, infrastructure
       presentation    → domain, application, infrastructure, presentation
       api             → domain, application, infrastructure
    2. domain、application、shared_kernel 不可 import 框架（FastAPI、SQLAlchemy、Pydantic…）
       也不可 import app.core；只能 import app.shared_kernel。
    3. infrastructure 不可 import FastAPI / Starlette（HTTP 屬於 presentation）。
    4. 跨領域只能 import 對方的 `api` 模組，而且只能在 infrastructure 層（adapter）中。
    5. shared_kernel 不可 import app 內其他套件。

結束碼：有違規為 1，否則為 0。可放進 pytest 或 CI。
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

LAYERS = ("domain", "application", "infrastructure", "presentation", "api")
ALLOWED_SAME_DOMAIN = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "infrastructure": {"domain", "application", "infrastructure"},
    "presentation": {"domain", "application", "infrastructure", "presentation"},
    "api": {"domain", "application", "infrastructure", "api"},
}
FRAMEWORKS = {
    "fastapi", "starlette", "sqlalchemy", "pydantic", "pydantic_settings",
    "alembic", "asyncpg", "psycopg", "psycopg2", "httpx", "requests", "redis", "celery",
}
HTTP_FRAMEWORKS = {"fastapi", "starlette"}
PURE_LAYERS = {"domain", "application"}


@dataclass
class Location:
    kind: str  # "domain_layer" | "shared_kernel" | "core" | "other"
    domain: str | None = None
    layer: str | None = None


@dataclass
class Violation:
    path: Path
    line: int
    message: str


def locate(parts: tuple[str, ...], pkg: str) -> Location:
    """parts 為模組路徑（不含 .py），例如 ('app','domains','orders','domain','entities')。"""
    if len(parts) < 2 or parts[0] != pkg:
        return Location("external")
    if parts[1] == "shared_kernel":
        return Location("shared_kernel")
    if parts[1] == "core":
        return Location("core")
    if parts[1] == "domains" and len(parts) >= 3:
        domain = parts[2]
        if len(parts) >= 4 and parts[3] in LAYERS:
            return Location("domain_layer", domain, parts[3])
        return Location("domain_layer", domain, None)  # 領域根目錄（__init__ 等）
    return Location("other")


def module_parts(file: Path, root: Path) -> tuple[str, ...]:
    rel = file.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return parts


def resolve_imports(node: ast.AST, current: tuple[str, ...], is_pkg: bool) -> list[tuple[str, ...]]:
    if isinstance(node, ast.Import):
        return [tuple(a.name.split(".")) for a in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level == 0:
            base = tuple((node.module or "").split("."))
        else:
            pkg = current if is_pkg else current[:-1]
            up = node.level - 1
            base = pkg[: len(pkg) - up] if up else pkg
            if node.module:
                base = base + tuple(node.module.split("."))
        # `from app.domains.orders import domain` 這類寫法：把名稱接上以便判斷層級
        results = []
        for a in node.names:
            results.append(base + (a.name,) if a.name != "*" else base)
        return results
    return []


def check_file(file: Path, root: Path, pkg: str) -> list[Violation]:
    parts = module_parts(file, root)
    here = locate(parts, pkg)
    if here.kind not in {"domain_layer", "shared_kernel"}:
        return []
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [Violation(file, e.lineno or 1, f"無法解析：{e.msg}")]

    out: list[Violation] = []
    is_pkg = file.name == "__init__.py"
    for node in ast.walk(tree):
        for target in resolve_imports(node, parts, is_pkg):
            if not target or not target[0]:
                continue
            top = target[0]
            there = locate(target, pkg)
            line = getattr(node, "lineno", 1)
            where = ".".join(target)

            if here.kind == "shared_kernel":
                if top in FRAMEWORKS:
                    out.append(Violation(file, line, f"shared_kernel 不可依賴框架 `{top}`"))
                elif top == pkg and there.kind != "shared_kernel":
                    out.append(Violation(file, line, f"shared_kernel 不可 import `{where}`"))
                continue

            layer = here.layer
            if layer is None:
                continue

            # 規則 2、3：框架依賴
            if layer in PURE_LAYERS and top in FRAMEWORKS:
                out.append(Violation(file, line, f"{layer} 層不可依賴框架 `{top}`"))
                continue
            if layer == "infrastructure" and top in HTTP_FRAMEWORKS:
                out.append(Violation(file, line, f"infrastructure 層不可依賴 HTTP 框架 `{top}`（屬於 presentation）"))
                continue
            if top != pkg:
                continue

            if there.kind == "core" and layer in PURE_LAYERS:
                out.append(Violation(file, line, f"{layer} 層不可 import app.core（`{where}`）；需要的抽象請放 shared_kernel"))
                continue
            if there.kind != "domain_layer":
                continue

            if there.domain == here.domain:
                # 規則 1：同領域由外向內
                if there.layer is not None and there.layer not in ALLOWED_SAME_DOMAIN[layer]:
                    out.append(Violation(file, line, f"{layer} 層不可依賴外層 {there.layer}（`{where}`）"))
            else:
                # 規則 4：跨領域只能經由 api，且只能在 infrastructure
                if there.layer != "api":
                    out.append(Violation(
                        file, line,
                        f"跨領域依賴 `{where}`：只能 import app.domains.{there.domain}.api",
                    ))
                elif layer != "infrastructure":
                    out.append(Violation(
                        file, line,
                        f"{layer} 層不可直接使用其他領域；請在 application 定義 port，於 infrastructure 寫 adapter 呼叫 {there.domain}.api",
                    ))
    return out


def run(root: Path, pkg: str) -> list[Violation]:
    base = root / pkg
    if not base.is_dir():
        raise SystemExit(f"找不到套件目錄：{base}")
    violations: list[Violation] = []
    for file in sorted(base.rglob("*.py")):
        violations += check_file(file, root, pkg)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="專案根目錄（包含 app/ 的目錄）")
    parser.add_argument("--package", default="app", help="頂層套件名稱，預設 app")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations = run(root, args.package)
    for v in violations:
        print(f"❌ {v.path.relative_to(root)}:{v.line}  {v.message}")
    if violations:
        print(f"\n共 {len(violations)} 個分層違規")
        return 1
    print("✅ 分層依賴檢查通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())

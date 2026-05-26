#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码探索工具 - 提供给 Agent 使用的项目代码理解工具。

设计理念（参考 Codex CLI 的 code-mode + connectors crate）：
- analyze_project: 快速识别项目类型和模块骨架（替代纯目录树）
- find_symbols: 按需搜索类/函数/接口定义位置
- trace_imports: 追踪某个文件/模块的导入依赖关系
"""
import os
import re
import ast
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


# ============================================================
# 共享常量
# ============================================================

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "target", "vendor",
                ".venv", "venv", "build", "dist", ".idea", ".qoze"}

PROJECT_SIGNATURES = {
    "rust": {"files": ["Cargo.toml"], "exts": [".rs"]},
    "python": {"files": ["pyproject.toml", "setup.py", "requirements.txt"], "exts": [".py"]},
    "typescript": {"files": ["package.json", "tsconfig.json"], "exts": [".ts", ".tsx"]},
    "javascript": {"files": ["package.json"], "exts": [".js", ".jsx"]},
    "java_maven": {"files": ["pom.xml"], "exts": [".java"]},
    "java_gradle": {"files": ["build.gradle", "build.gradle.kts"], "exts": [".java"]},
    "go": {"files": ["go.mod"], "exts": [".go"]},
    "c_cpp": {"files": ["CMakeLists.txt", "Makefile"], "exts": [".c", ".cpp", ".h", ".hpp"]},
}

DIR_ROLE_MAP = {
    "src": "源代码", "tests": "测试", "test": "测试", "__tests__": "测试",
    "docs": "文档", "doc": "文档", "scripts": "脚本", "script": "脚本",
    "tools": "工具", "utils": "工具函数", "lib": "库代码",
    "config": "配置", "configs": "配置",
    "assets": "静态资源", "static": "静态资源", "public": "公共资源",
    "api": "API/路由层", "routes": "路由定义", "handlers": "处理器",
    "services": "业务服务层", "service": "服务层",
    "models": "数据模型", "model": "模型", "entities": "实体",
    "repositories": "数据访问层", "repository": "数据访问", "dao": "数据访问",
    "controllers": "控制器层", "controller": "控制器",
    "middlewares": "中间件", "middleware": "中间件",
    "schemas": "数据模式/校验", "dto": "数据传输对象",
    "migrations": "数据库迁移",
    "cmd": "命令入口", "internal": "内部包", "pkg": "公共包",
}


# ============================================================
# 项目分析工具
# ============================================================

def _detect_lang(root: Path) -> tuple[str, list[str], list[str]]:
    """检测项目类型，返回 (语言, 特征文件列表, 源文件扩展名列表)"""
    root_files = {f.name for f in root.iterdir() if f.is_file()}
    
    for lang, sig in PROJECT_SIGNATURES.items():
        if all(f in root_files for f in sig["files"]):
            return lang, [f for f in sig["files"] if f in root_files], sig["exts"]
    
    return "unknown", [], [".py"]


def _count_src_files(root: Path, exts: list[str]) -> dict[str, int]:
    """统计各级目录下的源文件数量"""
    counts = {}
    exclude = EXCLUDE_DIRS
    
    for item in root.iterdir():
        if item.name.startswith(".") and item.name not in (".github",):
            continue
        if item.name in exclude:
            continue
        if item.is_dir():
            count = 0
            for f in item.rglob("*"):
                if f.suffix in exts and not any(p in exclude for p in f.parts):
                    count += 1
            if count > 0:
                counts[item.name] = count
        elif item.is_file() and item.suffix in exts:
            counts[item.name] = 1
    
    return counts


@tool
def analyze_project() -> str:
    """
    分析当前项目的代码结构，返回项目类型、关键入口文件和模块分层。

    当 Agent 首次进入项目或对项目结构不熟悉时优先调用此工具，
    而不是使用 `execute_command ls` 逐个探索目录。

    Returns:
        格式化的项目结构报告：项目类型、构建系统、入口文件、模块分层。
    """
    try:
        root = Path.cwd()
        lang, key_files, exts = _detect_lang(root)
        
        lines = [f"## 🗺️ 项目代码地图\n", f"- **项目类型**: {lang}"]

        # 关键文件
        if key_files:
            lines.append(f"- **关键配置**: `{'`, `'.join(key_files)}`")
        
        # 入口文件
        entries = _find_entries(root, lang, exts)
        if entries:
            lines.append(f"- **入口文件**: `{'`, `'.join(entries[:6])}`")
        
        # 模块结构（一级目录 + 源文件计数）
        src_counts = _count_src_files(root, exts)
        if src_counts:
            lines.append(f"\n### 模块结构\n")
            # 目录在前，文件在后
            dirs = [(n, c) for n, c in src_counts.items() if (root / n).is_dir()]
            files = [(n, c) for n, c in src_counts.items() if (root / n).is_file()]
            
            for name, count in sorted(dirs, key=lambda x: -x[1]):
                role = DIR_ROLE_MAP.get(name, "模块")
                lines.append(f"- `{name}/` — {role} ({count} 源文件)")
            for name, count in files:
                lines.append(f"- `{name}` ({count} 行)")
        
        # 检测特殊特征
        features = _detect_features(root, lang)
        if features:
            lines.append(f"\n### 检测到的技术特征")
            for f in features:
                lines.append(f"- {f}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"项目分析失败: {e}"


def _find_entries(root: Path, lang: str, exts: list[str]) -> list[str]:
    """查找入口文件"""
    entry_patterns = {
        "python": ["main.py", "app.py", "manage.py", "**/cli.py"],
        "rust": ["src/main.rs", "**/main.rs"],
        "typescript": ["src/index.ts", "src/index.tsx", "src/main.ts"],
        "java_maven": ["src/main/java/**/Application.java", "src/main/java/**/*App.java"],
        "go": ["cmd/**/main.go", "main.go"],
    }
    
    patterns = entry_patterns.get(lang, [])
    entries = []
    for pat in patterns:
        for match in root.glob(pat):
            try:
                entries.append(str(match.relative_to(root)))
            except ValueError:
                entries.append(str(match))
    return entries[:8]


def _detect_features(root: Path, lang: str) -> list[str]:
    """检测项目的技术特征（ORM、RPC、测试框架等）"""
    features = []
    
    if lang == "python" and (root / "pyproject.toml").exists():
        content = (root / "pyproject.toml").read_text(errors="replace")
        if "fastapi" in content: features.append("🌐 Web 框架: FastAPI")
        if "django" in content: features.append("🌐 Web 框架: Django")
        if "flask" in content: features.append("🌐 Web 框架: Flask")
        if "sqlalchemy" in content: features.append("🗄️ ORM: SQLAlchemy")
        if "pydantic" in content: features.append("✅ 数据校验: Pydantic")
        if "pytest" in content: features.append("🧪 测试: pytest")
        if "celery" in content: features.append("📦 任务队列: Celery")
        if "grpc" in content: features.append("🔌 RPC: gRPC")
    
    if lang == "rust" and (root / "Cargo.toml").exists():
        content = (root / "Cargo.toml").read_text(errors="replace")
        if "tokio" in content: features.append("⚡ 异步: Tokio")
        if "rusqlite" in content: features.append("🗄️ 数据库: SQLite (rusqlite)")
        if "sqlx" in content: features.append("🗄️ 数据库: sqlx")
        if "serde" in content: features.append("📦 序列化: Serde")
        if "tonic" in content or "prost" in content: features.append("🔌 RPC: gRPC (tonic/prost)")
        if "ratatui" in content: features.append("🖥️ TUI: Ratatui")
        if "clap" in content: features.append("💻 CLI: Clap")
    
    if lang in ("typescript", "javascript") and (root / "package.json").exists():
        content = (root / "package.json").read_text(errors="replace")
        if "next" in content: features.append("🌐 框架: Next.js")
        if "react" in content: features.append("⚛️ UI: React")
        if "vue" in content: features.append("💚 UI: Vue")
        if "prisma" in content: features.append("🗄️ ORM: Prisma")
        if "jest" in content: features.append("🧪 测试: Jest")
        if "express" in content: features.append("🌐 框架: Express")
        if "nest" in content: features.append("🌐 框架: NestJS")
    
    if lang == "go" and (root / "go.mod").exists():
        content = (root / "go.mod").read_text(errors="replace")
        if "gin-gonic" in content: features.append("🌐 Web: Gin")
        if "echo" in content: features.append("🌐 Web: Echo")
        if "gorm" in content: features.append("🗄️ ORM: GORM")
        if "grpc" in content: features.append("🔌 RPC: gRPC")
    
    return features


# ============================================================
# 符号搜索工具
# ============================================================

_SYMBOL_PATTERNS = {
    "python": [
        (r"^class\s+(\w+)", "class"),
        (r"^async\s+def\s+(\w+)", "async_fn"),
        (r"^def\s+(\w+)", "function"),
    ],
    "rust": [
        (r"^pub\s+(?:async\s+)?fn\s+(\w+)", "pub_fn"),
        (r"^pub\s+struct\s+(\w+)", "pub_struct"),
        (r"^pub\s+enum\s+(\w+)", "pub_enum"),
        (r"^pub\s+trait\s+(\w+)", "pub_trait"),
    ],
    "typescript": [
        (r"export\s+(?:async\s+)?function\s+(\w+)", "export_fn"),
        (r"export\s+class\s+(\w+)", "export_class"),
        (r"export\s+interface\s+(\w+)", "export_interface"),
        (r"export\s+const\s+(\w+)", "export_const"),
    ],
    "javascript": [
        (r"function\s+(\w+)", "function"),
        (r"class\s+(\w+)", "class"),
        (r"const\s+(\w+)\s*=\s*(?:async\s*)?\(.*\)\s*=>", "arrow_fn"),
    ],
    "java_maven": [
        (r"(?:public|private|protected)\s+class\s+(\w+)", "class"),
        (r"@RestController\n(?:public\s+)?class\s+(\w+)", "controller"),
        (r"@Service\n(?:public\s+)?class\s+(\w+)", "service"),
        (r"@Repository\n(?:public\s+)?(?:interface|class)\s+(\w+)", "repository"),
    ],
    "go": [
        (r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", "func"),
        (r"^type\s+(\w+)\s+struct", "struct"),
        (r"^type\s+(\w+)\s+interface", "interface"),
    ],
}


@tool
def find_symbols(keyword: str = "", symbol_type: str = "all", max_results: int = 60) -> str:
    """
    在项目中搜索符号定义（类、函数、接口等）。

    使用场景：
    - "这个项目的入口函数在哪？" → find_symbols(keyword="main")
    - "有哪些 Service 类？" → find_symbols(symbol_type="service")（仅 Java 项目）
    - "列出所有 async 函数" → find_symbols(symbol_type="async_fn")（仅 Python 项目）

    Args:
        keyword: 过滤符号名称（大小写不敏感），留空则返回所有符号
        symbol_type: 符号类型过滤。可选值取决于项目语言：
                     Python: "class", "function", "async_fn"
                     Rust: "pub_fn", "pub_struct", "pub_enum", "pub_trait"
                     TypeScript: "export_fn", "export_class", "export_interface"
                     Java: "class", "controller", "service", "repository"
                     默认 "all" 返回全部
        max_results: 最大返回数量（默认 60）

    Returns:
        符号列表（表格格式）：文件路径 | 行号 | 类型 | 名称
    """
    try:
        root = Path.cwd()
        lang, _, exts = _detect_lang(root)
        patterns = _SYMBOL_PATTERNS.get(lang, _SYMBOL_PATTERNS["python"])
        
        # 如果 symbol_type 给定了，只保留匹配的 pattern
        if symbol_type != "all":
            patterns = [(p, k) for p, k in patterns if k == symbol_type]
            if not patterns:
                available = ", ".join(set(k for _, k in _SYMBOL_PATTERNS.get(lang, [])))
                return f"未知符号类型 '{symbol_type}'。可用类型: {available}"
        
        keyword_lower = keyword.lower() if keyword else ""
        
        symbols = []
        for file_path in root.rglob("*"):
            if file_path.suffix not in exts:
                continue
            if any(p in EXCLUDE_DIRS for p in file_path.parts):
                continue
            if file_path.name.startswith("."):
                continue
            
            try:
                content = file_path.read_text(errors="replace")
            except Exception:
                continue
            
            try:
                rel = str(file_path.relative_to(root))
            except ValueError:
                rel = str(file_path)
            
            for line_no, line in enumerate(content.split("\n"), 1):
                for pattern, kind in patterns:
                    match = re.match(pattern, line.strip())
                    if match:
                        name = match.group(1)
                        if keyword_lower and keyword_lower not in name.lower():
                            continue
                        symbols.append((rel, line_no, kind, name))
                        if len(symbols) >= max_results:
                            break
                if len(symbols) >= max_results:
                    break
            if len(symbols) >= max_results:
                break
        
        if not symbols:
            hint = f"（关键词: '{keyword}'）" if keyword else ""
            return f"未找到匹配的符号定义{hint}。"
        
        # 格式化为紧凑表格
        lines = [f"## 🔍 符号索引 ({lang}, {len(symbols)} 条)\n"]
        lines.append("| 文件 | 行 | 类型 | 名称 |")
        lines.append("|------|-----|------|------|")
        for path, line, kind, name in symbols[:max_results]:
            # 截断长路径
            if len(path) > 40:
                path = "..." + path[-37:]
            lines.append(f"| `{path}` | {line} | `{kind}` | `{name}` |")
        
        return "\n".join(lines)
    except Exception as e:
        return f"符号搜索失败: {e}"


# ============================================================
# Import 追踪工具（Python 专用，利用 AST）
# ============================================================

@tool
def trace_imports(file_path: str) -> str:
    """
    分析指定 Python 文件的导入依赖关系。

    通过 AST 解析 import 语句，列出该文件导入的所有模块和符号，
    并标注哪些是项目内部模块（同仓库内），哪些是第三方库。

    Args:
        file_path: 要分析的 Python 文件路径（相对于当前目录）

    Returns:
        导入列表：内部导入和第三方导入分开列出。
    """
    try:
        root = Path.cwd()
        target = (root / file_path).resolve()
        
        if not target.exists():
            return f"文件不存在: {file_path}"
        if not target.suffix == ".py":
            return f"仅支持 Python 文件: {file_path}"
        
        content = target.read_text(errors="replace")
        tree = ast.parse(content)
        
        internal = []
        external = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    _classify_import(name, root, internal, external)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    _classify_import(name, root, internal, external)
        
        lines = [f"## 📦 `{file_path}` 的导入依赖\n"]
        if internal:
            lines.append(f"### 项目内部模块 ({len(internal)} 个)\n" + "\n".join(f"- `{m}`" for m in sorted(set(internal))))
        if external:
            lines.append(f"\n### 第三方/标准库 ({len(external)} 个)\n" + "\n".join(f"- `{m}`" for m in sorted(set(external))))
        
        return "\n".join(lines) if (internal or external) else "未检测到 import 语句。"
    except SyntaxError as e:
        return f"Python 语法错误，无法解析: {e}"
    except Exception as e:
        return f"导入分析失败: {e}"


def _classify_import(module_name: str, project_root: Path, internal: list, external: list):
    """判断导入是项目内部还是外部"""
    # 检查是否是项目内部模块
    project_packages = set()
    for d in project_root.iterdir():
        if d.is_dir() and not d.name.startswith(".") and d.name not in EXCLUDE_DIRS:
            project_packages.add(d.name.replace("-", "_"))
        elif d.is_file() and d.suffix == ".py" and not d.name.startswith("."):
            project_packages.add(d.stem.replace("-", "_"))
    
    top_level = module_name.split(".")[0]
    if top_level in project_packages or top_level in project_packages:
        internal.append(module_name)
    else:
        external.append(module_name)

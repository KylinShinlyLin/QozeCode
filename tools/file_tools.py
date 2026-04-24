import os
import fnmatch
from pathlib import Path
from typing import Iterable, List

from langchain_core.tools import tool

from utils.directory_config import EXCLUDE_DIRECTORIES


def _is_path_within_base(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve_under_cwd(path: str) -> Path:
    base = Path.cwd().resolve()
    target = Path(path)
    if not target.is_absolute():
        target = (base / target).resolve()
    else:
        target = target.resolve()
    if not _is_path_within_base(base, target):
        raise ValueError("Path must be within current working directory.")
    return target


def _is_excluded(name: str) -> bool:
    for pattern in EXCLUDE_DIRECTORIES:
        if pattern == name:
            return True
        if "*" in pattern and fnmatch.fnmatch(name, pattern):
            return True
    return False


def _iter_files(directory: Path, include_hidden: bool) -> Iterable[Path]:
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)

        # Filter directories in-place for os.walk
        filtered_dirs = []
        for d in dirs:
            if _is_excluded(d):
                continue
            if not include_hidden and d.startswith("."):
                continue
            filtered_dirs.append(d)
        dirs[:] = filtered_dirs

        for f in files:
            if _is_excluded(f):
                continue
            if not include_hidden and f.startswith("."):
                continue
            yield root_path / f


@tool
def read_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """Read a file by line range with safe limits.

    Args:
        path: File path (relative to current working directory or absolute).
        start_line: 1-based start line (inclusive).
        end_line: 1-based end line (inclusive).

    Returns:
        The requested file content with line numbers or an error message.
    """
    try:
        if start_line < 1 or end_line < start_line:
            return "Error: Invalid line range."

        target = _resolve_under_cwd(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        if not target.is_file():
            return f"Error: Path is not a file: {path}"

        lines: List[str] = []
        with target.open("r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f, start=1):
                if idx < start_line:
                    continue
                if idx > end_line:
                    break
                lines.append(f"{idx:6d}: {line.rstrip()}")

        if not lines:
            return "Warning: No content in the specified range."

        header = f"[READ_FILE] {target}"
        return header + "\n" + "\n".join(lines)
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def cat_file(paths: str | list[str] | None = None) -> str:
    """Return full file content (cat-like) for text files only.

    Args:
        paths: A single file path or a list of file paths (relative to cwd or absolute).

    Returns:
        Concatenated file contents or an error message.
    """
    try:
        if paths is None:
            return "Error: paths must be a non-empty string or list of strings."
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not paths:
            return "Error: paths must be a non-empty string or list of strings."

        outputs = []
        for path in paths:
            target = _resolve_under_cwd(path)
            if not target.exists():
                outputs.append(f"Error: File not found: {path}")
                continue
            if not target.is_file():
                outputs.append(f"Error: Path is not a file: {path}")
                continue

            # 跳过二进制文件
            with target.open("rb") as f:
                sample = f.read(4096)
                if b"\x00" in sample:
                    outputs.append(f"Error: Binary file detected (skipped): {path}")
                    continue

            with target.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            header = f"[CAT_FILE] {target}"
            outputs.append(header + "\n" + content)

        return "\n\n".join(outputs) if outputs else "No readable files."
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def list_files(directory: str = ".", pattern: str = "*", max_results: int = 200, include_hidden: bool = False) -> str:
    """List files under a directory with optional glob filtering.

    Args:
        directory: Directory to scan (relative to cwd or absolute).
        pattern: Glob pattern to filter files (e.g., "*.py", "*test*").
        max_results: Maximum number of files to return.
        include_hidden: Include hidden files and directories.

    Returns:
        A list of matching files (relative to cwd) or an error message.
    """
    try:
        target_dir = _resolve_under_cwd(directory)
        if not target_dir.exists():
            return f"Error: Directory not found: {directory}"
        if not target_dir.is_dir():
            return f"Error: Path is not a directory: {directory}"

        base = Path.cwd().resolve()
        matches: List[str] = []

        for file_path in _iter_files(target_dir, include_hidden):
            rel_path = str(file_path.resolve().relative_to(base))
            if pattern and not fnmatch.fnmatch(file_path.name, pattern) and not fnmatch.fnmatch(rel_path, pattern):
                continue
            matches.append(rel_path)
            if len(matches) >= max_results:
                break

        if not matches:
            return "No files matched."

        result = "\n".join(matches)
        if len(matches) >= max_results:
            result += f"\n... (truncated, max_results={max_results})"
        return result
    except Exception as e:
        return f"Error listing files: {str(e)}"


@tool
def list_dir(directory: str = ".", include_hidden: bool = False, max_results: int = 200) -> str:
    """List items in a directory (ls-like).

    Args:
        directory: Directory to list (relative to cwd or absolute).
        include_hidden: Include hidden entries.
        max_results: Maximum number of entries to return.

    Returns:
        A list of directory entries or an error message.
    """
    try:
        target_dir = _resolve_under_cwd(directory)
        if not target_dir.exists():
            return f"Error: Directory not found: {directory}"
        if not target_dir.is_dir():
            return f"Error: Path is not a directory: {directory}"

        entries = []
        for item in sorted(target_dir.iterdir(), key=lambda p: p.name.lower()):
            name = item.name
            if not include_hidden and name.startswith("."):
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(name + suffix)
            if len(entries) >= max_results:
                break

        if not entries:
            return "No entries found."
        output = "\n".join(entries)
        if len(entries) >= max_results:
            output += f"\n... (truncated, max_results={max_results})"
        header = f"[LIST_DIR] {target_dir}"
        return header + "\n" + output
    except Exception as e:
        return f"Error listing directory: {str(e)}"


@tool
def find_files(
        directory: str = ".",
        pattern: str = "*",
        max_depth: int = 6,
        file_type: str = "all",
        include_hidden: bool = False,
        max_results: int = 200,
) -> str:
    """Find files/dirs under a directory (find-like).

    Args:
        directory: Directory to search (relative to cwd or absolute).
        pattern: Glob pattern to match against file/dir name (e.g., "*.py").
        max_depth: Max depth to descend.
        file_type: "file", "dir", or "all".
        include_hidden: Include hidden entries.
        max_results: Maximum number of results to return.

    Returns:
        A list of matching paths or an error message.
    """
    try:
        target_dir = _resolve_under_cwd(directory)
        if not target_dir.exists():
            return f"Error: Directory not found: {directory}"
        if not target_dir.is_dir():
            return f"Error: Path is not a directory: {directory}"

        base = Path.cwd().resolve()
        results: List[str] = []

        for root, dirs, files in os.walk(target_dir):
            root_path = Path(root)
            depth = len(root_path.relative_to(target_dir).parts)
            if depth >= max_depth:
                dirs[:] = []
            else:
                filtered_dirs = []
                for d in dirs:
                    if _is_excluded(d):
                        continue
                    if not include_hidden and d.startswith("."):
                        continue
                    filtered_dirs.append(d)
                dirs[:] = filtered_dirs

            if file_type in ("dir", "all"):
                for d in dirs:
                    if pattern and not fnmatch.fnmatch(d, pattern):
                        continue
                    rel = str((root_path / d).resolve().relative_to(base))
                    results.append(rel + "/")
                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break

            if file_type in ("file", "all"):
                for f in files:
                    if _is_excluded(f):
                        continue
                    if not include_hidden and f.startswith("."):
                        continue
                    if pattern and not fnmatch.fnmatch(f, pattern):
                        continue
                    rel = str((root_path / f).resolve().relative_to(base))
                    results.append(rel)
                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break

        if not results:
            return "No matches found."
        header = f"[FIND_FILES] {target_dir} pattern='{pattern}' depth<={max_depth} type={file_type}"
        output = header + "\n" + "\n".join(results)
        if len(results) >= max_results:
            output += f"\n... (truncated, max_results={max_results})"
        return output
    except Exception as e:
        return f"Error finding files: {str(e)}"


# @tool
# def file_stats(path: str) -> str:
#     """Return wc-like stats for a text file.
#
#     Args:
#         path: File path (relative to cwd or absolute).
#
#     Returns:
#         Line, word, and byte counts or an error message.
#     """
#     try:
#         target = _resolve_under_cwd(path)
#         if not target.exists():
#             return f"Error: File not found: {path}"
#         if not target.is_file():
#             return f"Error: Path is not a file: {path}"
#
#         # Basic text/binary detection: treat files with NUL bytes as binary
#         with target.open("rb") as f:
#             sample = f.read(4096)
#             if b"\x00" in sample:
#                 return "Error: Binary file detected. file_stats only supports text files."
#
#         lines = 0
#         words = 0
#         bytes_count = 0
#
#         with target.open("rb") as f:
#             for chunk in iter(lambda: f.read(64 * 1024), b""):
#                 bytes_count += len(chunk)
#                 # Decode per chunk for word/line counts
#                 text = chunk.decode("utf-8", errors="replace")
#                 lines += text.count("\n")
#                 words += len(text.split())
#
#         return f"[FILE_STATS] {target}\nlines: {lines}\nwords: {words}\nbytes: {bytes_count}"
#     except Exception as e:
#         return f"Error getting file stats: {str(e)}"


@tool
def grep_file(paths: str | list[str], keyword: str, context_lines: int = 0, max_matches: int = 200) -> str:
    """Grep-like search within one or multiple files.

    Args:
        paths: A single file path or a list of file paths (relative to cwd or absolute).
        keyword: Keyword to search for.
        context_lines: Include N lines of context before/after each match.
        max_matches: Maximum number of matches to return.

    Returns:
        Matching lines with line numbers or an error message.
    """
    try:
        if not keyword:
            return "Error: keyword is required."

        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not paths:
            return "Error: paths must be a non-empty string or list of strings."

        results: List[str] = []

        for path in paths:
            target = _resolve_under_cwd(path)
            if not target.exists():
                results.append(f"Error: File not found: {path}")
                continue
            if not target.is_file():
                results.append(f"Error: Path is not a file: {path}")
                continue

            # Basic text/binary detection: treat files with NUL bytes as binary
            with target.open("rb") as f:
                sample = f.read(4096)
                if b"\x00" in sample:
                    results.append(f"Error: Binary file detected (skipped): {path}")
                    continue

            buffer: List[str] = []
            buffer_lines: List[int] = []
            results.append(f"[GREP_FILE] {target} keyword='{keyword[:60]}'")
            with target.open("r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, start=1):
                    line_clean = line.rstrip("\n")
                    buffer.append(line_clean)
                    buffer_lines.append(idx)
                    if len(buffer) > context_lines * 2 + 1:
                        buffer.pop(0)
                        buffer_lines.pop(0)

                    if keyword in line:
                        start_idx = max(0, len(buffer) - (context_lines + 1))
                        end_idx = len(buffer)
                        for i in range(start_idx, end_idx):
                            lnum = buffer_lines[i]
                            ctx_line = buffer[i]
                            prefix = ">" if keyword in ctx_line else " "
                            results.append(f"{lnum}: {prefix} {ctx_line}")
                        results.append("---")
                        if len(results) >= max_matches:
                            break
            if len(results) >= max_matches:
                break

        if not results:
            return "No matches found."
        output = "\n".join(results)
        if len(results) >= max_matches:
            output += f"\n... (truncated, max_matches={max_matches})"
        return output
    except Exception as e:
        return f"Error grepping file: {str(e)}"


@tool
def search_in_files(
        directory: str,
        keyword: str,
        file_glob: str = "*",
        max_results: int = 50,
        context_lines: int = 0,
        max_file_bytes: int = 500_000
) -> str:
    """Search for a keyword within files under a directory.

    Args:
        directory: Directory to scan (relative to cwd or absolute).
        keyword: Keyword to search for.
        file_glob: Glob pattern to filter files (e.g., "*.py").
        max_results: Maximum number of matches to return.
        context_lines: Include N lines of context before/after each match.
        max_file_bytes: Skip files larger than this size.

    Returns:
        Matching lines with file path and line number or an error message.
    """
    try:
        if not keyword:
            return "Error: keyword is required."
        target_dir = _resolve_under_cwd(directory)
        if not target_dir.exists():
            return f"Error: Directory not found: {directory}"
        if not target_dir.is_dir():
            return f"Error: Path is not a directory: {directory}"

        base = Path.cwd().resolve()
        results: List[str] = []

        for file_path in _iter_files(target_dir, include_hidden=False):
            if file_glob and not fnmatch.fnmatch(file_path.name, file_glob):
                continue
            try:
                if file_path.stat().st_size > max_file_bytes:
                    continue
                rel_path = str(file_path.resolve().relative_to(base))
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    buffer: List[str] = []
                    for idx, line in enumerate(f, start=1):
                        buffer.append(line.rstrip("\n"))
                        if len(buffer) > context_lines * 2 + 1:
                            buffer.pop(0)
                        if keyword in line:
                            start_idx = max(0, len(buffer) - (context_lines + 1))
                            end_idx = len(buffer)
                            for offset, ctx_line in enumerate(buffer[start_idx:end_idx],
                                                              start=idx - (end_idx - start_idx) + 1):
                                prefix = ">" if keyword in ctx_line else " "
                                results.append(f"{rel_path}:{offset}: {prefix} {ctx_line}")
                            results.append("---")
                            if len(results) >= max_results:
                                break
                if len(results) >= max_results:
                    break
            except Exception:
                continue

        if not results:
            return "No matches found."

        header = f"[SEARCH_IN_FILES] keyword='{keyword[:60]}'"
        output = header + "\n" + "\n".join(results)
        if len(results) >= max_results:
            output += f"\n... (truncated, max_results={max_results})"
        return output
    except Exception as e:
        return f"Error searching files: {str(e)}"


# @tool
# def write_file(path: str, content: str) -> str:
#     """Create a new file or completely overwrite an existing file with new content.
#
#     Args:
#         path: File path (relative to cwd or absolute).
#         content: The complete content to write to the file.
#
#     Returns:
#         Success message or error.
#     """
#     try:
#         target = _resolve_under_cwd(path)
#         target.parent.mkdir(parents=True, exist_ok=True)
#         with target.open("w", encoding="utf-8") as f:
#             f.write(content)
#         return f"[WRITE_FILE] Successfully wrote {len(content)} characters to {target}"
#     except Exception as e:
#         return f"Error writing file: {str(e)}"


@tool
def replace_in_file(path: str, old_text: str, new_text: str) -> str:
    """Replace an exact string with new text in a file.

    WARNING: The old_text must match exactly what is in the file, including spaces, tabs, and newlines!

    Args:
        path: File path (relative to cwd or absolute).
        old_text: The exact text to find and replace.
        new_text: The text to replace it with.

    Returns:
        Success message showing how many replacements occurred, or an error.
    """
    try:
        if not old_text:
            return "Error: old_text cannot be empty."

        target = _resolve_under_cwd(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        if not target.is_file():
            return f"Error: Path is not a file: {path}"

        with target.open("r", encoding="utf-8", errors="replace") as f:
            file_content = f.read()

        if old_text not in file_content:
            return "Error: old_text not found in file. Ensure exact match including whitespace."

        count = file_content.count(old_text)
        new_content = file_content.replace(old_text, new_text)

        with target.open("w", encoding="utf-8") as f:
            f.write(new_content)

        return f"[REPLACE_IN_FILE] Successfully replaced {count} occurrence(s) in {target}"
    except Exception as e:
        return f"Error replacing in file: {str(e)}"

"""Local repository analysis utilities.

Scans a project directory on disk and assembles a structured code-context
string suitable for passing to the Coding and Review agents. The module is
deliberately dependency-free: it only uses the standard library so the rest of
the workflow can run offline when network access is unavailable for the
GitHub issue fetcher.

High-level flow:

1. :func:`scan_repository` is the public entrypoint. It returns a
   ``(summary, context_str)`` tuple: ``summary`` is a one-line human-readable
   report (number of files, total size, root) useful for logs/banners, and
   ``context_str`` is the Markdown block handed to the agents.
2. ``_iter_source_files`` walks the tree using :mod:`os.walk`, skipping common
   noise directories (``.venv``, ``__pycache__``, ``.git``, ``node_modules``…)
   and only keeping files whose extensions match :data:`SOURCE_EXTENSIONS`.
3. ``_read_file_safely`` reads each file with a per-file size cap and a
   decode-tolerant strategy so binary files or files with weird encodings
   don't crash the scan.
4. :func:`format_repository_context` builds the final Markdown envelope,
   preserving file paths alongside their contents so agents know *which file
   contained which snippet*. A total-size cap truncates the tail of the
   context so we never blow past the model's context window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------------------
# Defaults. Stored as module-level constants so callers can override per-scan
# via the `scan_repository` kwargs instead of mutating globals.
# ---------------------------------------------------------------------------

# File extensions considered "source" and included in the context. Covers
# Python plus the most common config / documentation / frontend files that
# a typical software engineering assistant will need to reference.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".toml",
        ".cfg",
        ".ini",
        ".yml",
        ".yaml",
        ".json",
        ".md",
        ".rst",
        ".txt",
        ".sh",
        ".bat",
        ".ps1",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".scss",
        ".env",
    }
)

# Directory names that are never walked. We use an exact-match set (cheap)
# plus fnmatch patterns for anything that needs globbing.
IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        ".tox",
        ".nox",
    }
)

IGNORED_DIR_PATTERNS: tuple[str, ...] = (
    "*.egg-info",
    ".eggs",
)

# File-level ignores. Includes compiled Python artifacts, binary blobs, and
# the context output itself so we don't accidentally feed a previous scan
# back into a later run.
IGNORED_FILE_PATTERNS: tuple[str, ...] = (
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.pyd",
    "*.dll",
    "*.exe",
    "*.class",
    "*.jar",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.zip",
    "*.tar.*",
    "*.gz",
    "*.whl",
    ".DS_Store",
    "Thumbs.db",
    "*_repo_context*.md",
)

DEFAULT_MAX_FILE_BYTES: int = 200 * 1024  # 200 KiB per file
DEFAULT_MAX_TOTAL_CHARS: int = 1_500_000   # ~1.5M chars total (safe cap)


class RepoScanError(RuntimeError):
    """Raised when a repository cannot be scanned (e.g. missing root dir)."""


@dataclass(frozen=True)
class RepoScanResult:
    """Structured result of :func:`scan_repository`.

    ``summary`` is a short banner line useful for stdout / logs.
    ``context`` is the full Markdown string intended for LLM consumption.
    ``files_seen`` is the raw count of source files that passed filters.
    """

    summary: str
    context: str
    files_seen: int
    root: Path
    truncated: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _name_ignored(name: str) -> bool:
    """Return True if a basename matches any ignored-file pattern."""
    return any(fnmatch(name, pattern) for pattern in IGNORED_FILE_PATTERNS)


def _dir_ignored(name: str) -> bool:
    """Return True if a directory basename should be skipped entirely."""
    if name in IGNORED_DIR_NAMES:
        return True
    return any(fnmatch(name, pattern) for pattern in IGNORED_DIR_PATTERNS)


def _is_source_file(path: Path) -> bool:
    """Return True if *path*'s extension is on the source-extension allowlist.

    We also treat dotfiles like ``.env`` (no extension but name starts with
    ``.env``) as source files so environment templates are included.
    """
    if path.suffix.lower() in SOURCE_EXTENSIONS:
        return True
    name = path.name
    if name.startswith(".env") and path.suffix.lower() in {"", ".local", ".dev", ".prod", ".test"}:
        return True
    return False


def _iter_source_files(root: Path) -> Iterable[Path]:
    """Yield every source file under *root* (unsorted by default; we sort
    per-directory to keep the output deterministic across runs).
    """
    # topdown=True lets us prune dirs in-place by mutating `dirnames`.
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Prune: filter dirnames IN PLACE so os.walk does not descend.
        dirnames[:] = sorted(d for d in dirnames if not _dir_ignored(d))
        for filename in sorted(filenames):
            if _name_ignored(filename):
                continue
            candidate = Path(dirpath) / filename
            if _is_source_file(candidate):
                yield candidate


def _read_file_safely(path: Path, max_bytes: int) -> Optional[str]:
    """Read *path* as text with a strict size cap and tolerant decoding.

    Returns ``None`` for files that exceed ``max_bytes`` or that cannot be
    decoded as text after trying UTF-8, UTF-8-surrogateescape, and cp1252.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return ""
    if size > max_bytes:
        return None  # too large; skip
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pass
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: surrogateescape so we still include files with stray bytes.
    try:
        return raw.decode("utf-8", errors="surrogateescape")
    except Exception:  # noqa: BLE001 - very last fallback
        return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _format_file_tree(files: Sequence[Path], root: Path) -> str:
    """Render a flat, indented tree of the files we are including.

    Kept deliberately simple (no nested branch glyphs) so we never spend code
    complexity on pretty-printing while remaining readable.
    """
    lines: list[str] = []
    for f in files:
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            rel = str(f)
        lines.append(f"  - {rel}")
    return "\n".join(lines) if lines else "  (no source files found)"


def format_repository_context(
    *,
    root: Path,
    files: Sequence[Path],
    file_contents: dict[Path, str],
    max_total_chars: int,
) -> tuple[str, bool]:
    """Build the Markdown context string and return ``(context, truncated)``.

    ``truncated`` is True when the combined size exceeded ``max_total_chars``
    and we had to drop files from the tail to stay within the budget. Callers
    can surface this to users via :class:`RepoScanResult`.
    """
    header_lines: list[str] = [
        "# Local Repository Context",
        "",
        f"- **Project root:** `{root.resolve().as_posix()}`",
        f"- **Source files included:** {len(files)}",
        "",
        "## File tree",
        "",
        _format_file_tree(files, root),
        "",
        "## File contents",
        "",
    ]
    # Budget accounting: start from the header length and append files until
    # we run out of room. We preserve ordering (sorted by relpath) so the
    # truncation point is deterministic.
    parts: list[str] = ["\n".join(header_lines)]
    used = sum(len(p) for p in parts)
    truncated = False

    for path in files:
        content = file_contents.get(path)
        if content is None:
            continue  # skipped (too big / unreadable)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        block = (
            f"### File: `{rel}`\n\n"
            "```\n"
            f"{content.rstrip()}\n"
            "```\n\n"
        )
        if used + len(block) > max_total_chars:
            truncated = True
            break
        parts.append(block)
        used += len(block)

    if truncated:
        parts.append(
            "> Note: Repository context was truncated because the combined "
            "file contents exceeded the configured size cap. Not all source "
            "files are included above.\n\n"
        )

    return "".join(parts), truncated


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def scan_repository(
    root: os.PathLike[str] | str | None = None,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    extra_source_extensions: Optional[Iterable[str]] = None,
    extra_ignore_dirs: Optional[Iterable[str]] = None,
    extra_ignore_patterns: Optional[Iterable[str]] = None,
) -> RepoScanResult:
    """Scan *root* and return a :class:`RepoScanResult` suitable for LLM input.

    Parameters
    ----------
    root:
        Directory to scan. Defaults to the current working directory when
        ``None``. Must exist and be a directory.
    max_file_bytes:
        Skip individual files whose size exceeds this limit. Default 200 KiB.
    max_total_chars:
        Hard cap for the assembled context string. Files are appended in
        sorted order until this budget is exhausted. Default ~1.5M chars.
    extra_source_extensions:
        Additional extensions (with leading dot) to treat as source files.
    extra_ignore_dirs:
        Additional exact directory names to skip during the walk.
    extra_ignore_patterns:
        Additional fnmatch patterns for files to skip.

    Raises :class:`RepoScanError` if *root* is not a directory.
    """
    global IGNORED_DIR_NAMES, IGNORED_FILE_PATTERNS, SOURCE_EXTENSIONS

    resolved_root = Path(root if root is not None else os.getcwd()).resolve()
    if not resolved_root.is_dir():
        raise RepoScanError(
            f"Cannot scan repository: {resolved_root!s} is not a directory."
        )

    # Build one-off overrides without mutating module-level globals.
    extra_exts = {e.lower() for e in (extra_source_extensions or ())}
    extra_exts.discard("")
    if extra_exts:
        allowed_exts = SOURCE_EXTENSIONS | extra_exts
    else:
        allowed_exts = SOURCE_EXTENSIONS

    extra_dirs = set(extra_ignore_dirs or ())
    if extra_dirs:
        ignored_dir_names = IGNORED_DIR_NAMES | extra_dirs
    else:
        ignored_dir_names = IGNORED_DIR_NAMES

    extra_pats = tuple(extra_ignore_patterns or ())
    if extra_pats:
        ignored_file_pats = IGNORED_FILE_PATTERNS + extra_pats
    else:
        ignored_file_pats = IGNORED_FILE_PATTERNS

    # --- Walk, applying overridden filters locally -------------------------
    def dir_ignored_local(name: str) -> bool:
        if name in ignored_dir_names:
            return True
        return any(fnmatch(name, pattern) for pattern in IGNORED_DIR_PATTERNS)

    def name_ignored_local(name: str) -> bool:
        return any(fnmatch(name, pattern) for pattern in ignored_file_pats)

    def is_source_local(path: Path) -> bool:
        if path.suffix.lower() in allowed_exts:
            return True
        name = path.name
        if name.startswith(".env") and path.suffix.lower() in {"", ".local", ".dev", ".prod", ".test"}:
            return True
        return False

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(resolved_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if not dir_ignored_local(d))
        for filename in sorted(filenames):
            if name_ignored_local(filename):
                continue
            candidate = Path(dirpath) / filename
            if is_source_local(candidate):
                files.append(candidate)

    # --- Read files --------------------------------------------------------
    contents: dict[Path, str] = {}
    for f in files:
        text = _read_file_safely(f, max_file_bytes)
        if text is not None:
            contents[f] = text

    # Drop files we couldn't read from the ordering so the tree matches.
    readable_files = [f for f in files if f in contents]

    # --- Format ------------------------------------------------------------
    context, truncated = format_repository_context(
        root=resolved_root,
        files=readable_files,
        file_contents=contents,
        max_total_chars=max_total_chars,
    )

    summary = (
        f"Repository scan: {len(readable_files)} source files from "
        f"{resolved_root.as_posix()} (truncated={truncated})"
    )

    return RepoScanResult(
        summary=summary,
        context=context,
        files_seen=len(readable_files),
        root=resolved_root,
        truncated=truncated,
    )

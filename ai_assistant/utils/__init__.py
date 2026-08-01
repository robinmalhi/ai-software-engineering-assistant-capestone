"""Utilities subpackage.

Lightweight helpers used across the project. Start empty and add modules
(formatting, logging, text processing, etc.) as the project grows.
"""

from .github_issues import (
    GitHubIssueError,
    GitHubIssueRef,
    fetch_github_issue,
    format_github_issue,
    format_raw_issue,
    looks_like_github_issue_url,
    parse_github_issue_url,
    resolve_issue_input,
)
from .github_repo import (
    GitHubRepoCloneError,
    GitHubRepoRef,
    TemporaryClonedRepo,
    looks_like_github_repo_url,
    parse_github_repo_url,
    scan_github_repository_url,
    with_cloned_github_repo,
)
from .repo_scanner import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_TOTAL_CHARS,
    IGNORED_DIR_NAMES,
    IGNORED_DIR_PATTERNS,
    IGNORED_FILE_PATTERNS,
    RepoScanError,
    RepoScanResult,
    SOURCE_EXTENSIONS,
    format_repository_context,
    scan_repository,
)
from .reporting import (
    DEFAULT_REPORT_FILENAME,
    StepRecord,
    WorkflowReport,
    generate_and_write_report,
    render_report,
    write_report,
)

__all__ = [
    # github_issues
    "GitHubIssueError",
    "GitHubIssueRef",
    "fetch_github_issue",
    "format_github_issue",
    "format_raw_issue",
    "looks_like_github_issue_url",
    "parse_github_issue_url",
    "resolve_issue_input",
    # github_repo
    "GitHubRepoCloneError",
    "GitHubRepoRef",
    "TemporaryClonedRepo",
    "looks_like_github_repo_url",
    "parse_github_repo_url",
    "scan_github_repository_url",
    "with_cloned_github_repo",
    # repo_scanner
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_TOTAL_CHARS",
    "IGNORED_DIR_NAMES",
    "IGNORED_DIR_PATTERNS",
    "IGNORED_FILE_PATTERNS",
    "RepoScanError",
    "RepoScanResult",
    "SOURCE_EXTENSIONS",
    "format_repository_context",
    "scan_repository",
    # reporting
    "DEFAULT_REPORT_FILENAME",
    "StepRecord",
    "WorkflowReport",
    "generate_and_write_report",
    "render_report",
    "write_report",
]

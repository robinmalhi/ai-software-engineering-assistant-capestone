"""GitHub Issue Analysis helpers.

Accepts either a GitHub issue URL or raw issue text, and returns a
normalized, single string suitable for passing to the Requirements Analysis
Agent. Responsibilities:

* Detect whether the input is a GitHub issue URL.
* Parse ``owner/repo/issue_number`` out of the URL.
* Fetch ``title`` and ``body`` via the GitHub REST API when a URL is given.
* Fall back to treating the input as raw issue text when it is not a URL.
* Handle invalid URLs, network errors, non-2xx responses, and missing
  fields gracefully so a failed fetch never breaks the pipeline.

The module is intentionally HTTP-library agnostic on the outside: it imports
``requests`` lazily so it only becomes a hard dependency when a URL is
actually used (raw text mode needs no network).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from ai_assistant.config import GITHUB_API_BASE_URL, get_github_token


# Matches a GitHub issues URL with owner, repo, and issue number.
# Accepts http/https, optional www. subdomain, optional trailing slash,
# query strings, and URL fragments.
_GITHUB_ISSUE_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/"
    r"issues/(?P<number>\d+)"
    r"(?:[/?#].*)?$"
)


class GitHubIssueError(RuntimeError):
    """Raised when a GitHub issue cannot be fetched or parsed.

    Callers should catch this and fall back to raw text analysis when
    appropriate so the workflow never fails hard on a bad URL.
    """


@dataclass(frozen=True)
class GitHubIssueRef:
    """Parsed reference to a GitHub issue."""

    owner: str
    repo: str
    number: int

    @property
    def api_url(self) -> str:
        return f"{GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/issues/{self.number}"


def looks_like_github_issue_url(value: str) -> bool:
    """Return True if *value* appears to be a GitHub issues URL.

    This is intentionally a light heuristic before doing any network work.
    We validate the URL more strictly inside :func:`parse_github_issue_url`
    so bad URLs produce an actionable error message rather than a silent
    "this isn't a URL" fallthrough.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def parse_github_issue_url(url: str) -> GitHubIssueRef:
    """Parse a GitHub issues URL into a :class:`GitHubIssueRef`.

    Raises :class:`GitHubIssueError` for malformed URLs or non-GitHub URLs.
    """
    if not isinstance(url, str):
        raise GitHubIssueError("URL must be a string.")

    candidate = url.strip()
    match = _GITHUB_ISSUE_URL_RE.match(candidate)
    if not match:
        # If the hostname is github.com but the path shape is wrong, surface
        # a more specific message to help the user correct it.
        parsed = urlparse(candidate)
        if parsed.hostname and "github.com" in parsed.hostname:
            raise GitHubIssueError(
                f"GitHub URL has unexpected shape: {candidate!r}. "
                "Expected https://github.com/<owner>/<repo>/issues/<number>."
            )
        raise GitHubIssueError(f"Not a valid GitHub issue URL: {candidate!r}.")

    return GitHubIssueRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


def _build_github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-software-engineering-assistant/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _requests_session():
    """Lazy ``requests`` import so raw-text mode needs no HTTP dependency."""
    try:
        import requests  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment issue
        raise GitHubIssueError(
            "The 'requests' package is required to fetch GitHub issue URLs. "
            "Install it into your environment or pass raw issue text instead."
        ) from exc
    return requests


def fetch_github_issue(ref: GitHubIssueRef) -> dict:
    """Fetch raw issue JSON from the GitHub REST API.

    Raises :class:`GitHubIssueError` on any network or API failure so the
    caller can decide whether to fall back to raw text or surface the error.
    """
    requests = _requests_session()
    headers = _build_github_headers()

    try:
        response = requests.get(ref.api_url, headers=headers, timeout=30)
    except Exception as exc:  # noqa: BLE001 - translate every network failure
        raise GitHubIssueError(
            f"Network error while fetching GitHub issue {ref.api_url}: {exc}"
        ) from exc

    if response.status_code != 200:
        # Try to extract GitHub's message for a nicer error, but tolerate
        # non-JSON bodies as well.
        detail = None
        try:
            payload = response.json()
            detail = payload.get("message") if isinstance(payload, dict) else None
        except ValueError:
            detail = None
        raise GitHubIssueError(
            f"GitHub API returned HTTP {response.status_code} for "
            f"{ref.api_url}" + (f": {detail}" if detail else ".")
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubIssueError(
            f"GitHub API returned invalid JSON for {ref.api_url}."
        ) from exc

    if not isinstance(data, dict):
        raise GitHubIssueError(
            f"GitHub API returned an unexpected response shape for {ref.api_url}."
        )
    return data


def format_github_issue(
    *,
    title: str,
    body: Optional[str],
    html_url: Optional[str] = None,
    labels: Optional[list[str]] = None,
    state: Optional[str] = None,
) -> str:
    """Format a fetched GitHub issue into the string sent to the first agent.

    The Requirements Analysis Agent was originally trained on a single blob
    of issue text, so we preserve that shape while adding structured header
    fields (title, URL, labels...) as Markdown sections it can still read
    naturally.
    """
    cleaned_title = (title or "(untitled issue)").strip()
    cleaned_body = (body or "").strip()
    lines = [f"# GitHub Issue: {cleaned_title}"]
    if html_url:
        lines.append(f"- **URL:** {html_url}")
    if state:
        lines.append(f"- **State:** {state}")
    if labels:
        joined = ", ".join(label for label in labels if label)
        if joined:
            lines.append(f"- **Labels:** {joined}")
    lines.append("")
    lines.append("## Body")
    lines.append(cleaned_body if cleaned_body else "(no body provided)")
    return "\n".join(lines)


def format_raw_issue(raw_text: str) -> str:
    """Format raw issue text into the same envelope used for fetched issues.

    Using a consistent envelope means downstream agents don't need to know
    whether the input came from a URL or from the CLI.
    """
    return (
        "# Issue (raw input)\n\n"
        "## Body\n\n"
        f"{raw_text.strip() if raw_text else '(empty input)'}"
    )


def resolve_issue_input(user_input: Optional[str]) -> tuple[str, str]:
    """Normalize *user_input* into (source, issue_text) for the pipeline.

    Resolution rules:
    1. If *user_input* is empty or ``None``, return ``('default', <fallback>)``
       using the default issue in config.
    2. If *user_input* looks like a GitHub issue URL, try to fetch and format
       it. On failure fall back to treating it as raw text and report
       ``'raw_text (URL fetch failed: ...)'`` as the source.
    3. Otherwise treat it as raw issue text and return ``('raw_text', ...)``.

    Returns ``(source, issue_text)`` so callers/logging can describe where
    the input came from.
    """
    from ai_assistant.config import DEFAULT_ISSUE  # local import to avoid cycles

    if not user_input or not isinstance(user_input, str) or not user_input.strip():
        return ("default", format_raw_issue(DEFAULT_ISSUE))

    candidate = user_input.strip()

    if looks_like_github_issue_url(candidate):
        try:
            ref = parse_github_issue_url(candidate)
            data = fetch_github_issue(ref)
            raw_labels = data.get("labels") or []
            labels: list[str] = []
            for item in raw_labels:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str):
                        labels.append(name)
                elif isinstance(item, str):
                    labels.append(item)
            formatted = format_github_issue(
                title=str(data.get("title") or "(untitled issue)"),
                body=data.get("body"),
                html_url=data.get("html_url") or ref.api_url,
                labels=labels,
                state=data.get("state"),
            )
            return (f"github_issue:{ref.owner}/{ref.repo}#{ref.number}", formatted)
        except GitHubIssueError as exc:
            # Fall back instead of raising so the workflow still runs.
            source = f"raw_text (URL fetch failed: {exc})"
            return (source, format_raw_issue(user_input))

    return ("raw_text", format_raw_issue(user_input))

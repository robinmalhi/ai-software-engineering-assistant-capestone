"""Public GitHub repository cloning + analysis helpers.

Accepts a public GitHub repository URL (``https://github.com/<owner>/<repo>``,
with optional ``.git`` suffix, branch/ref, query strings, or ``/tree/<ref>``
shapes), clones it into a temporary directory, runs the local
:func:`~ai_assistant.utils.repo_scanner.scan_repository` over the checkout,
then guarantees cleanup of the temp directory via a context-manager pattern.

The module is deliberately flexible about clone strategy: it prefers calling
the ``git`` CLI via :mod:`subprocess` so public repos can be cloned with
``--depth 1`` (shallow clone, minimal bandwidth) and cleaned up simply by
deleting the temp directory. When ``git`` is not installed on the host, we
fall back to downloading a source tarball from GitHub's codeload endpoint
over HTTPS and unpacking it with :mod:`tarfile` — no extra dependencies
required beyond what ``github_issues.py`` already uses (``requests`` is lazy
imported only when needed).

Design goals:

* **Always clean up.** The :class:`TemporaryClonedRepo` context manager
  ensures ``tempfile.TemporaryDirectory`` is removed even when the caller
  raises. Callers that don't use the CM still get ``atexit``-registered
  cleanup as a last-resort safety net.
* **Never break the pipeline.** All clone failures raise
  :class:`GitHubRepoCloneError`, which the workflow catches and downgrades
  into a "proceed without repo context" path — matching the graceful-failure
  pattern of the issue fetcher and local-repo scanner.
* **Modular.** Pure utilities here; no workflow imports. The pipeline only
  calls :func:`with_cloned_github_repo` / :func:`scan_github_repository_url`.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator, Optional, Tuple

from ai_assistant.config import GITHUB_API_BASE_URL, get_github_token
from ai_assistant.utils.repo_scanner import RepoScanResult, scan_repository


# Matches GitHub repo URLs. Accepted forms:
#   https://github.com/owner/repo
#   https://github.com/owner/repo.git
#   https://github.com/owner/repo/
#   https://github.com/owner/repo/tree/main
#   https://github.com/owner/repo/tree/v1.0?x=1#y
#   http://github.com/owner/repo.git
_GITHUB_REPO_URL_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?(?:[/?#].*)?$"
)


class GitHubRepoCloneError(RuntimeError):
    """Raised when a GitHub repository URL cannot be parsed, cloned, or unpacked.

    Callers (typically :mod:`ai_assistant.workflow.pipeline`) should catch
    this and continue without repository context so a failed clone never
    fails the overall workflow.
    """


@dataclass(frozen=True)
class GitHubRepoRef:
    """Parsed reference to a public GitHub repository (owner + repo + optional ref)."""

    owner: str
    repo: str
    ref: Optional[str] = None  # branch, tag, or commit SHA. None means the default branch.

    @property
    def clone_url(self) -> str:
        """HTTPS clone URL (``.git`` suffix) suitable for ``git clone <url>``."""
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def html_url(self) -> str:
        """Browser URL for the repository page (used in metadata)."""
        return f"https://github.com/{self.owner}/{self.repo}" + (
            f"/tree/{self.ref}" if self.ref else ""
        )

    @property
    def codeload_tarball_url(self) -> str:
        """GitHub codeload endpoint for a tarball download (fallback when git CLI is missing)."""
        ref = self.ref if self.ref else "HEAD"
        safe_ref = urllib.parse.quote(ref, safe="")
        return f"https://codeload.github.com/{self.owner}/{self.repo}/tar.gz/refs/heads/{safe_ref}"


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def looks_like_github_repo_url(value: str) -> bool:
    """Lightweight heuristic: True if *value* starts with http(s)://."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    return s.startswith("http://") or s.startswith("https://")


def parse_github_repo_url(url: str) -> GitHubRepoRef:
    """Parse *url* into a :class:`GitHubRepoRef`.

    Supports optional ``/tree/<ref>`` suffix in the URL path. Raises
    :class:`GitHubRepoCloneError` with a descriptive message for non-GitHub
    URLs or GitHub URLs with the wrong shape.
    """
    if not isinstance(url, str):
        raise GitHubRepoCloneError("Repository URL must be a string.")

    candidate = url.strip()
    match = _GITHUB_REPO_URL_RE.match(candidate)
    if not match:
        parsed = urllib.parse.urlparse(candidate)
        if parsed.hostname and "github.com" in parsed.hostname:
            raise GitHubRepoCloneError(
                f"GitHub URL has unexpected shape: {candidate!r}. "
                "Expected https://github.com/<owner>/<repo>."
            )
        raise GitHubRepoCloneError(f"Not a valid GitHub repository URL: {candidate!r}.")

    owner = match.group("owner")
    repo = match.group("repo")

    # Parse the remainder of the path (after /<owner>/<repo>). We only accept
    # empty/trailing-slash, `.git`, or `/tree/<ref>`. Everything else (e.g.
    # `/pull/5`, `/issues/1`, `/blob/...`) is a GitHub URL but NOT a valid
    # repository root URL.
    cleaned = candidate
    # Strip trailing query/fragment for path-shape analysis.
    path_only = urllib.parse.urlparse(cleaned).path.rstrip("/")
    owner_repo_path = f"/{owner}/{repo}"
    remainder = path_only[len(owner_repo_path):]
    if remainder and remainder != ".git":
        # Must match `/tree/<ref>` (where ref may contain `/`).
        tree_match = re.match(r"^/tree/(?P<ref>.+)$", remainder)
        if not tree_match:
            raise GitHubRepoCloneError(
                f"GitHub URL path contains non-repository suffix {remainder!r}. "
                "Expected a repository root URL such as https://github.com/<owner>/<repo> "
                "or a tree URL such as https://github.com/<owner>/<repo>/tree/<ref>."
            )

    # Extract /tree/<ref> if present. Ref can contain `/` (e.g. "feature/x.y"
    # or "refs/heads/main") so we consume everything up to the next `?` or `#`
    # instead of stopping at the first slash.
    ref: Optional[str] = None
    stripped = candidate.split("#", 1)[0].split("?", 1)[0]
    tree_match_ref = re.search(r"/tree/(?P<ref>.+)$", stripped)
    if tree_match_ref:
        ref = urllib.parse.unquote(tree_match_ref.group("ref").rstrip("/"))

    return GitHubRepoRef(owner=owner, repo=repo, ref=ref)


# ---------------------------------------------------------------------------
# Clone strategies
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    """Return True if the ``git`` CLI is reachable on PATH."""
    return shutil.which("git") is not None


def _run_git(args: list[str], *, cwd: Optional[Path] = None) -> None:
    """Run a git subcommand, translating failures into GitHubRepoCloneError."""
    cmd = ["git", *args]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitHubRepoCloneError(
            "git CLI not found on PATH. Install git or allow HTTPS tarball fallback."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - translate any OS/pipe errors
        raise GitHubRepoCloneError(f"Failed to run git {' '.join(args)!r}: {exc}") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise GitHubRepoCloneError(
            f"git {' '.join(args)!r} exited with status {completed.returncode}: "
            f"{stderr or '(no stderr output)'}"
        )


def _clone_via_git(ref: GitHubRepoRef, dest: Path) -> None:
    """Shallow-clone *ref* into the empty directory *dest* using the git CLI.

    Prefers ``--depth 1`` for speed; when a specific ref is requested and the
    shallow fetch fails (because codeload's HEAD and the named ref diverge, or
    the ref is a non-branch tag), we retry with ``--depth 50`` then finally
    an unshallow fetch before giving up.
    """
    # git clone requires the destination to not exist yet.
    if dest.exists():
        shutil.rmtree(dest)

    base_cmd = ["clone", "--quiet"]

    if ref.ref:
        base_cmd.extend(["--branch", ref.ref])

    # Shallow + filter=blob:none is extremely fast for code-only snapshots.
    base_cmd.extend(["--depth", "1", "--filter=blob:none"])
    base_cmd.extend([ref.clone_url, str(dest)])

    try:
        _run_git(base_cmd)
        return
    except GitHubRepoCloneError:
        # If the ref-specific clone failed, fall back to a slightly deeper
        # fetch of the default branch.
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=True)
        fallback = ["clone", "--quiet", "--depth", "50", ref.clone_url, str(dest)]
        _run_git(fallback)


def _download_tarball(ref: GitHubRepoRef, dest: Path) -> None:
    """Fallback clone strategy: download the GitHub tarball and unpack it.

    Used when ``git`` is not installed. Uses a lazy ``requests`` import so
    raw-text-only runs that never hit this code path don't require the
    ``requests`` package.
    """
    try:
        import requests  # type: ignore
    except ImportError as exc:  # pragma: no cover - env issue
        raise GitHubRepoCloneError(
            "Neither the 'git' CLI nor the 'requests' package are available. "
            "Install one of them to clone GitHub repositories."
        ) from exc

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-software-engineering-assistant/1.0",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = ref.codeload_tarball_url
    try:
        response = requests.get(url, headers=headers, timeout=120, stream=True)
    except Exception as exc:  # noqa: BLE001
        raise GitHubRepoCloneError(
            f"Network error while downloading GitHub tarball {url}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise GitHubRepoCloneError(
            f"GitHub codeload returned HTTP {response.status_code} for {url}."
        )

    try:
        data = BytesIO(response.content)
        with tarfile.open(fileobj=data, mode="r:gz") as tf:
            # Codeload tarballs have a single top-level folder like
            # "owner-repo-<sha>/". We strip that single component so the
            # extracted layout matches what `git clone` would produce at
            # `dest` directly.
            members = tf.getmembers()
            if not members:
                raise GitHubRepoCloneError(f"GitHub tarball for {ref.clone_url} is empty.")
            toplevel = members[0].name.split("/", 1)[0]
            dest.mkdir(parents=True, exist_ok=True)
            for member in members:
                # Defensive: reject absolute paths or path traversal.
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    continue
                stripped = member.name[len(toplevel) + 1 :] if member.name.startswith(toplevel + "/") else member.name
                if not stripped or stripped == ".":
                    continue
                member.name = stripped
                target = dest / stripped
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        tf.extract(member, path=str(dest))
                    except Exception as exc:  # noqa: BLE001
                        # Skip unextractable members rather than failing the whole repo.
                        pass
    except GitHubRepoCloneError:
        raise
    except tarfile.TarError as exc:
        raise GitHubRepoCloneError(
            f"Failed to unpack GitHub tarball for {ref.clone_url}: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise GitHubRepoCloneError(
            f"Unexpected error while unpacking GitHub tarball for {ref.clone_url}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public context manager + high-level scanner
# ---------------------------------------------------------------------------


@dataclass
class TemporaryClonedRepo:
    """Context manager yielding the checkout directory of a cloned GitHub repo.

    Guarantees cleanup of the temporary directory on ``__exit__``, and also
    registers the directory with :mod:`atexit` so process-abort paths still
    don't leak leftover folders.
    """

    ref: GitHubRepoRef
    _tmpdir: Optional[tempfile.TemporaryDirectory[str]] = None

    @property
    def path(self) -> Path:
        if self._tmpdir is None:
            raise RuntimeError("TemporaryClonedRepo.path accessed outside its context manager.")
        return Path(self._tmpdir.name) / "repo"

    def __enter__(self) -> "TemporaryClonedRepo":
        self._tmpdir = tempfile.TemporaryDirectory(prefix="ai-sea-ghrepo-")

        def _cleanup_tmpdir() -> None:
            try:
                if self._tmpdir is not None:
                    self._tmpdir.cleanup()
            except Exception:  # noqa: BLE001 - atexit best-effort
                pass

        atexit.register(_cleanup_tmpdir)
        self._cleanup_cb = _cleanup_tmpdir  # type: ignore[attr-defined]

        # Strategy priority: git CLI (fast, shallow) > tarball download.
        dest = self.path
        try:
            if _git_available():
                _clone_via_git(self.ref, dest)
            else:
                _download_tarball(self.ref, dest)
        except GitHubRepoCloneError:
            # Clean up eagerly on failure rather than waiting for atexit.
            try:
                if self._tmpdir is not None:
                    self._tmpdir.cleanup()
            finally:
                try:
                    atexit.unregister(_cleanup_tmpdir)
                except Exception:  # noqa: BLE001
                    pass
                self._tmpdir = None
            raise

        if not dest.is_dir():
            self.__exit__(None, None, None)
            raise GitHubRepoCloneError(
                f"Clone appeared to succeed but checkout directory {dest} does not exist."
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        cb = getattr(self, "_cleanup_cb", None)
        if cb is not None:
            try:
                atexit.unregister(cb)
            except Exception:  # noqa: BLE001
                pass
        td = self._tmpdir
        self._tmpdir = None
        if td is not None:
            try:
                td.cleanup()
            except Exception:  # noqa: BLE001
                pass


@contextmanager
def with_cloned_github_repo(repo_url: str) -> Iterator[Tuple[GitHubRepoRef, Path]]:
    """Context manager yielding ``(ref, checkout_path)`` for a cloned public GitHub repo.

    Usage::

        with with_cloned_github_repo("https://github.com/o/r") as (ref, path):
            result = scan_repository(path)
        # Temp directory is cleaned up here, even on exceptions.
    """
    parsed_ref = parse_github_repo_url(repo_url)
    with TemporaryClonedRepo(parsed_ref) as cloned:
        yield parsed_ref, cloned.path


def scan_github_repository_url(
    repo_url: str,
    *,
    max_file_bytes: int = ...,  # type: ignore[assignment]
    max_total_chars: int = ...,  # type: ignore[assignment]
) -> Tuple[GitHubRepoRef, RepoScanResult]:
    """High-level convenience: clone *repo_url*, scan it, cleanup, return ref+result.

    Wraps :func:`with_cloned_github_repo` and :func:`scan_repository`.
    Raises :class:`GitHubRepoCloneError` on any parse/clone/scan failure.
    """
    kwargs: dict = {}
    if max_file_bytes is not ...:
        kwargs["max_file_bytes"] = max_file_bytes
    if max_total_chars is not ...:
        kwargs["max_total_chars"] = max_total_chars
    with with_cloned_github_repo(repo_url) as (ref, path):
        try:
            result = scan_repository(path, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise GitHubRepoCloneError(
                f"Failed to scan cloned repository {ref.clone_url}: {exc}"
            ) from exc
        return ref, result

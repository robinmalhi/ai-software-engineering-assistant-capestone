"""Entrypoint for the AI Software Engineering Assistant.

Usage examples:

    # Run with the built-in default issue, analyzing the current working dir
    python main.py

    # Run with raw issue text (quote it to keep it a single argument)
    python main.py "Add password reset with JWT tokens."

    # Run from a GitHub issue URL
    python main.py --url https://github.com/owner/repo/issues/123

    # Analyze a *different* repository (public GitHub repo) instead of cwd
    python main.py --repo-url https://github.com/owner/repo "fix the build"

This module intentionally stays small: it loads settings, resolves the
input into a normalized issue string, and delegates pipeline execution to
:mod:`ai_assistant.workflow`. Keeping orchestration logic in the workflow
package means this entrypoint can easily be swapped for a FastAPI server,
CLI framework (Typer/Click), or test runner later.
"""

from __future__ import annotations

import argparse
import asyncio

from ai_assistant.config import load_settings
from ai_assistant.workflow import prepare_workflow_input, run_workflow

load_settings()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AI Software Engineering Assistant on a GitHub issue URL "
            "or raw issue text, optionally analyzing a public GitHub "
            "repository instead of the current working directory."
        )
    )
    issue_group = parser.add_mutually_exclusive_group()
    issue_group.add_argument(
        "--url",
        type=str,
        default=None,
        help="GitHub issue URL to analyze (e.g. https://github.com/o/r/issues/1).",
    )
    issue_group.add_argument(
        "text",
        nargs="?",
        default=None,
        help="Raw issue text to analyze. If omitted, the built-in default is used.",
    )
    repo_group = parser.add_mutually_exclusive_group()
    repo_group.add_argument(
        "--repo-url",
        type=str,
        default=None,
        help=(
            "Public GitHub repository URL to clone and analyze instead of the "
            "current directory. Example: https://github.com/o/r or "
            "https://github.com/o/r/tree/branch-name."
        ),
    )
    repo_group.add_argument(
        "--no-local-repo",
        action="store_true",
        help=(
            "Disable local repository analysis entirely (do not scan cwd and "
            "do not clone a remote repo). Useful for offline or snippet runs."
        ),
    )
    return parser.parse_args(argv)


def _select_user_input(args: argparse.Namespace) -> str | None:
    # --url wins when provided; otherwise positional text; otherwise None
    # triggers the built-in default issue inside prepare_workflow_input.
    if args.url:
        return args.url
    return args.text


def _select_repo_kwargs(args: argparse.Namespace) -> dict:
    """Return the ``repo_url`` / ``repo_root`` kwargs for run_workflow.

    Priority:
      1. ``--repo-url URL`` -> pass as ``repo_url``; ``repo_root=None``.
      2. ``--no-local-repo`` -> skip all local + remote repo analysis.
      3. (default)         -> use ``repo_root="."`` (current directory scan).
    """
    if args.repo_url:
        return {"repo_url": args.repo_url, "repo_root": None}
    if args.no_local_repo:
        return {"repo_root": None, "repo_url": None}
    return {"repo_root": ".", "repo_url": None}


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    user_input = _select_user_input(args)
    repo_kwargs = _select_repo_kwargs(args)

    source, issue_text = prepare_workflow_input(user_input)
    print(f"\n[Workflow] Input source: {source}")
    if args.repo_url:
        print(f"[Workflow] Target repository: {args.repo_url} (will clone to temp dir)")
    elif args.no_local_repo:
        print("[Workflow] Local & remote repository analysis disabled.")
    else:
        print("[Workflow] Target repository: current working directory")
    print(
        "[Workflow] Passing the issue below to the Requirements Analysis Agent:\n"
        f"{issue_text}"
    )

    await run_workflow(issue_text, issue_source=source, **repo_kwargs)


if __name__ == "__main__":
    asyncio.run(main())

"""Sequential five-agent pipeline.

The pipeline is defined as a data-driven list of ``(step_name, agent)`` pairs.
``run_workflow`` iterates them in order, passing each agent's ``final_output``
as the input to the next agent.

Keeping orchestration here (instead of in ``main.py``) means the same pipeline
can be reused from a CLI, an API server, a test harness, or future tools without
duplicating logic.

Repository context (if enabled via ``run_workflow(repo_root=...)``) is assembled
once before the step loop and injected into the Coding and Review agents'
inputs, so they can reference existing source files without needing access to
disk themselves.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from agents import Agent, Runner

from ai_assistant.agents import (
    coding_agent,
    documentation_agent,
    planning_agent,
    requirements_agent,
    review_agent,
)
from ai_assistant.utils.github_issues import resolve_issue_input
from ai_assistant.utils.github_repo import (
    GitHubRepoCloneError,
    GitHubRepoRef,
    with_cloned_github_repo,
)
from ai_assistant.utils.repo_scanner import RepoScanResult, RepoScanError, scan_repository
from ai_assistant.utils.reporting import (
    DEFAULT_REPORT_FILENAME,
    generate_and_write_report,
)

# Ordered sequential workflow. Add/reorder steps here to change the pipeline.
WORKFLOW: List[Tuple[str, Agent]] = [
    ("Requirements Analysis", requirements_agent),
    ("Implementation Planning", planning_agent),
    ("Coding Assistant", coding_agent),
    ("Review & Bug Investigation", review_agent),
    ("Documentation", documentation_agent),
]

# Steps that should receive the local repository context when it is available.
# The Requirements and Planning agents operate on the user's request / design,
# while Coding and Review benefit from seeing the existing codebase.
REPO_CONTEXT_STEPS: frozenset[str] = frozenset(
    {"Coding Assistant", "Review & Bug Investigation"}
)

# Banner separator width used when printing step results to stdout.
_STEP_BANNER_WIDTH = 60


def _inject_repo_context(base_input: str, repo_context: str) -> str:
    """Prepend the repository context block to a step's input string.

    The context is placed *before* the step body so the model sees project
    structure first, then the specific task to perform against it. A clear
    section delimiter keeps the two blocks visually separable.
    """
    divider = "\n" + ("-" * _STEP_BANNER_WIDTH) + "\n\n"
    return repo_context.rstrip() + divider + base_input.lstrip()


def build_step_input(
    current_agent_name: str,
    previous_agent_name: str,
    previous_output: str,
    original_issue: str,
    repo_context: Optional[str] = None,
) -> str:
    """Build the input string passed to a pipeline step (after the first).

    The prompt includes:
      - the step name,
      - the *original* user request so downstream agents don't drift,
      - the previous agent's output, which is the primary artifact to act on,
      - (optionally, for Coding/Review steps) the repository context snapshot
        produced by :func:`~ai_assistant.utils.repo_scanner.scan_repository`.
    """
    base = (
        f"## Step: {current_agent_name}\n\n"
        f"### Original request\n{original_issue.strip()}\n\n"
        f"### Output from previous step ({previous_agent_name})\n"
        f"{previous_output.strip()}\n\n"
        f"Please continue the workflow using the previous output above as your "
        f"primary input, while keeping the original request in mind."
    )
    if repo_context and current_agent_name in REPO_CONTEXT_STEPS:
        return _inject_repo_context(base, repo_context)
    return base


def prepare_workflow_input(user_input: str | None) -> tuple[str, str]:
    """Turn raw CLI input (URL, free text, or ``None``) into pipeline input.

    Returns a tuple of ``(source_description, issue_text)``:
      * ``source_description`` is a human-readable label like
        ``github_issue:owner/repo#123`` or ``raw_text``, useful for logs and
        the banner printed before the workflow starts.
      * ``issue_text`` is the formatted string passed directly to the
        Requirements Analysis Agent as step 1 input.
    """
    return resolve_issue_input(user_input)


async def run_workflow(
    initial_input: str,
    *,
    repo_root: "os.PathLike[str] | str | None" = ".",
    repo_url: Optional[str] = None,
    issue_source: Optional[str] = None,
    report_output_dir: "Optional[os.PathLike[str] | str]" = ".",
    report_filename: str = DEFAULT_REPORT_FILENAME,
    write_report: bool = True,
) -> str:
    """Execute the sequential pipeline and return the final agent's output.

    Each agent's ``final_output`` becomes the next agent's input. Intermediate
    outputs are printed to stdout with a clear banner so the whole chain of
    work is observable. After the last step, ``report.md`` is written
    containing every agent's output.

    Parameters
    ----------
    initial_input:
        Fully formatted issue string (see :func:`prepare_workflow_input`).
    repo_root:
        Directory to scan for local repository context. Used only when
        ``repo_url`` is ``None``. The scan runs once before the step loop
        and the resulting snapshot is injected into the Coding and Review
        steps. Pass ``None`` to disable repository scanning entirely
        (useful for tests, short snippets, or fully offline environments
        where even file I/O should be avoided).
    repo_url:
        Public GitHub repository URL to clone into a temporary directory and
        scan. When provided, takes precedence over ``repo_root``. The clone
        is always cleaned up (tempdir removed) before this function returns,
        even on agent errors. On any parse/clone failure, the pipeline
        proceeds without repository context rather than failing hard.
    issue_source:
        Human-readable label describing where ``initial_input`` came from
        (e.g. ``"github_issue:o/r#1"``). Written into the report header; no
        effect on agent execution.
    report_output_dir:
        Directory where ``report.md`` will be written. Defaults to the
        current directory.
    report_filename:
        Name for the report file (default ``report.md``).
    write_report:
        Pass ``False`` to skip writing the report (useful for programmatic
        callers that already persist results elsewhere).
    """
    # Callers coming from prepare_workflow_input() already pass a fully
    # formatted issue string; store it so every downstream step can still
    # reference the original request.
    original_issue = initial_input

    # --- Optional repository scan (runs once, before any agent call) -------
    #
    # Priority:
    #   1. repo_url is set      -> clone GitHub repo to tempdir, scan it.
    #   2. repo_root is set     -> scan local directory.
    #   3. both None            -> skip repo analysis entirely.
    #
    # All failures in this block downgrade to "proceed without repo context"
    # so a bad URL or missing git CLI never kills the whole pipeline.
    repo_result: Optional[RepoScanResult] = None
    repo_context: Optional[str] = None
    repo_summary_for_report: Optional[str] = None
    cloned_ref: Optional[GitHubRepoRef] = None

    if repo_url is not None:
        # Prefer the GitHub URL path; wrap clone + scan together so the temp
        # dir is guaranteed cleaned up via the context manager.
        try:
            with with_cloned_github_repo(repo_url) as (ref, checkout_path):
                cloned_ref = ref
                repo_result = scan_repository(checkout_path)
                # Override the summary so the banner/report clearly indicate a
                # remote repo was analyzed, not the local cwd.
                remote_summary = (
                    f"Remote GitHub repo {ref.owner}/{ref.repo}"
                    + (f" @ {ref.ref}" if ref.ref else "")
                    + f": {repo_result.files_seen} source files"
                    + f" (truncated={repo_result.truncated})"
                )
                repo_context = repo_result.context
                repo_summary_for_report = remote_summary
                print(f"\n[Workflow] {remote_summary}")
        except GitHubRepoCloneError as exc:
            print(f"\n[Workflow] GitHub repository clone skipped: {exc}")
            repo_summary_for_report = f"github_repo skipped ({exc})"
            repo_result = None
            repo_context = None
        except RepoScanError as exc:
            print(f"\n[Workflow] Repository scan skipped: {exc}")
            repo_summary_for_report = f"github_repo scan skipped ({exc})"
            repo_result = None
            repo_context = None
    elif repo_root is not None:
        try:
            repo_result = scan_repository(repo_root)
        except RepoScanError as exc:
            print(f"\n[Workflow] Repository scan skipped: {exc}")
            repo_summary_for_report = f"skipped ({exc})"
            repo_result = None
            repo_context = None
        else:
            repo_context = repo_result.context
            repo_summary_for_report = repo_result.summary
            print(f"\n[Workflow] {repo_result.summary}")

    # If we cloned a remote repo successfully, expose its metadata to the
    # report writer via extra_metadata downstream.
    extra_report_metadata: List[Tuple[str, str]] = []
    if cloned_ref is not None:
        extra_report_metadata.append(("Repository", cloned_ref.html_url))
        if cloned_ref.ref:
            extra_report_metadata.append(("Checked out ref", cloned_ref.ref))

    # Per-step output capture for the Markdown report.
    captured_steps: List[Tuple[str, str]] = []

    current_input = original_issue
    previous_name = "Original request"

    for index, (step_name, agent) in enumerate(WORKFLOW, start=1):
        if index == 1:
            step_input = original_issue
            # Requirements agent analyses the issue text only; no project
            # context injected here even when available.
        else:
            step_input = build_step_input(
                current_agent_name=step_name,
                previous_agent_name=previous_name,
                previous_output=current_input,
                original_issue=original_issue,
                repo_context=repo_context,
            )

        result = await Runner.run(agent, step_input)
        current_output = result.final_output

        print(f"\n{'=' * _STEP_BANNER_WIDTH}")
        print(f"Step {index}/{len(WORKFLOW)}: {step_name}")
        print("=" * _STEP_BANNER_WIDTH)
        print(current_output)

        captured_steps.append((step_name, current_output))

        current_input = current_output
        previous_name = step_name

    # --- Write report.md ---------------------------------------------------
    if write_report and captured_steps:
        try:
            report_path = generate_and_write_report(
                steps=captured_steps,
                original_issue=original_issue,
                issue_source=issue_source,
                repo_scan_summary=repo_summary_for_report,
                extra_metadata=extra_report_metadata or None,
                output_dir=report_output_dir,
                filename=report_filename,
                overwrite=True,
            )
        except Exception as exc:  # noqa: BLE001 — never let report I/O fail the pipeline
            print(f"\n[Workflow] Report generation skipped: {exc}")
        else:
            print(f"\n[Workflow] Report written to: {report_path.as_posix()}")

    return current_input

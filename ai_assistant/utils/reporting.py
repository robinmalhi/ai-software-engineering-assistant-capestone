"""Markdown report generation for the multi-agent workflow.

Takes the raw outputs produced by each pipeline step and assembles a single
``report.md`` file suitable for sharing, archival, or follow-up review.

The module is intentionally pipeline-agnostic: it consumes plain Python
structures (an ordered list of ``(step_name, output)`` pairs plus optional
metadata like the original issue text, repo scan summary, etc.) rather than
importing workflow types. That keeps the report generator reusable for ad-hoc
runs and tests and avoids an import cycle back to :mod:`ai_assistant.workflow`.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepRecord:
    """One step's name and its agent-produced output string."""

    name: str
    output: str
    index: int


@dataclass
class WorkflowReport:
    """Everything needed to render the Markdown report.

    Only ``steps`` is mandatory; everything else is optional metadata that
    renders an informational section when present and is cleanly skipped
    otherwise.
    """

    steps: List[StepRecord] = field(default_factory=list)
    original_issue: Optional[str] = None
    issue_source: Optional[str] = None
    repo_scan_summary: Optional[str] = None
    generated_at: _dt.datetime = field(default_factory=_dt.datetime.now)
    extra_metadata: List[Tuple[str, str]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Builder helpers (kept tiny so callers don't have to reason about
    # the dataclass internals when assembling a report incrementally).
    # ------------------------------------------------------------------

    def add_step(self, name: str, output: str, index: Optional[int] = None) -> None:
        """Append a step record. ``index`` defaults to the next 1-based slot."""
        idx = index if index is not None else len(self.steps) + 1
        self.steps.append(StepRecord(name=name, output=output, index=idx))

    def add_metadata(self, label: str, value: str) -> None:
        self.extra_metadata.append((label, value))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _sanitize_anchor(name: str) -> str:
    """Return a GitHub-Flavored-Markdown-compatible anchor slug."""
    return (
        name.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
    )


def _render_metadata_block(report: WorkflowReport) -> str:
    """Render the top-of-file summary / metadata table."""
    lines: list[str] = [
        "## Run Summary",
        "",
        f"- **Generated at:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')} (local time)",
    ]
    if report.issue_source:
        lines.append(f"- **Input source:** {report.issue_source}")
    if report.repo_scan_summary:
        lines.append(f"- **Repository scan:** {report.repo_scan_summary}")
    for label, value in report.extra_metadata:
        lines.append(f"- **{label}:** {value}")

    # TOC: link to each step section
    if report.steps:
        lines.append("")
        lines.append("### Pipeline Steps")
        lines.append("")
        for step in report.steps:
            anchor = _sanitize_anchor(f"{step.index} {step.name}")
            lines.append(f"- [Step {step.index}: {step.name}](#{anchor})")

    return "\n".join(lines)


def _render_original_issue(text: str) -> str:
    """Render the user's issue input as a clearly delimited section."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    return (
        "\n\n## Original Issue\n\n"
        "<details>\n"
        "<summary>Show input passed to the Requirements Agent</summary>\n\n"
        f"{cleaned}\n\n"
        "</details>\n"
    )


def _render_step(step: StepRecord) -> str:
    """Render a single step's output under its own H2 heading.

    We wrap the output verbatim into a ``markdown`` fenced block only when
    the output would otherwise nest awkwardly against the surrounding H2.
    In practice most agents already produce Markdown, so we drop the fence
    and let headings render naturally, but we still add a clear delimiter
    so sections don't visually bleed together.
    """
    heading = f"## Step {step.index}: {step.name}"
    body = step.output.strip() if step.output else "_(agent produced no output)_"
    divider = "\n" + ("-" * 72) + "\n"
    return heading + "\n\n" + body + divider + "\n"


def render_report(report: WorkflowReport) -> str:
    """Render the complete Markdown document as a single string."""
    parts: list[str] = [
        "# AI Software Engineering Assistant — Workflow Report\n",
        _render_metadata_block(report),
    ]
    if report.original_issue:
        parts.append(_render_original_issue(report.original_issue))
    parts.append("\n")
    for step in report.steps:
        parts.append(_render_step(step))
    parts.append(
        "\n*End of report. Regenerated automatically after every successful "
        "workflow run.*\n"
    )
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# I/O helpers — these are the thin wrappers that actually touch the disk.
# Kept separate so render_report stays pure and unit-testable.
# ---------------------------------------------------------------------------


DEFAULT_REPORT_FILENAME: str = "report.md"


def write_report(
    content: str,
    *,
    output_dir: "str | os.PathLike[str] | None" = None,
    filename: str = DEFAULT_REPORT_FILENAME,
    overwrite: bool = True,
) -> Path:
    """Write *content* to ``<output_dir>/<filename>`` and return the path.

    * ``output_dir=None`` defaults to the current working directory.
    * Missing directories are created with ``parents=True, exist_ok=True``.
    * When ``overwrite=False`` and the file exists, a numbered suffix is
      appended (``report-2.md``, ``report-3.md``, …) up to 100 retries.
    """
    import os  # local import so render_report keeps zero file-I/O deps

    out_dir = Path(output_dir if output_dir is not None else os.getcwd()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem, ext = Path(filename).stem, Path(filename).suffix or ".md"
    candidate = out_dir / filename

    if not overwrite:
        for i in range(2, 101):
            if not candidate.exists():
                break
            candidate = out_dir / f"{stem}-{i}{ext}"
        else:
            raise RuntimeError(
                f"Could not find an unused filename under {out_dir} after 100 attempts."
            )

    candidate.write_text(content, encoding="utf-8")
    return candidate


def generate_and_write_report(
    steps: Sequence[Tuple[str, str]],
    *,
    original_issue: Optional[str] = None,
    issue_source: Optional[str] = None,
    repo_scan_summary: Optional[str] = None,
    extra_metadata: Optional[Iterable[Tuple[str, str]]] = None,
    output_dir: "Optional[str | os.PathLike[str]]" = None,
    filename: str = DEFAULT_REPORT_FILENAME,
    overwrite: bool = True,
) -> Path:
    """Convenience combo: build the :class:`WorkflowReport`, render it, and write.

    Parameters mirror the split between :class:`WorkflowReport` and
    :func:`write_report` so you can get the file written in a single call
    from the pipeline.
    """
    report = WorkflowReport(
        original_issue=original_issue,
        issue_source=issue_source,
        repo_scan_summary=repo_scan_summary,
        extra_metadata=list(extra_metadata or []),
    )
    for idx, (name, output) in enumerate(steps, start=1):
        report.add_step(name=name, output=output, index=idx)
    content = render_report(report)
    return write_report(
        content,
        output_dir=output_dir,
        filename=filename,
        overwrite=overwrite,
    )

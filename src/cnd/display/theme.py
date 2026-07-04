from collections import Counter
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from rich import box
from rich.console import Console, ConsoleOptions, ConsoleRenderable, Group, RenderResult
from rich.measure import Measurement
from rich.panel import Panel
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text

from cnd.core.manifest import CndManifest

# (color, badge) per node kind.
NODE_STYLE: dict[str, tuple[str, str]] = {
    "heading": ("blue", "H"),
    "paragraph": ("green", "P"),
    "table": ("magenta", "T"),
    "quote": ("yellow", "Q"),
    "code": ("bright_black", "C"),
    "math": ("cyan", "M"),
    "figure": ("bright_magenta", "Fg"),
    "list": ("bright_green", "L"),
}


def format_node_ref(node_id: UUID, label: str | None = None) -> str:
    """Human-readable cross-reference for display (label preferred)."""
    if label:
        return f"@{label}"
    return str(node_id)


def format_node_refs(refs: Sequence[Any]) -> str:
    """Format a sequence of node refs or raw UUIDs for display."""
    parts: list[str] = []
    for ref in refs:
        if hasattr(ref, "id"):
            parts.append(format_node_ref(ref.id, getattr(ref, "label", None)))
        else:
            parts.append(str(ref))
    return ", ".join(parts)


class ShareBar:
    """A bar that fills the whole cell width; the filled part is the share and
    the dim track always runs to the end so the 100% boundary stays visible."""

    def __init__(self, fraction: float, color: str, max_width: int = 40) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._color = color
        self._max_width = max_width

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = max(1, min(options.max_width, self._max_width))
        filled = max(1, round(self._fraction * width))
        filled = min(filled, width)
        track = width - filled
        yield Segment("█" * filled, Style.parse(self._color))
        if track:
            yield Segment("░" * track, Style.parse("grey30"))

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(4, min(options.max_width, self._max_width))


def kv_line(fields: Sequence[tuple[str, str]]) -> Text:
    line = Text()
    for index, (key, value) in enumerate(fields):
        if index:
            line.append("   ·   ", "dim")
        line.append(f"{key}=", "dim")
        line.append(value, "cyan")
    return line


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


def format_preview(text: str, *, max_len: int, truncate_text: bool) -> str:
    if not truncate_text:
        return text
    return truncate(text, max_len)


def stat_cell(label: str, value: str) -> Text:
    cell = Text()
    cell.append(f"{label}\n", "dim")
    cell.append(value, "bold white")
    return cell


def document_panel(manifest: CndManifest) -> Panel:
    doc = manifest.doc
    doc_table = Table.grid(expand=True)
    doc_table.add_column(style="dim", ratio=1)
    doc_table.add_column(style="white", ratio=3)
    doc_table.add_row("title", doc.title)
    doc_table.add_row("version", f"v{manifest.cnd_version}")
    doc_table.add_row("doc_hash", manifest.doc_hash)
    if doc.lang:
        doc_table.add_row("lang", doc.lang)
    if doc.authors:
        doc_table.add_row("authors", ", ".join(doc.authors))
    return Panel(
        doc_table,
        title="[bold]Document[/]",
        border_style="blue",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def options_panel(title: str, rows: Sequence[tuple[str, str]]) -> Panel:
    stats = Table.grid(expand=True)
    stats.add_column(style="dim")
    stats.add_column(style="white")
    for key, value in rows:
        stats.add_row(key, value)
    return Panel(
        stats,
        title=f"[bold]{title}[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def legend_panel(
    styles: dict[str, tuple[str, str]],
    *,
    title: str = "Legend",
) -> Panel:
    legend = Table.grid(expand=True, padding=(0, 2))
    legend.add_column(width=5)
    legend.add_column(style="white")
    for kind, (color, badge) in styles.items():
        legend.add_row(
            f"[bold black on {color}] {badge} [/]",
            f"[bold {color}]{kind.upper()}[/]",
        )
    return Panel(
        legend,
        title=f"[bold]{title}[/]",
        border_style="bright_black",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def summary_panel(
    title: str,
    counts: Counter[str],
    style_map: dict[str, tuple[str, str]],
    stats: Sequence[tuple[str, str]],
) -> Panel:
    total = sum(counts.values())
    divisor = total or 1

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE_HEAVY,
        expand=True,
        pad_edge=False,
    )
    table.add_column("Composition", no_wrap=True)
    table.add_column("Count", justify="right")
    table.add_column("Share", justify="right", style="dim")
    table.add_column("Distribution", ratio=1)

    for kind, count in sorted(counts.items()):
        color, badge = style_map.get(kind, ("white", "?"))
        fraction = count / divisor
        table.add_row(
            f"[bold black on {color}] {badge} [/]  [bold {color}]{kind}[/]",
            str(count),
            f"{fraction * 100:.1f}%",
            ShareBar(fraction, color),
        )

    stats_grid = Table.grid(expand=True, padding=(0, 3))
    for _ in stats:
        stats_grid.add_column(justify="left", ratio=1)
    stats_grid.add_row(*[stat_cell(label, value) for label, value in stats])

    body = Group(table, Text(""), stats_grid)
    return Panel(
        body,
        title=f"[bold]{title}[/]",
        title_align="left",
        border_style="bright_black",
        box=box.ROUNDED,
        padding=(1, 2),
        expand=True,
    )


def typed_panel(
    kind: str,
    style_map: dict[str, tuple[str, str]],
    body_parts: list[ConsoleRenderable],
) -> Panel:
    color, badge = style_map.get(kind, ("white", "?"))
    panel_title = Text.assemble(
        (f" {badge} ", f"bold black on {color}"),
        ("  ", ""),
        (kind.upper(), f"bold {color}"),
    )
    return Panel(
        Group(*body_parts),
        title=panel_title,
        title_align="left",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
        expand=False,
    )


def print_header_grid(console: Console, panels: list[Panel]) -> None:
    grid = Table.grid(expand=True, padding=(0, 1))
    for _ in panels:
        grid.add_column(ratio=1)
    grid.add_row(*panels)
    console.print(grid)

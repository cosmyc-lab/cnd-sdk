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

from cnd.core.cnd import Cnd

# (color, badge) per node kind — a categorical palette of 10 hue-separated
# truecolor flags for a dark terminal (OKLCH L 0.48-0.67, chroma >= 0.10,
# >= 3:1 on a dark surface); legend/summary row adjacency checked with the
# dataviz palette validator. Order is alphabetical EXCEPT image and quote are
# swapped in row position: after the image<->quote color swap, olive-quote sat
# next to amber-table (near-identical under protanopia); swapping their rows
# moves olive clear of both amber and green so every adjacent pair stays
# distinct. Legend and summary both follow this dict order.
NODE_STYLE: dict[str, tuple[str, str]] = {
    "code": ("#00a3c4", "C"),
    "figure": ("#d95926", "Fg"),
    "heading": ("#8a55f2", "H"),
    "quote": ("#8a8c1a", "Q"),
    "list": ("#9085e9", "L"),
    "math": ("#e66767", "M"),
    "paragraph": ("#008300", "P"),
    "image": ("#c94fb4", "Im"),
    "table": ("#c98500", "T"),
    "terms": ("#199e70", "D"),
}

# Chrome: the header menu panels (Document, Render options, Legend) wear the
# blue frame — blue is the chrome identity, which is why the heading flag is
# magenta, not blue. Node panels and the summary keep a quiet neutral gray
# so the categorical flags stay the only vivid elements in the tree.
CHROME_BORDER = "#3987e5"
NEUTRAL_BORDER = "#898781"

# Widest badge is 2 chars ("Fg"/"Im"); every chip pads to this width so kind
# labels after a chip always start in the same column.
_BADGE_WIDTH = 2


def badge_foreground(color: str) -> str:
    """Ink for a badge letter on its colored chip, picked per chip by
    luminance so the letter always contrasts (dark ink on light chips,
    light ink on dark chips). Non-hex (named) colors fall back to black
    ink — the only named chip color is the white unknown-kind fallback."""
    if not color.startswith("#") or len(color) != 7:
        return "black"

    def _lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * _lin(int(color[1:3], 16))
        + 0.7152 * _lin(int(color[3:5], 16))
        + 0.0722 * _lin(int(color[5:7], 16))
    )
    # Dark ink wins iff its WCAG contrast beats white ink's:
    # (L+0.05)/0.05 > 1.05/(L+0.05)  <=>  L > sqrt(0.0525) - 0.05.
    return "#0d0d0d" if luminance > 0.179 else "#ffffff"


def badge_chip(color: str, badge: str) -> str:
    """Markup for a uniform-width badge chip with contrast-safe lettering."""
    return f"[bold {badge_foreground(color)} on {color}] {badge:<{_BADGE_WIDTH}} [/]"


def format_node_ref(label: str) -> str:
    """Human-readable cross-reference for display."""
    return f"@{label}"


def format_node_refs(refs: Sequence[Any]) -> str:
    """Format a sequence of link edges, or bare labels, for display."""
    parts: list[str] = []
    for ref in refs:
        label = getattr(ref, "label", ref)
        parts.append(format_node_ref(str(label)))
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


def document_panel(cnd: Cnd) -> Panel:
    doc = cnd.doc
    doc_table = Table.grid(expand=True)
    doc_table.add_column(style="dim", ratio=1)
    doc_table.add_column(style="white", ratio=3)
    doc_table.add_row("title", doc.title)
    doc_table.add_row("version", f"v{cnd.cnd_version}")
    doc_table.add_row("paginated", "yes" if cnd.paginated else "no")
    if cnd.source:
        doc_table.add_row("source", f"{cnd.source.type}   {cnd.source.hash}")
    if doc.lang:
        doc_table.add_row("lang", doc.lang)
    if doc.authors:
        doc_table.add_row("authors", ", ".join(doc.authors))
    return Panel(
        doc_table,
        title="[bold]Document[/]",
        border_style=CHROME_BORDER,
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
        border_style=CHROME_BORDER,
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
            badge_chip(color, badge),
            f"[bold {color}]{kind.upper()}[/]",
        )
    return Panel(
        legend,
        title=f"[bold]{title}[/]",
        border_style=CHROME_BORDER,
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

    known = [(k, counts[k]) for k in style_map if k in counts]
    extra = sorted((k, c) for k, c in counts.items() if k not in style_map)
    for kind, count in known + extra:
        color, badge = style_map.get(kind, ("white", "?"))
        fraction = count / divisor
        table.add_row(
            f"{badge_chip(color, badge)}  [bold {color}]{kind}[/]",
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
        border_style=CHROME_BORDER,
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
        (f" {badge:<{_BADGE_WIDTH}} ", f"bold {badge_foreground(color)} on {color}"),
        ("  ", ""),
        (kind.upper(), f"bold {color}"),
    )
    return Panel(
        Group(*body_parts),
        title=panel_title,
        title_align="left",
        border_style=NEUTRAL_BORDER,
        box=box.ROUNDED,
        padding=(1, 2),
        expand=False,
    )


def pool_panel(title: str, rows: Sequence[tuple[str, str, str]]) -> Panel:
    """Panel listing out-of-tree pool entries: (label, body, meta) rows."""
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(style="white", ratio=1)
    grid.add_column(style="dim", no_wrap=True, justify="right")
    for label, body, meta in rows:
        grid.add_row(label, body, meta)
    return Panel(
        grid,
        title=f"[bold]{title}[/]",
        title_align="left",
        border_style=CHROME_BORDER,
        box=box.ROUNDED,
        padding=(1, 2),
        expand=True,
    )


def print_header_grid(console: Console, panels: list[Panel]) -> None:
    grid = Table.grid(expand=True, padding=(0, 1))
    for _ in panels:
        grid.add_column(ratio=1)
    grid.add_row(*panels)
    console.print(grid)

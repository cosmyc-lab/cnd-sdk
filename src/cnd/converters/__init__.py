"""Outbound converters — a whole CND to a complete document artifact.

See ``cnd.converters.base`` for the layer split and
docs/proposals/0007 for the design. Zero-dependency, like the core: this
package must not import ``rich`` or any other optional extra.
"""

from cnd.converters.base import (
    CndConverter,
    ConversionResult,
    ResolvedMarker,
    iter_body,
    resolve_markers,
)
from cnd.converters.html import HtmlConverter, HtmlNodeRenderer
from cnd.converters.markdown import MarkdownConverter, format_bib_entry

__all__ = [
    "CndConverter",
    "ConversionResult",
    "HtmlConverter",
    "HtmlNodeRenderer",
    "MarkdownConverter",
    "ResolvedMarker",
    "format_bib_entry",
    "iter_body",
    "resolve_markers",
]

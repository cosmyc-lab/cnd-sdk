"""Which URLs a renderer may emit as a link target or an image source.

A CND carries an ``href`` (``LinkRef``) or an image ``path`` as the
producer wrote it. A renderer that turns one into a live link must not
hand a reader ``javascript:`` or another scheme that runs code, so every
renderer asks the same question here.
"""

import re

__all__ = ["is_safe_url"]

SAFE_SCHEMES = frozenset({"http", "https", "mailto"})
"""Schemes a renderer may link to; a URL without a scheme is relative."""

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
_LEADING = re.compile(r"^[\x00-\x20]+")
_TAB_OR_NEWLINE = re.compile(r"[\t\n\r]")


def _normalized(url: str) -> str:
    """``url`` as a browser reads its scheme: leading C0 controls and
    spaces stripped, every tab and newline removed (WHATWG URL)."""
    return _TAB_OR_NEWLINE.sub("", _LEADING.sub("", url))


def url_scheme(url: str) -> str | None:
    """The lower-cased scheme of ``url``, or ``None`` when it has none (a
    relative path, a fragment, a query)."""
    match = _SCHEME.match(_normalized(url))
    return match.group(1).lower() if match else None


def is_safe_url(url: str) -> bool:
    """Whether ``url`` may become a link target: its scheme is ``http``,
    ``https`` or ``mailto`` (any case), or it has no scheme at all."""
    scheme = url_scheme(url)
    return scheme is None or scheme in SAFE_SCHEMES

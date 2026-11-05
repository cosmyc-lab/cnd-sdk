"""Which URLs a renderer may emit as a link target or an image source.

A CND carries an ``href`` (``LinkRef``) or an image ``path`` as the
producer wrote it. A renderer that turns one into a live link must not
hand a reader ``javascript:`` or another scheme that runs code, so every
renderer asks the same question here.
"""

import re
from collections.abc import Iterable

__all__ = ["allowed_link_schemes", "is_safe_image_source", "is_safe_url"]

SAFE_SCHEMES = frozenset({"http", "https", "mailto"})
"""Schemes a renderer may link to; a URL without a scheme is relative."""

NEVER_LINKED_SCHEMES = frozenset({"javascript", "vbscript", "data"})
"""Schemes that run code or embed a document: no caller may allow them
(``allowed_link_schemes``), and ``is_safe_url`` refuses them even when
they are passed."""

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
_SCHEME_NAME = re.compile(r"[a-z][a-z0-9+.\-]*")
_LEADING = re.compile(r"^[\s\x00-\x20\ufeff]+")
_TAB_OR_NEWLINE = re.compile(r"[\t\n\r]")


def _normalized(url: str) -> str:
    """``url`` as its most lenient reader reads its scheme: leading C0
    controls and every leading Unicode whitespace (and a BOM) stripped,
    as a browser strips the first and a Markdown parser or a ``trim()``
    the second; every tab and newline removed (WHATWG URL). Stripping
    more than one reader does only makes the check stricter."""
    return _TAB_OR_NEWLINE.sub("", _LEADING.sub("", url))


def url_scheme(url: str) -> str | None:
    """The lower-cased scheme of ``url``, or ``None`` when it has none (a
    relative path, a fragment, a query)."""
    match = _SCHEME.match(_normalized(url))
    return match.group(1).lower() if match else None


def allowed_link_schemes(schemes: Iterable[str]) -> frozenset[str]:
    """The extra schemes a caller allows a renderer to link to, checked.

    A consumer that resolves an application scheme of its own allows it
    here (spec §8, "URL rule"). Schemes match in any case, so names are
    lower-cased. A name that is not a scheme (RFC 3986: a letter, then
    letters, digits, ``+``, ``-`` or ``.``), or one of
    ``NEVER_LINKED_SCHEMES``, raises ``ValueError``; a bare string, which
    would be read one character at a time, raises ``TypeError``."""
    if isinstance(schemes, str):
        raise TypeError("allowed_link_schemes takes a collection of scheme names, not one string")
    allowed: set[str] = set()
    for scheme in schemes:
        name = scheme.lower() if isinstance(scheme, str) else None
        if name is None or not _SCHEME_NAME.fullmatch(name):
            raise ValueError(f"not a URL scheme name: {scheme!r}")
        if name in NEVER_LINKED_SCHEMES:
            raise ValueError(f"the {name!r} scheme can never become a link")
        allowed.add(name)
    return frozenset(allowed)


def is_safe_url(url: str, extra_schemes: frozenset[str] = frozenset()) -> bool:
    """Whether ``url`` may become a link target: its scheme is ``http``,
    ``https`` or ``mailto`` (any case), or one of ``extra_schemes`` (the
    result of ``allowed_link_schemes``), or it has no scheme at all. A
    scheme of ``NEVER_LINKED_SCHEMES`` is refused whatever the caller
    passes."""
    if isinstance(extra_schemes, str):
        raise TypeError("extra_schemes is a set of scheme names, not one string")
    scheme = url_scheme(url)
    if scheme is None or scheme in SAFE_SCHEMES:
        return True
    return scheme in extra_schemes and scheme not in NEVER_LINKED_SCHEMES


def is_safe_image_source(path: str) -> bool:
    """Whether ``path`` may become an image ``src``: a safe URL
    (``is_safe_url``) or an inline ``data:image/…`` URI."""
    return is_safe_url(path) or _normalized(path).lower().startswith("data:image/")

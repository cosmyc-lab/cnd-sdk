"""Escaping free text for CommonMark/GFM output.

A CND carries plain text. Written into Markdown unescaped, that text can
change the document's structure: a paragraph reading ``1. Keep`` becomes
a list, ``<name>`` becomes inline HTML, ``*`` becomes emphasis. These
helpers escape exactly the characters that would start such syntax, and
leave the rest readable (an intraword ``_`` or a backslash before a
letter stays as written).
"""

import re

_ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_ALWAYS = set("*`[]~")
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_HEADING = re.compile(r"^( {0,3})(#{1,6})(?=[ \t]|$)")
_QUOTE = re.compile(r"^( {0,3})>")
_BULLET = re.compile(r"^( {0,3})([-+])(?=[ \t]|$)")
_ORDERED = re.compile(r"^( {0,3})(\d{1,9})([.)])(?=[ \t]|$)")
_UNDERLINE = re.compile(r"^( {0,3})(=+|-+)[ \t]*$")
_DASH_BREAK = re.compile(r"^( {0,3})(?:-[ \t]*){3,}$")


def escape_inline(text: str) -> str:
    """Escape characters that start inline syntax anywhere in a line."""
    out: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < n else ""
        prev = text[i - 1] if i > 0 else ""
        if ch == "\\":
            out.append("\\\\" if not nxt or nxt in _ASCII_PUNCT or nxt in "\r\n" else "\\")
        elif ch in _ALWAYS:
            out.append("\\" + ch)
        elif ch == "_":
            out.append("_" if prev.isalnum() and nxt.isalnum() else "\\_")
        elif ch == "<":
            out.append("\\<" if nxt and (nxt.isascii() and nxt.isalpha() or nxt in "/!?") else "<")
        elif ch == "&":
            out.append("\\&" if _ENTITY.match(text, i) else "&")
        else:
            out.append(ch)
    return "".join(out)


def _escape_line_start(line: str) -> str:
    if m := _HEADING.match(line):
        return f"{m.group(1)}\\{line[len(m.group(1)):]}"
    if m := _QUOTE.match(line):
        return f"{m.group(1)}\\{line[len(m.group(1)):]}"
    if m := _BULLET.match(line):
        return f"{m.group(1)}\\{line[len(m.group(1)):]}"
    if m := _ORDERED.match(line):
        cut = len(m.group(1)) + len(m.group(2))
        return f"{line[:cut]}\\{line[cut:]}"
    if m := _UNDERLINE.match(line) or _DASH_BREAK.match(line):
        return f"{m.group(1)}\\{line[len(m.group(1)):]}"
    return line


def escape_block(text: str) -> str:
    """``escape_inline`` plus a block marker at the start of any line."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(_escape_line_start(line) for line in escape_inline(text).split("\n"))

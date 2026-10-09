"""The Markdown export parses back to the CND's structure (CommonMark + GFM tables).

Each case is a failure seen on real documents: a code block containing
fences swallowing the rest of the document, ordered lists renumbered,
paragraphs read as lists/HTML/emphasis, pipes adding table columns,
quotes read as paragraphs, image paths with spaces.
"""

from datetime import datetime, timezone
from uuid import uuid4

from markdown_it import MarkdownIt

from cnd.converters import MarkdownConverter
from cnd.core.cnd import Cnd, DocMetadata
from cnd.core.nodes import (
    CodeNode, HeadingNode, ImageNode, ListItem, ListNode, ParagraphNode,
    QuoteNode, TableCell, TableNode,
)

NESTED_FENCE_CODE = "# Skill\n\n```typ\n#set page()\n```\n\n## Layout\n\n````\nend"


def _id() -> dict:
    return {"id": uuid4()}


def _heading(level: int, text: str, children: list, number: str | None = None) -> HeadingNode:
    return HeadingNode(type="heading", level=level, text=text, number=number,
                       heading_path=[text], children=children, **_id())


def _document() -> Cnd:
    task2 = _heading(2, "Task two", [
        CodeNode(type="code", text=NESTED_FENCE_CODE, lang="markdown", **_id()),
    ], number="1.2")
    task3 = _heading(2, "Task three", [
        ParagraphNode(type="paragraph", text="1. Keep the default folders", **_id()),
        ParagraphNode(type="paragraph", text="Output: <name> — created|updated (<reason>)", **_id()),
        ParagraphNode(type="paragraph", text="Globs: docs/**/*.md and my_var_name", **_id()),
        ListNode(type="list", ordered=True, items=[
            ListItem(text="first", number=1), ListItem(text="third", number=3),
        ], **_id()),
        TableNode(type="table", cells=[
            TableCell(row=0, col=0, text="Call", is_header=True),
            TableCell(row=0, col=1, text="Meaning", is_header=True),
            TableCell(row=1, col=0, text='badge(kind: "ok" | "warn")'),
            TableCell(row=1, col=1, text="status"),
        ], **_id()),
        QuoteNode(type="quote", text="Ship it.\n- not a bullet", attribution="A reviewer", **_id()),
        ImageNode(type="image", path="team logo.png", alt="Team logo", **_id()),
    ], number="1.3")
    root = _heading(1, "Plan", [task2, task3], number="1")
    return Cnd(cnd_version="0.4.0", built_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
               doc=DocMetadata(title="Structure check", authors=[]), nodes=[root])


def _tokens():
    text = MarkdownConverter().convert(_document()).text
    body = text.split("\n---\n", 1)[1]  # drop the YAML front matter
    return MarkdownIt("commonmark").enable("table").parse(body)


def _all(tokens):
    for tok in tokens:
        yield tok
        yield from _all(tok.children or [])


def test_headings_survive_a_code_block_holding_fences() -> None:
    tokens = _tokens()
    headings = [tokens[i + 1].content for i, t in enumerate(tokens) if t.type == "heading_open"]
    assert headings == ["1 Plan", "1.2 Task two", "1.3 Task three"]


def test_code_block_is_one_fence_with_its_full_text() -> None:
    fences = [t for t in _tokens() if t.type == "fence"]
    assert len(fences) == 1
    assert fences[0].content.rstrip("\n") == NESTED_FENCE_CODE


def test_no_text_turns_into_html_or_emphasis() -> None:
    kinds = {t.type for t in _all(_tokens())}
    assert "html_inline" not in kinds and "html_block" not in kinds
    assert "em_open" not in kinds and "strong_open" not in kinds


def test_paragraph_starting_with_a_number_stays_a_paragraph() -> None:
    tokens = _tokens()
    ordered = [t for t in tokens if t.type == "ordered_list_open"]
    assert len(ordered) == 1  # only the real list
    inline = [t.content for t in tokens if t.type == "inline"]
    assert any(c.startswith("1\\. Keep") for c in inline)


def test_ordered_list_keeps_its_numbers_in_the_text() -> None:
    text = MarkdownConverter().convert(_document()).text
    assert "1. first\n3. third" in text


def test_table_row_keeps_its_column_count() -> None:
    rows, current = [], 0
    for t in _tokens():
        if t.type == "tr_open":
            current = 0
        elif t.type in ("td_open", "th_open"):
            current += 1
        elif t.type == "tr_close":
            rows.append(current)
    assert rows == [2, 2]


def test_quote_is_a_blockquote_and_its_dash_line_is_not_a_list() -> None:
    tokens = _tokens()
    assert len([t for t in tokens if t.type == "blockquote_open"]) == 1
    assert not any(t.type == "bullet_list_open" for t in tokens)
    start = next(i for i, t in enumerate(tokens) if t.type == "blockquote_open")
    end = next(i for i, t in enumerate(tokens) if t.type == "blockquote_close")
    inside = [t.content for t in tokens[start:end] if t.type == "inline"]
    assert any("A reviewer" in c for c in inside)  # attribution stays in the quote


def test_image_with_a_space_in_its_path_is_an_image() -> None:
    images = [t for t in _all(_tokens()) if t.type == "image"]
    assert [i.attrs["src"] for i in images] == ["team%20logo.png"]


def test_nested_ordered_list_parses_as_two_lists() -> None:
    node = ListNode(type="list", ordered=True, items=[
        ListItem(text="a", children=[ListItem(text="a1"), ListItem(text="a2")]),
        ListItem(text="b"),
    ], **_id())
    cnd = Cnd(cnd_version="0.4.0", built_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
              doc=DocMetadata(title="Nested", authors=[]), nodes=[node])
    body = MarkdownConverter().convert(cnd).text.split("\n---\n", 1)[1]
    tokens = MarkdownIt("commonmark").enable("table").parse(body)
    assert len([t for t in tokens if t.type == "ordered_list_open"]) == 2


def _paragraph_tokens(text: str):
    node = ParagraphNode(type="paragraph", text=text, **_id())
    cnd = Cnd(cnd_version="0.4.0", built_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
              doc=DocMetadata(title="Para", authors=[]), nodes=[node])
    body = MarkdownConverter().convert(cnd).text.split("\n---\n", 1)[1]
    return list(_all(MarkdownIt("commonmark").enable("table").parse(body)))


def test_backslash_before_a_newline_is_not_a_hard_break() -> None:
    kinds = [t.type for t in _paragraph_tokens("C:\\\nnext")]
    assert "hardbreak" not in kinds and "softbreak" in kinds


"""Small constructors shared by the 0.5 test modules."""

from cnd.core.text import RichText


def rt(value: str, **kwargs) -> RichText:
    """A RichText from a string, the shorthand every test needs."""
    return RichText(value=value, **kwargs)

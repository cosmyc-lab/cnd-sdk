import pytest

from cnd.core.nodes import NodeLocation


def _loc(span: int, *, page: int = 1) -> NodeLocation:
    return NodeLocation(
        page=page,
        span=span,
        page_span=span,
        parent_span=0,
        span_count=1,
    )


class TestNodeLocationOrdering:
    def test_orders_by_span_only(self) -> None:
        early = _loc(1, page=1)
        late = _loc(2, page=2)

        assert early < late
        assert late > early
        assert early <= late
        assert late >= early

    def test_same_span_is_not_less_than(self) -> None:
        left = _loc(3, page=1)
        right = _loc(3, page=2)

        assert not (left < right)
        assert not (right < left)

    def test_min_max(self) -> None:
        locations = [_loc(3), _loc(1), _loc(2)]

        assert min(locations) == _loc(1)
        assert max(locations) == _loc(3)

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError):
            min([])

        with pytest.raises(ValueError):
            max([])

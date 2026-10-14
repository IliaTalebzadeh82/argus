import pytest

from argus.events.kafka_lag import PartitionLag


def test_zero_and_positive_lag():
    assert PartitionLag.from_offsets(0, 0, 20, 20).pending_records == 0
    assert PartitionLag.from_offsets(0, 0, 20, 17).pending_records == 3


def test_no_commit_keeps_explicit_state_and_uses_retained_low():
    result = PartitionLag.from_offsets(2, 4, 20, None)
    assert result.committed_offset is None
    assert result.pending_records == 16


@pytest.mark.parametrize(
    "low,high,committed", [(0, 20, 21), (4, 20, 3), (-1, 20, None), (3, 2, None)]
)
def test_invalid_offsets_fail(low, high, committed):
    with pytest.raises(ValueError, match="invalid offsets"):
        PartitionLag.from_offsets(0, low, high, committed)

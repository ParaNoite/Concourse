"""CLI 时间简写解析测试。"""

from datetime import timezone
import pytest
from concourse.cli import parse_shorthand


def test_plus_suffix():
    dt = parse_shorthand("1028+")
    assert dt.month == 10
    assert dt.day == 28
    assert dt.hour == 15  # 23:59 CST = 15:59 UTC
    assert dt.minute == 59
    assert dt.tzinfo == timezone.utc


def test_minus_suffix():
    dt = parse_shorthand("1028-")
    assert dt.month == 10
    assert dt.day == 27  # 00:00 CST = 前一天 16:00 UTC
    assert dt.hour == 16
    assert dt.tzinfo == timezone.utc


def test_iso_passthrough():
    dt = parse_shorthand("2026-11-01T12:00:00+00:00")
    assert dt.year == 2026
    assert dt.month == 11


def test_bare_digits_rejected():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        parse_shorthand("1028")


def test_invalid_format():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        parse_shorthand("abc+")

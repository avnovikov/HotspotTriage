"""Tests for dashboard cache include/exclude filter composition."""

from hotspottriage.dashboard.cache_filter_fields import (
    compose_filter_from_fields,
    split_filter_for_fields,
)


def test_split_empty():
    assert split_filter_for_fields("") == ("", "")
    assert split_filter_for_fields("  ") == ("", "")


def test_split_include_only():
    assert split_filter_for_fields("src/**,*.py") == ("src/**,*.py", "")


def test_split_mixed():
    assert split_filter_for_fields("src/**,!**/tests/**") == ("src/**", "**/tests/**")


def test_compose_empty():
    assert compose_filter_from_fields("", "") is None


def test_compose_exclude_only():
    assert compose_filter_from_fields("", "**/tests/**") == "!**/tests/**"


def test_compose_include_and_exclude():
    assert compose_filter_from_fields("src/**", "**/tests/**") == "src/**,!**/tests/**"


def test_compose_preserves_leading_bang_in_exclude_field():
    assert compose_filter_from_fields("", "!foo") == "!foo"


def test_round_trip():
    combined = "a/**,!b/**"
    inc, exc = split_filter_for_fields("./a/**,!b/**")
    assert inc == "a/**"
    assert exc == "b/**"
    assert compose_filter_from_fields(inc, exc) == combined


def test_compose_strips_dot_slash():
    assert compose_filter_from_fields("./src/**", "./tests/**") == "src/**,!tests/**"

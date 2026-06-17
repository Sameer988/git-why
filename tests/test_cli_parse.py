import click
import pytest

from git_why.cli import parse_target


def test_parse_target_file_only():
    assert parse_target("src/auth.py") == ("src/auth.py", None, None)


def test_parse_target_single_line():
    assert parse_target("src/auth.py:42") == ("src/auth.py", 42, 42)


def test_parse_target_range():
    assert parse_target("src/auth.py:42-60") == ("src/auth.py", 42, 60)


def test_parse_target_windows_path_file_only():
    assert parse_target("C:\\repo\\src\\auth.py") == ("C:\\repo\\src\\auth.py", None, None)


def test_parse_target_windows_path_with_line():
    assert parse_target("C:\\repo\\src\\auth.py:42") == ("C:\\repo\\src\\auth.py", 42, 42)


def test_parse_target_invalid_empty():
    with pytest.raises(click.BadParameter):
        parse_target("")


def test_parse_target_invalid_line():
    with pytest.raises(click.BadParameter):
        parse_target("src/auth.py:nope")


def test_parse_target_invalid_range():
    with pytest.raises(click.BadParameter):
        parse_target("src/auth.py:60-42")

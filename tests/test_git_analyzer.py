from git_why.git_analyzer import get_file_content, read_target_lines


def test_get_file_content_strips_utf8_bom(tmp_path):
    path = tmp_path / "auth.py"
    path.write_text("\ufeffdef check():\n    return True\n", encoding="utf-8")

    content = get_file_content(str(path), None, None, context=8)

    assert "\ufeff" not in content
    assert "def check()" in content


def test_get_file_content_marks_target_line_with_arrow(tmp_path):
    path = tmp_path / "auth.py"
    path.write_text("def check():\n    return True\n", encoding="utf-8")

    content = get_file_content(str(path), 2, 2, context=0)

    assert "\u2192" in content
    assert "return True" in content


def test_read_target_lines_returns_raw_lines_with_highlight_set(tmp_path):
    path = tmp_path / "auth.py"
    path.write_text("def check():\n    return True\n    return False\n", encoding="utf-8")

    lines, start_line, highlighted = read_target_lines(str(path), 2, 2, context=1)

    assert start_line == 1
    assert lines == ["def check():", "    return True", "    return False"]
    assert highlighted == {2}


def test_read_target_lines_whole_file_has_no_highlight(tmp_path):
    path = tmp_path / "auth.py"
    path.write_text("a = 1\nb = 2\n", encoding="utf-8")

    lines, start_line, highlighted = read_target_lines(str(path), None, None, context=8)

    assert start_line == 1
    assert lines == ["a = 1", "b = 2"]
    assert highlighted == set()


def test_get_file_content_handles_binary_file_gracefully(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(bytes(range(256)))

    # Whole-file mode should not crash or dump raw bytes.
    content = get_file_content(str(path), None, None, context=8)
    assert "binary file" in content.lower()

    # Line-range mode must not explode with a misleading "has N lines" error
    # just because the binary placeholder is a single line.
    content_ranged = get_file_content(str(path), 42, 42, context=8)
    assert "binary file" in content_ranged.lower()


def test_read_target_lines_handles_binary_file_gracefully(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(bytes(range(256)))

    lines, start_line, highlighted = read_target_lines(str(path), 42, 42, context=8)
    assert any("binary file" in line.lower() for line in lines)
    assert start_line == 1
    assert highlighted == set()

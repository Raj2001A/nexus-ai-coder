import pytest

from backend.tools import file_ops


def test_validate_path_allows_project_child(active_project):
    resolved = file_ops._validate_path("src/main.py")

    assert resolved == (active_project / "src" / "main.py").resolve()


def test_validate_path_rejects_escape(active_project):
    with pytest.raises(PermissionError):
        file_ops._validate_path("../outside.py")


def test_write_and_read_file_content(active_project):
    write_result = file_ops.write_file_content("pkg/example.py", "print('ok')\n")
    read_result = file_ops.read_file_content("pkg/example.py")

    assert write_result["success"] is True
    assert read_result["success"] is True
    assert "print('ok')" in read_result["raw_content"]


def test_replace_file_content_updates_expected_snippet(active_project):
    target = active_project / "pkg" / "example.py"
    target.parent.mkdir()
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")

    result = file_ops.replace_file_content(
        "pkg/example.py",
        "return 'old'",
        "return 'new'",
    )

    assert result["success"] is True
    assert "return 'new'" in target.read_text(encoding="utf-8")
    assert result["operation"] == "patch_replace"
    assert "--- a/pkg/example.py" in result["diff_preview"]


def test_replace_file_lines_updates_target_range(active_project):
    target = active_project / "pkg" / "service.py"
    target.parent.mkdir()
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")

    result = file_ops.replace_file_lines("pkg/service.py", 2, 3, "updated2\nupdated3")

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "line1\nupdated2\nupdated3\n"
    assert result["operation"] == "patch_lines"

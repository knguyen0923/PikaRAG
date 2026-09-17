from scripts.check_pinned_deps import find_undocumented_pins


def test_pin_with_preceding_comment_is_documented():
    lines = ["# Pinned because of reasons.", "requests==2.32.5"]
    assert find_undocumented_pins(lines) == []


def test_pin_with_no_preceding_comment_is_flagged():
    lines = ["requests==2.32.5"]
    assert find_undocumented_pins(lines) == ["requests==2.32.5"]


def test_pin_preceded_by_blank_line_is_flagged():
    lines = ["# Some unrelated comment.", "", "requests==2.32.5"]
    assert find_undocumented_pins(lines) == ["requests==2.32.5"]


def test_unpinned_line_is_ignored():
    lines = ["requests>=2.32.5"]
    assert find_undocumented_pins(lines) == []


def test_multiple_documented_pins_all_pass():
    lines = [
        "# Reason one.",
        "requests==2.32.5",
        "# Reason two.",
        "pytest==8.3.3",
    ]
    assert find_undocumented_pins(lines) == []


def test_real_requirements_file_has_no_undocumented_pins():
    from pathlib import Path

    lines = (
        (Path(__file__).resolve().parent.parent / "requirements.txt")
        .read_text()
        .splitlines()
    )
    assert find_undocumented_pins(lines) == []

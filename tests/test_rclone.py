"""Unit tests for copy_tool.rclone helpers — pure, no Qt required."""

from copy_tool import rclone


# --- exit_code_string ---------------------------------------------------------

def test_exit_code_string_known():
    assert rclone.exit_code_string(0) == 'Success'
    assert rclone.exit_code_string(7) == 'Fatal error'
    assert rclone.exit_code_string(8) == 'Exceeded transfer limit'
    assert rclone.exit_code_string(9) == 'Success, no files transferred'


def test_exit_code_string_out_of_range_does_not_raise():
    # Signal-based exits (137/143) and negatives must not raise IndexError.
    assert 'Unknown error' in rclone.exit_code_string(137)
    assert 'Unknown error' in rclone.exit_code_string(-1)
    assert 'Unknown error' in rclone.exit_code_string(100)


# --- classify_exit_code -------------------------------------------------------

def test_classify_success():
    assert rclone.classify_exit_code(0) == 'complete'


def test_classify_no_files_is_warning():
    assert rclone.classify_exit_code(9) == 'warning'


def test_classify_errors_include_8():
    # 1-8 are all failures; in particular 8 ("exceeded transfer limit") must
    # NOT be treated as success (the old silent-success data-loss trap).
    for code in range(1, 9):
        assert rclone.classify_exit_code(code) == 'error', code


def test_classify_unexpected_is_error():
    assert rclone.classify_exit_code(137) == 'error'


# --- parse_log_message --------------------------------------------------------

def test_parse_plain_message():
    parsed = rclone.parse_log_message(
        '2024/01/02 03:04:05 ERROR : something went wrong')
    assert parsed is not None
    assert parsed['type'] == 'MESSAGE'
    assert parsed['loglevel'] == 'ERROR'
    assert parsed['message'] == 'something went wrong'


def test_parse_progress_message():
    line = ('2024/01/02 03:04:05 NOTICE : '
            '1.5 GiB / 3 GiB, 50%, 10 MiB/s, ETA 2m30s (xfr#2/5)')
    parsed = rclone.parse_log_message(line)
    assert parsed is not None
    assert parsed['type'] == 'PROGRESS'
    assert parsed['sent'] == '1.5'
    assert parsed['sent_unit'] == 'GiB'
    assert parsed['total'] == '3'
    assert parsed['files'] == '2'
    assert parsed['files_total'] == '5'


def test_parse_non_log_line_returns_none():
    assert rclone.parse_log_message('random text without a level') is None

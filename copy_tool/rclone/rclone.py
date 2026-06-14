import re
import sys
from pathlib import Path
from shutil import which
from typing import Dict, List, Union

"""Regex to match/parse an rclone log message"""
_RCLONE_REGEX_LOG_MSG = re.compile(
    R'(?:<\d+>)?'  # systemd logging mode prefix
    R'((?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) )?'
    R'(?P<loglevel>DEBUG|INFO|NOTICE|ERROR)\s*:\s*'
    R'(?P<message>\w.*)'
)

"""Regex to match/parse the rclone one-line progress report"""
_RCLONE_REGEX_LOG_PROG = re.compile(
    R'(?P<sent>\d+\.?\d*) (?P<sent_unit>[A-Za-z]+) / (?P<total>\d+\.?\d*) '
    R'(?P<total_unit>[A-Za-z]+), (?P<percent>\d+|-)%?, (?P<rate>\d+\.?\d*) '
    R'(?P<rate_unit>[A-Za-z]+/[A-Za-z]+), ETA (?P<eta>[\w-]*)'
    R'(?: \(xfr#(?P<files>\d+)/(?P<files_total>\d+)\))?')

_RCLONE_EXIT_CODE_MSGS = [
    'Success',
    'Syntax or usage error',
    'Uncategorized error',
    'Directory not found',
    'File not found',
    'Temporary error (Retry attempted)',
    'Less serious error (Retry not attempted)',
    'Fatal error',
    'Exceeded transfer limit',
    'Success, no files transferred'
]


def parse_log_message(line: str) -> Union[Dict, None]:
    """Parse rclone log message and return as a dict."""
    # Match the log message
    match = _RCLONE_REGEX_LOG_MSG.match(line)
    if not match:
        return None
    # Default type is just a message
    parsed = match.groupdict()
    parsed['type'] = 'MESSAGE'

    # If loglevel is NOTICE, see if it's a progress report
    if parsed['loglevel'] == 'NOTICE':
        match = _RCLONE_REGEX_LOG_PROG.match(parsed['message'])
        if match:
            parsed['type'] = 'PROGRESS'
            parsed.update(match.groupdict())
    return parsed


def exit_code_string(exit_code: int) -> str:
    """Return the human-readable message for an rclone exit code.

    Falls back to a generic message for codes outside the documented range
    (e.g. signal-based exits like 137/143) rather than raising IndexError.
    """
    if 0 <= exit_code < len(_RCLONE_EXIT_CODE_MSGS):
        return _RCLONE_EXIT_CODE_MSGS[exit_code]
    return f'Unknown error (exit code {exit_code})'


def classify_exit_code(exit_code: int) -> str:
    """Classify an rclone exit code as 'complete', 'warning', or 'error'.

    * 0 -> 'complete' (success)
    * 9 -> 'warning'  (success, no files transferred)
    * everything else (1-8 and any unexpected code) -> 'error'
    """
    if exit_code == 0:
        return 'complete'
    if exit_code == 9:
        return 'warning'
    return 'error'


def executable_path() -> Union[str, None]:
    """Returns the path to the rclone executable."""
    # Check bundle path first
    path = None
    if hasattr(sys, '_MEIPASS'):
        path = which('rclone', path=str(Path(sys._MEIPASS).resolve()))
    # Check system path if nothing bundled
    if path is None:
        path = which('rclone')

    return path


def is_installed() -> bool:
    """Check whether rclone is installed on the host machine."""
    return executable_path() is not None


"""User-provided value for --max-backlog flag"""
_RCLONE_BACKLOG: Union[int, None] = None


def default_max_backlog() -> int:
    """Default value for --max-backlog flag"""
    return 10000


def set_max_backlog(backlog: Union[int, None]):
    """Set the value returned by max_backlog()"""
    global _RCLONE_BACKLOG
    _RCLONE_BACKLOG = backlog


def reset_max_backlog():
    """Reset the value returned by max_backlog() to the default"""
    global _RCLONE_BACKLOG
    _RCLONE_BACKLOG = None


def max_backlog() -> int:
    """Get the value provided to the --max-backlog flag. If a user-provided
    value has not been set, returns the default value"""
    if _RCLONE_BACKLOG is not None:
        return _RCLONE_BACKLOG
    else:
        return default_max_backlog()


"""User-provided value for the stats reporting time"""
_RCLONE_STATS_TIME: Union[str, None] = None


def default_stats_time() -> str:
    """Default stats reporting time"""
    return '500ms'


def set_stats_time(time: str):
    """Set the value returned by stats_time()"""
    global _RCLONE_STATS_TIME
    _RCLONE_STATS_TIME = time


def reset_stats_time():
    """Reset the value returned by stats_time() to the default"""
    global _RCLONE_STATS_TIME
    _RCLONE_STATS_TIME = None


def stats_time() -> str:
    """Get the value provided to the --stats flag. If a user-provided value
    has not been set, returns the default value"""
    if _RCLONE_STATS_TIME is not None:
        return _RCLONE_STATS_TIME
    else:
        return default_stats_time()


def default_args() -> List[str]:
    """Default rclone arguments"""
    return [
        '--max-backlog', str(max_backlog()),
        '--stats', stats_time(),
        '--stats-log-level', 'NOTICE',
        '--stats-one-line'
    ]

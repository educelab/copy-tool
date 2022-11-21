import argparse
import re
import sys
from pathlib import Path
from shutil import which
from typing import Callable, Dict, List, Union

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
    global _RCLONE_EXIT_CODE_MSGS
    return _RCLONE_EXIT_CODE_MSGS[exit_code]


def default_log_listener(d: Dict):
    """Default rclone log listener function. Prints the log message to stdout
    using print().

    :param d: Parsed progress report dict
    :return: None
    """
    print(f'{d["date"]} {d["time"]} {d["loglevel"]}: {d["message"]}')


def null_log_listener(d: Dict):
    """No-op rclone log listener function."""
    pass


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


def copy(src: str, dest: str,
         listener: Callable[[Dict], None] = default_log_listener) -> int:
    """Run the rclone copy command.

    :param src: Source file or directory
    :param dest: Destination directory
    :param listener: Callable for handling progress updates
    :return: process return code
    """
    args = ['copy', src, dest]
    return rclone(args=args, listener=listener)


def rclone(args: List[str],
           listener: Callable[[Dict], None] = default_log_listener) -> int:
    """Run rclone with the given list of arguments. Note that default_args()
    for reporting progress are always prepended to args:

    rclone --stats 500ms --stats-log-level NOTICE --stats-one-line [args...]

    :param args: List of program arguments
    :param listener: Callable for handling progress updates
    :return: process return code
    """
    import subprocess as sp

    # Add the rclone executable as the first argument
    rclone_exe = executable_path()
    if rclone_exe is None:
        raise FileNotFoundError('rclone executable not found')
    args[0:0] = [rclone_exe, *default_args()]

    # (Windows) For some reason, we have to explicitly disable the extra
    # subprocess window in a way we didn't before
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = sp.STARTUPINFO()
        startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = sp.SW_HIDE

    # Run rclone
    return_code = None
    with sp.Popen(args=args, stderr=sp.PIPE, startupinfo=startupinfo) as proc:
        def read_buffer(buffer):
            """Read from stderr two bytes at time and handle new lines"""
            b = proc.stderr.read(2).decode()
            if b is not None:
                buffer = f'{buffer}{b}'
            new_line = None
            if '\n' in buffer:
                new_line, buffer = buffer.split(sep='\n')
            if new_line is not None:
                parsed = parse_log_message(new_line)
                if parsed is not None:
                    listener(parsed)
            return buffer

        def flush_buffer(buffer):
            """Read all remaining bytes from buffer and parse all new lines"""
            b = proc.stderr.read().decode()
            if b is not None:
                buffer = f'{buffer}{b}'
            new_lines = None
            if '\n' in buffer:
                new_lines = buffer.split(sep='\n')
            if new_lines is None:
                return
            for n in new_lines:
                parsed = parse_log_message(n)
                if parsed is not None:
                    listener(parsed)

        # Read and parse stderr until the process ends
        stderr_buffer = ''
        while return_code is None:
            stderr_buffer = read_buffer(stderr_buffer)
            return_code = proc.poll()
        flush_buffer(stderr_buffer)

    return return_code


def main():
    parser = argparse.ArgumentParser('rclone.py')
    parser.add_argument('input', metavar='SRC', help='Input file or directory')
    parser.add_argument('output', metavar='DEST', help='Output directory')
    args = parser.parse_args()
    copy(src=args.input, dest=args.output)


if __name__ == '__main__':
    main()

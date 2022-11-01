import argparse
import re
import subprocess as sp
import sys
from pathlib import Path
from shutil import which
from typing import Callable, Dict, List, Union

"""Regex to match/parse an rclone log message"""
_REGEX_RCLONE_LOG_MSG = re.compile(
    R'(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) '
    R'(?P<loglevel>DEBUG|INFO|NOTICE|ERROR)\s*:\s*'
    R'(?P<message>\w.*)'
)

"""Regex to match/parse the rclone one-line progress report"""
_REGEX_RCLONE_LOG_PROG = re.compile(
    R'(?P<sent>\d+\.?\d*) (?P<sent_unit>[A-Za-z]+) / (?P<total>\d+\.?\d*) '
    R'(?P<total_unit>[A-Za-z]+), (?P<percent>\d+|-)%?, (?P<rate>\d+\.?\d*) '
    R'(?P<rate_unit>[A-Za-z]+/[A-Za-z]+), ETA (?P<eta>.*?)'
    R'( \(xfr#(?P<files>\d+)/(?P<files_total>\d+)\))?')


def _parse_rclone_log_message(line: str) -> Union[Dict, None]:
    """Parse rclone log message and return as a dict."""
    # Match the log message
    match = _REGEX_RCLONE_LOG_MSG.match(line)
    if not match:
        return None
    # Default type is just a message
    parsed = match.groupdict()
    parsed['type'] = 'MESSAGE'

    # If loglevel is NOTICE, so if it's a progress report
    if parsed['loglevel'] == 'NOTICE':
        match = _REGEX_RCLONE_LOG_PROG.match(parsed['message'])
        if match:
            parsed['type'] = 'PROGRESS'
            parsed.update(match.groupdict())
    return parsed


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
    """Run rclone with the given list of arguments. Note that default arguments
    for reporting progress are always prepended to args:

    rclone --stats 500ms --stats-log-level NOTICE --stats-one-line [args...]

    :param args: List of program arguments
    :param listener: Callable for handling progress updates
    :return: process return code
    """
    # Add the rclone executable as the first argument
    rclone_exe = executable_path()
    if rclone_exe is None:
        raise FileNotFoundError('rclone executable not found')
    args[0:0] = [rclone_exe,
                 '--stats', '500ms',
                 '--stats-log-level', 'NOTICE',
                 '--stats-one-line']

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
                parsed = _parse_rclone_log_message(new_line)
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
                new_lines, buffer = buffer.split(sep='\n')
            if new_lines is None:
                return
            for n in new_lines:
                parsed = _parse_rclone_log_message(n)
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

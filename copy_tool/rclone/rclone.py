import argparse
import re
import subprocess as sp
import sys
from pathlib import Path
from shutil import which
from typing import Callable, Dict, List, Union

"""Regex to parses the rclone one-line progress report"""
_REGEX_PROG_ONE_LINE = re.compile(
    R'(?P<sent>\d+\.?\d*) (?P<sent_unit>[A-Za-z]+) / (?P<total>\d+\.?\d*) '
    R'(?P<total_unit>[A-Za-z]+), (?P<percent>\d+)%, (?P<rate>\d+\.?\d*) '
    R'(?P<rate_unit>[A-Za-z]+/[A-Za-z]+), ETA (?P<eta>.*?) '
    R'\(xfr#(?P<files>\d+)/(?P<files_total>\d+)')


def default_progress_listener(d: Dict):
    """Default progress report listener function. Prints the progress report to
    stdout using print().

    :param d: Parsed progress report dict
    :return: None
    """
    sent = f'{d["sent"]} {d["sent_unit"]} / {d["total"]} {d["total_unit"]}'
    percent = f'{d["percent"]}%'
    rate = f'{d["rate"]} {d["rate_unit"]}'
    eta = f'ETA {d["eta"]}'
    xfr = f'({d["files"]}/{d["files_total"]})'
    print(f'{sent}, {percent}, {rate}, {eta} {xfr}')


def null_progress_listener(d: Dict):
    """No-op progress report listener function."""
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
         listener: Callable[[Dict], None] = default_progress_listener):
    """Run the rclone copy command.

    :param src: Source file or directory
    :param dest: Destination directory
    :param listener: Callable for handling progress updates
    :return: None
    """
    args = ['copy', src, dest]
    rclone(args=args, listener=listener)


def rclone(args: List[str],
           listener: Callable[[Dict], None] = default_progress_listener):
    """Run rclone with the given list of arguments. Note that default arguments
    for reporting progress are always prepended to args:

    rclone -P --stats-one-line [args...]

    :param args: List of program arguments
    :param listener: Callable for handling progress updates
    :return: None
    """
    # Add the rclone executable as the first argument
    rclone_exe = executable_path()
    if rclone_exe is None:
        raise FileNotFoundError('rclone executable not found')
    args[0:0] = [rclone_exe, '-P', '--stats-one-line']

    # (Windows) For some reason, we have to explicitly disable the extra
    # subprocess window in a way we didn't before
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = sp.STARTUPINFO()
        startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = sp.SW_HIDE

    # Run rclone
    with sp.Popen(args=args, stdout=sp.PIPE, startupinfo=startupinfo) as proc:
        def read_buffer(buffer):
            b = proc.stdout.read(2).decode()
            if b is not None:
                buffer = f'{buffer}{b}'
            new_line = None
            if '\n' in buffer:
                new_line, buffer = buffer.split(sep='\n')
            elif ')' in buffer:
                new_line, buffer = buffer.split(sep=')')
            if new_line is not None:
                parsed = _parse_one_line_progress(new_line)
                if parsed is not None:
                    listener(parsed)
            return buffer

        stdout_buffer = ''
        while proc.poll() is None:
            stdout_buffer = read_buffer(stdout_buffer)

    return proc


def _parse_one_line_progress(line: str) -> Union[Dict, None]:
    """Parse one-line progress and return as a dict."""
    match = _REGEX_PROG_ONE_LINE.match(line)
    if match:
        return match.groupdict()
    return None


def main():
    parser = argparse.ArgumentParser('rclone.py')
    parser.add_argument('input', metavar='SRC', help='Input file or directory')
    parser.add_argument('output', metavar='DEST', help='Output directory')
    args = parser.parse_args()
    copy(src=args.input, dest=args.output)


if __name__ == '__main__':
    main()

import re
import subprocess as sp
import sys
from pathlib import Path
from shutil import which
from typing import List, Union
import argparse

_REGEX_PROG_ONE_LINE = re.compile(
    R'(?P<sent>\d+\.?\d*) (?P<sent_unit>[A-Za-z]+) / (?P<total>\d+\.?\d*) '
    R'(?P<total_unit>[A-Za-z]+), (?P<percent>\d+)%, (?P<rate>\d+\.?\d*) '
    R'(?P<rate_unit>[A-Za-z]+/[A-Za-z]+), ETA (?P<eta>.*?) '
    R'\(xfr#(?P<files>\d+)/(?P<files_total>\d+)')


def default_listener(d):
    sent_total = f'{d["sent"]} {d["sent_unit"]} / {d["total"]} {d["total_unit"]}'
    percent = f'{d["percent"]}%'
    rate = f'{d["rate"]} {d["rate_unit"]}'
    eta = f'ETA {d["eta"]}'
    xfr = f'({d["files"]}/{d["files_total"]})'
    print(f'{sent_total}, {percent}, {rate}, {eta} {xfr}')


def executable_path() -> Union[str, None]:
    # Check bundle path first
    path = None
    if hasattr(sys, '_MEIPASS'):
        path = which('rclone', path=str(Path(sys._MEIPASS).resolve()))
    # Check system path if nothing bundled
    if path is None:
        path = which('rclone')

    return path


def is_installed() -> bool:
    return executable_path() is not None


def copy(src, dest, listener=default_listener):
    args = ['-P', '--stats-one-line', 'copy', str(src), str(dest)]
    rclone(args=args, listener=listener)


def rclone(args: List[str], listener=default_listener):
    rclone_exe = executable_path()
    if rclone_exe is None:
        raise FileNotFoundError('rclone executable not found')

    args.insert(0, rclone_exe)

    with sp.Popen(args, stdout=sp.PIPE) as proc:

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


def _parse_one_line_progress(line):
    match = _REGEX_PROG_ONE_LINE.match(line)
    if match:
        return match.groupdict()
    return None


def main():
    parser = argparse.ArgumentParser('rclone.py')
    parser.add_argument('input', metavar='SRC', nargs=1,
                        help='Input file or directory')
    parser.add_argument('output', metavar='DEST', nargs=1,
                        help='Output directory')
    args = parser.parse_args()
    copy(src=args.input, dest=args.output)


if __name__ == '__main__':
    main()

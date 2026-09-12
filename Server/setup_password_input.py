"""Password input with '*' feedback on Windows/POSIX, including Python 3.11-3.13.

The graphical setup is preferred for selection/editing and clipboard shortcuts.
Console secrets are never passed through CMD variables or stripped of spaces.
"""
from __future__ import annotations
import os
import sys
from typing import Callable, TextIO


def read_masked(get_character: Callable[[], str], output: TextIO, *, windows: bool = False) -> str:
    characters: list[str] = []
    while True:
        char = get_character()
        if char == '':
            raise EOFError('Password input ended.')
        if windows and char in ('\x00', '\xe0'):
            get_character()  # Arrow/function-key suffix; not part of a password.
            continue
        if char in ('\r', '\n'):
            output.write('\n')
            output.flush()
            # getwch returns UTF-16 units for non-BMP input; normalize only here.
            value = ''.join(characters)
            if windows:
                value = value.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'strict')
            return value
        if char == '\x03':
            output.write('\n')
            output.flush()
            raise KeyboardInterrupt
        if char in ('\x04', '\x1a'):
            output.write('\n')
            output.flush()
            raise EOFError('Password entry cancelled.')
        if char in ('\b', '\x7f'):
            if characters:
                characters.pop()
                output.write('\b \b')
        elif char in ('\x15', '\x1b'):  # Ctrl+U / Escape clear this field.
            output.write('\b \b' * len(characters))
            characters.clear()
        elif ord(char) >= 32:
            characters.append(char)
            output.write('*')
        output.flush()


def read_password(prompt: str, *, visible: bool = False) -> str:
    if visible:
        return input(prompt)  # Explicit opt-in only. Preserve all spaces.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError('Password entry needs an interactive terminal. Use the graphical setup instead of redirected input/output.')
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if os.name == 'nt':
        import msvcrt
        return read_masked(msvcrt.getwch, sys.stdout, windows=True)
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return read_masked(lambda: sys.stdin.read(1), sys.stdout)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

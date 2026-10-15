#!/usr/bin/env python3
"""Tiny falling-glyph animation: a neutral, good-looking window for the demo."""
import os
import random
import sys
import time

GLYPHS = "01234567890abcdefghijklmnopqrstuvwxyz+-*/=<>[]{}"
cols, rows = os.get_terminal_size()
drops = [random.randint(-rows, 0) for _ in range(cols)]
speed = [random.choice((1, 1, 2)) for _ in range(cols)]
trail = [random.randint(6, 18) for _ in range(cols)]
sys.stdout.write("\x1b[?25l\x1b[2J")
try:
    while True:
        cols, rows = os.get_terminal_size()
        if len(drops) != cols:
            drops = [random.randint(-rows, 0) for _ in range(cols)]
            speed = [random.choice((1, 1, 2)) for _ in range(cols)]
            trail = [random.randint(6, 18) for _ in range(cols)]
        out = []
        for c in range(cols):
            head = drops[c]
            if 0 <= head < rows:
                out.append("\x1b[%d;%dH\x1b[38;2;220;255;190m%s" % (head + 1, c + 1, random.choice(GLYPHS)))
            for k in (1, 2, 3):
                r = head - k
                if 0 <= r < rows:
                    out.append("\x1b[%d;%dH\x1b[38;2;142;198;63m%s" % (r + 1, c + 1, random.choice(GLYPHS)))
            r = head - trail[c]
            if 0 <= r < rows:
                out.append("\x1b[%d;%dH " % (r + 1, c + 1))
            drops[c] += speed[c] if random.random() < 0.6 else 0
            if drops[c] - trail[c] > rows:
                drops[c] = random.randint(-8, 0)
                trail[c] = random.randint(6, 18)
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        time.sleep(0.06)
except KeyboardInterrupt:
    sys.stdout.write("\x1b[?25h")

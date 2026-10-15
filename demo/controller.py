#!/usr/bin/env python3
"""Wireframe controller overlay that lights up with the recorded pad inputs.

    python3 controller.py screen2.mp4 overlay.mov

Reads the pad log that drive.py saved beside the recording
(screen2.mp4.events.json), maps every output frame of the trailer back to the
footage time it shows (the clips are speed-ramped, see build2.plan) and draws
a 760x500 RGBA wireframe pad with the pressed buttons glowing, the sticks
tracking and the triggers filling. Output is a qtrle .mov with alpha.
Pure numpy; ffmpeg encodes.
"""
import bisect
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build2

CW, CH, FPS = 760, 500, 30
yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)

ACCENT = np.array([142, 198, 63], np.float32)
WIRE = np.array([226, 232, 238], np.float32)
FACE = {"south": (118, 205, 70), "east": (236, 64, 78), "west": (56, 136, 245), "north": (247, 204, 48)}


# ── signed-distance shapes ──
def circle(cx, cy, r):
    return np.hypot(xx - cx, yy - cy) - r


def rrect(cx, cy, hw, hh, r):
    qx = np.abs(xx - cx) - hw + r
    qy = np.abs(yy - cy) - hh + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def capsule(ax, ay, bx, by, r):
    pax, pay, bax, bay = xx - ax, yy - ay, bx - ax, by - ay
    h = np.clip((pax * bax + pay * bay) / (bax * bax + bay * bay), 0, 1)
    return np.hypot(pax - bax * h, pay - bay * h) - r


def ellipse(cx, cy, rx, ry):
    return (np.hypot((xx - cx) / rx, (yy - cy) / ry) - 1) * min(rx, ry)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def line_mask(sd, width=1.6):
    return np.clip(width - np.abs(sd), 0, 1)


def fill_mask(sd):
    return np.clip(0.5 - sd, 0, 1)


def glow_mask(sd, spread=11.0):
    return np.where(sd > 0, np.exp(-np.maximum(sd, 0) / spread), 1.0).astype(np.float32)


# ── geometry ──
BODY = smin(ellipse(380, 238, 258, 118),
            smin(capsule(238, 280, 186, 424, 62), capsule(522, 280, 574, 424, 62), 30), 42)
PANEL = rrect(380, 250, 372, 246, 28)
L_STICK_C, R_STICK_C, DPAD_C, FACE_C = (240, 208), (470, 322), (300, 322), (536, 208)
SHAPES = {
    "l1": capsule(186, 104, 304, 94, 15), "r1": capsule(456, 94, 574, 104, 15),
    "select": circle(336, 214, 11), "start": circle(424, 214, 11), "guide": circle(380, 168, 18),
    "south": circle(FACE_C[0], FACE_C[1] + 37, 19), "east": circle(FACE_C[0] + 37, FACE_C[1], 19),
    "west": circle(FACE_C[0] - 37, FACE_C[1], 19), "north": circle(FACE_C[0], FACE_C[1] - 37, 19),
    "l3": circle(*L_STICK_C, 44), "r3": circle(*R_STICK_C, 44),
}
L2, R2 = rrect(222, 50, 56, 30, 15), rrect(538, 50, 56, 30, 15)
CROSS = np.minimum(rrect(DPAD_C[0], DPAD_C[1], 14, 40, 5), rrect(DPAD_C[0], DPAD_C[1], 40, 14, 5))
ARMS = {
    "dpad_up": rrect(DPAD_C[0], DPAD_C[1] - 26, 14, 16, 5), "dpad_down": rrect(DPAD_C[0], DPAD_C[1] + 26, 14, 16, 5),
    "dpad_left": rrect(DPAD_C[0] - 26, DPAD_C[1], 16, 14, 5), "dpad_right": rrect(DPAD_C[0] + 26, DPAD_C[1], 16, 14, 5),
}


class Canvas:
    def __init__(self):
        self.prgb = np.zeros((CH, CW, 3), np.float32)
        self.a = np.zeros((CH, CW), np.float32)

    def over(self, color, mask):
        mask = np.clip(mask, 0, 1)
        self.prgb = np.asarray(color, np.float32) * mask[..., None] + self.prgb * (1 - mask[..., None])
        self.a = mask + self.a * (1 - mask)

    def rgba(self, master=1.0):
        a = np.maximum(self.a, 1e-6)
        rgb = np.clip(self.prgb / a[..., None], 0, 255)
        return np.dstack([rgb, np.clip(self.a * master, 0, 1) * 255]).astype(np.uint8)


def draw(state, master=1.0, pulse=0.0):
    c = Canvas()
    c.over((5, 6, 15), fill_mask(PANEL) * 0.5)
    c.over(WIRE, line_mask(PANEL, 1.4) * 0.14)
    c.over(WIRE, line_mask(BODY, 2.0) * 0.9)
    pressed = state["btn"]

    def lit(name, sd, color):
        c.over(color, glow_mask(sd) * 0.42 * (sd > -1))
        c.over(color, fill_mask(sd) * 0.92)

    for name, sd in SHAPES.items():
        color = np.array(FACE.get(name, ACCENT), np.float32)
        c.over(color if name in FACE else WIRE, line_mask(sd) * (0.95 if name in FACE else 0.8))
        if name in ("l3", "r3"):
            continue
        if name in pressed or (name == "guide" and pulse > 0):
            lit(name, sd, color)

    # triggers: analog fill from the bottom
    for name, sd, amt in (("l2", L2, state["lt"]), ("r2", R2, state["rt"])):
        c.over(WIRE, line_mask(sd) * 0.8)
        if amt > 0.02:
            top = 80 - amt * 60
            c.over(ACCENT, fill_mask(sd) * (yy > top) * 0.92)
            c.over(ACCENT, glow_mask(sd) * 0.3 * (sd > -1) * amt)

    # d-pad
    c.over(WIRE, line_mask(CROSS) * 0.8)
    for name, sd in ARMS.items():
        if name in pressed:
            c.over(ACCENT, np.minimum(fill_mask(CROSS), fill_mask(sd)) * 0.95)
            c.over(ACCENT, glow_mask(CROSS) * 0.35 * (sd < 4) * (CROSS > -1))

    # sticks: outer ring (lights on click) and a dot that follows the thumb
    for key, (cx, cy), click in (("l", L_STICK_C, "l3"), ("r", R_STICK_C, "r3")):
        sd = SHAPES[click]
        if click in pressed:
            c.over(ACCENT, glow_mask(sd) * 0.4 * (sd > -1))
            c.over(ACCENT, line_mask(sd, 3.0) * 0.95)
        x, y = state[key]
        mag = min(1.0, math.hypot(x, y))
        dot = circle(cx + x * 17, cy + y * 17, 23)
        c.over(ACCENT if mag > 0.08 else WIRE, line_mask(dot, 1.8) * (0.95 if mag > 0.08 else 0.7))
        c.over(ACCENT, fill_mask(dot) * (0.18 + 0.72 * mag) * (mag > 0.08))
        if mag > 0.08:
            c.over(ACCENT, glow_mask(dot, 8.0) * 0.25 * (dot > -1) * mag)
    return c.rgba(master)


# ── input replay ──
class Replay:
    def __init__(self, events, lead):
        self.times, self.snaps = [], []
        btn, l, r, lt, rt = set(), (0.0, 0.0), (0.0, 0.0), 0.0, 0.0
        for e in events:
            t, kind = e[0] + lead, e[1]
            if kind == "btn":
                (btn.add if e[3] else btn.discard)(e[2])
            elif kind == "stick":
                if e[2] == "l":
                    l = (e[3], e[4])
                else:
                    r = (e[3], e[4])
            elif kind == "trig":
                if e[2] == "l":
                    lt = e[3]
                else:
                    rt = e[3]
            self.times.append(t)
            self.snaps.append({"btn": set(btn), "l": l, "r": r, "lt": lt, "rt": rt})
        self.idle = {"btn": set(), "l": (0.0, 0.0), "r": (0.0, 0.0), "lt": 0.0, "rt": 0.0}

    def at(self, video_t):
        i = bisect.bisect_right(self.times, video_t) - 1
        return self.snaps[i] if i >= 0 else self.idle


def main():
    screen, out = sys.argv[1:3]
    meta = json.load(open(screen + ".events.json"))
    lead = meta["video_len"] - meta["script_len"]
    vt = {c["key"]: c["t"] + lead for c in meta["cues"] if c.get("key")}
    replay = Replay(meta["pad"], lead)
    plan = build2.plan(vt)             # [{start, beats, ss, speed}] in output beats
    beat = build2.BEAT
    total = 64 * beat
    frames = int(total * FPS)

    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                           "-s", "%dx%d" % (CW, CH), "-r", str(FPS), "-i", "-", "-c:v", "qtrle", out],
                          stdin=subprocess.PIPE)
    for f in range(frames):
        t = f / FPS
        state, pulse, master = replay.idle, 0.0, 1.0
        if t < 8 * beat:                                   # intro: connected, guide pulsing
            pulse = 1.0 if (t % (beat * 2)) < beat else 0.0
            master = min(1.0, t / 0.4)
        else:
            for seg in plan:
                s0, s1 = seg["start"] * beat, (seg["start"] + seg["beats"]) * beat
                if s0 <= t < s1:
                    state = replay.at(seg["ss"] + (t - s0) * seg["speed"])
                    break
            else:
                master = 0.0
        ff.stdin.write(draw(state, master, pulse).tobytes())
    ff.stdin.close()
    ff.wait()
    print("wrote %s (%d frames)" % (out, frames))


if __name__ == "__main__":
    main()

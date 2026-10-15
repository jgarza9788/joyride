#!/usr/bin/env python3
"""A wireframe Xbox-style controller that lights up with the recorded pad inputs.

    python3 controller3.py screen2.mp4 overlay.mov

Line art only: a spline-traced Xbox silhouette (long swept grips, shoulder
bumpers, triggers behind them), a faint mesh inside the shell, the standard
layout (left stick high-left, d-pad low-left, face buttons high-right, right
stick low-right, View / Guide / Menu in the middle). Pressed controls fill
and glow; sticks track the thumbs; triggers fill with how far they're pulled.
Rendered at 1.5x and downscaled by ffmpeg. Pure numpy.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build2  # noqa: E402
from controller import Replay  # noqa: E402

CW, CH, FPS, S = 760, 500, 30, 1.5
PW, PH = int(CW * S), int(CH * S)
yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
xx, yy = (xx + 0.5) / S, (yy + 0.5) / S

ACCENT = np.array([142, 198, 63], np.float32)
WIRE = np.array([222, 230, 238], np.float32)
FACE = {"south": (118, 205, 70), "east": (236, 64, 78), "west": (56, 136, 245), "north": (247, 204, 48)}
LETTER = {"south": "A", "east": "B", "west": "X", "north": "Y"}
FONT = "/usr/share/fonts/TTF/FiraCodeNerdFontMono-Bold.ttf"


# ── shapes ──
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


def poly(verts):
    sd = None
    n = len(verts)
    for i in range(n):
        (x0, y0), (x1, y1) = verts[i], verts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        d = ((xx - x0) * ey - (yy - y0) * ex) / math.hypot(ex, ey)
        sd = d if sd is None else np.maximum(sd, d)
    return sd


def aa(sd):
    return np.clip(0.5 - sd * S, 0, 1)


def line(sd, w=1.5):
    return np.clip(0.5 + (w / 2 - np.abs(sd)) * S, 0, 1)


def fall(sd, spread):
    return np.where(sd > 0, np.exp(-np.maximum(sd, 0) / spread), 1.0).astype(np.float32)


def catmull(points, per=24):
    """Closed Catmull-Rom spline through points -> dense polyline."""
    pts = np.asarray(points, np.float64)
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for t in np.linspace(0, 1, per, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return np.array(out)


def polyline_sdf(path):
    """Signed distance to a closed polyline (negative inside), exact."""
    n = len(path)
    dist = np.full(xx.shape, 1e9, np.float32)
    inside = np.zeros(xx.shape, bool)
    for i in range(n):
        x0, y0 = path[i]
        x1, y1 = path[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        l2 = ex * ex + ey * ey
        h = np.clip(((xx - x0) * ex + (yy - y0) * ey) / l2, 0, 1)
        d = np.hypot(xx - x0 - ex * h, yy - y0 - ey * h)
        np.minimum(dist, d, out=dist)
        crosses = ((y0 > yy) != (y1 > yy)) & (xx < (x1 - x0) * (yy - y0) / (y1 - y0 + 1e-12) + x0)
        inside ^= crosses
    return np.where(inside, -dist, dist)


# Right half of the silhouette, as (dx from centre, y). Top centre first, then
# down the outside of the shoulder and grip, round the grip tip, and back up
# the inside to the bottom centre. Mirrored for the left half.
HALF = [(0, 114), (80, 112), (150, 106), (214, 106), (262, 120), (296, 148), (316, 190), (326, 240),
        (324, 292), (314, 346), (296, 400), (270, 442), (238, 468), (204, 476), (172, 466),
        (150, 438), (134, 398), (120, 362), (100, 336), (66, 324), (0, 320)]
CENTRE_X = 380


def silhouette():
    k = 0.965        # a touch narrower than the raw points
    right = [(CENTRE_X + dx * k, y) for dx, y in HALF]
    left = [(CENTRE_X - dx * k, y) for dx, y in reversed(HALF[1:-1])]
    return catmull(right + left, per=16)


BODY = polyline_sdf(silhouette())

# layout
L_C, R_C, DP_C, FC_C = (232, 196), (466, 292), (296, 292), (530, 196)
FACE_POS = {"south": (FC_C[0], FC_C[1] + 36), "east": (FC_C[0] + 36, FC_C[1]),
            "west": (FC_C[0] - 36, FC_C[1]), "north": (FC_C[0], FC_C[1] - 36)}
FACE_R = 17
DOMES = {n: circle(p[0], p[1], FACE_R) for n, p in FACE_POS.items()}
SMALL = {"select": circle(332, 214, 10), "start": circle(428, 214, 10), "guide": circle(380, 168, 17)}
BUMP = {"l1": capsule(138, 116, 286, 98, 13), "r1": capsule(474, 98, 622, 116, 13)}
TRIG = {"l": poly([(168, 36), (262, 36), (276, 80), (150, 84)]), "r": poly([(498, 36), (592, 36), (610, 84), (484, 80)])}
CROSS = np.minimum(rrect(DP_C[0], DP_C[1], 14, 40, 4), rrect(DP_C[0], DP_C[1], 40, 14, 4))
ARMS = {"dpad_up": rrect(DP_C[0], DP_C[1] - 26, 14, 16, 4), "dpad_down": rrect(DP_C[0], DP_C[1] + 26, 14, 16, 4),
        "dpad_left": rrect(DP_C[0] - 26, DP_C[1], 16, 14, 4), "dpad_right": rrect(DP_C[0] + 26, DP_C[1], 16, 14, 4)}
STICK_R, CAP_R = 42, 25


def glyph_mask(text, cx, cy, size):
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=%dx%d" % (PW, PH), "-vf",
           "drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=white:x=%.1f-tw/2:y=%.1f-th/2"
           % (FONT, text, int(size * S), cx * S, cy * S),
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(PH, PW).astype(np.float32) / 255.0


class Canvas:
    def __init__(self):
        self.prgb = np.zeros((PH, PW, 3), np.float32)
        self.a = np.zeros((PH, PW), np.float32)

    def over(self, color, mask):
        mask = np.clip(mask, 0, 1).astype(np.float32)
        self.prgb = np.asarray(color, np.float32) * mask[..., None] + self.prgb * (1 - mask[..., None])
        self.a = mask + self.a * (1 - mask)

    def add(self, color, mask):
        mask = np.clip(mask, 0, 1).astype(np.float32)
        self.prgb = self.prgb + np.asarray(color, np.float32) * mask[..., None]
        self.a = np.clip(self.a + mask * 0.9 * (1 - self.a), 0, 1)

    def copy(self):
        c = Canvas.__new__(Canvas)
        c.prgb, c.a = self.prgb.copy(), self.a.copy()
        return c

    def rgba(self, master):
        a = np.maximum(self.a, 1e-6)
        rgb = np.clip(self.prgb / a[..., None], 0, 255)
        return np.dstack([rgb, np.clip(self.a * master, 0, 1) * 255]).astype(np.uint8)


def build_static():
    c = Canvas()
    panel = rrect(380, 250, 372, 246, 28)
    c.over((4, 5, 12), aa(panel) * 0.50)
    c.over(WIRE, line(panel, 1.2) * 0.08)

    inside = aa(BODY)
    # faint mesh inside the shell, plus grip hatching
    grid = ((xx % 22) < 0.7) | ((yy % 22) < 0.7)
    c.over(WIRE, grid * inside * 0.05)
    hatch = (((xx * 0.6 + yy * 0.8) % 9) < 0.8) & (yy > 336)
    c.over(WIRE, hatch * aa(BODY + 12) * 0.13)
    # outline, inset contour, second inset
    c.over(WIRE, line(BODY, 1.9) * 0.95)
    c.over(WIRE, line(BODY + 13, 1.0) * 0.30)
    c.over(WIRE, line(BODY + 26, 0.8) * 0.12 * (yy < 330))

    for sd in BUMP.values():
        c.over(WIRE, line(sd, 1.5) * 0.85)
        c.over(WIRE, line(sd + 6, 0.8) * 0.2)
    for sd in TRIG.values():
        c.over(WIRE, line(sd, 1.5) * 0.7)

    # sticks: outer ring, inner ring, platter
    for (cx, cy) in (L_C, R_C):
        c.over(WIRE, line(circle(cx, cy, STICK_R + 8), 1.0) * 0.28)
        c.over(WIRE, line(circle(cx, cy, STICK_R), 1.5) * 0.75)
        c.over(WIRE, line(circle(cx, cy, STICK_R - 8), 0.8) * 0.2)
    # d-pad
    c.over(WIRE, line(CROSS, 1.5) * 0.85)
    c.over(WIRE, line(circle(*DP_C, 52), 1.0) * 0.25)
    for sd in (poly([(DP_C[0], DP_C[1] - 36), (DP_C[0] - 7, DP_C[1] - 26), (DP_C[0] + 7, DP_C[1] - 26)]),
               poly([(DP_C[0], DP_C[1] + 36), (DP_C[0] + 7, DP_C[1] + 26), (DP_C[0] - 7, DP_C[1] + 26)]),
               poly([(DP_C[0] - 36, DP_C[1]), (DP_C[0] - 26, DP_C[1] + 7), (DP_C[0] - 26, DP_C[1] - 7)]),
               poly([(DP_C[0] + 36, DP_C[1]), (DP_C[0] + 26, DP_C[1] - 7), (DP_C[0] + 26, DP_C[1] + 7)])):
        c.over(WIRE, line(sd, 0.9) * 0.45)
    # face buttons
    c.over(WIRE, line(circle(*FC_C, 62), 1.0) * 0.22)
    for name, sd in DOMES.items():
        colr = np.array(FACE[name], np.float32)
        c.over(colr, line(sd, 1.7) * 0.95)
        c.over(colr, glyph_mask(LETTER[name], *FACE_POS[name], 20) * 0.9)
    # centre cluster
    for name, sd in SMALL.items():
        c.over(WIRE, line(sd, 1.4) * 0.8)
    c.over(WIRE, line(circle(380, 168, 11), 0.9) * 0.4)
    c.over(WIRE, line(capsule(374, 162, 386, 174, 0.01), 1.2) * 0.55)
    c.over(WIRE, line(capsule(386, 162, 374, 174, 0.01), 1.2) * 0.55)
    for dy in (-3, 0, 3):                                    # menu icon
        c.over(WIRE, aa(rrect(428, 214 + dy, 4.5, 0.55, 0.3)) * 0.7)
    c.over(WIRE, line(rrect(330, 212, 3.6, 2.6, 0.8), 0.8) * 0.7)   # view icon
    c.over(WIRE, line(rrect(334, 216, 3.6, 2.6, 0.8), 0.8) * 0.7)
    for text, cx, cy, size in (("LT", 215, 60, 14), ("RT", 545, 60, 14), ("LB", 212, 106, 11), ("RB", 548, 106, 11)):
        c.over(WIRE, glyph_mask(text, cx, cy, size) * 0.35)
    return c


STATIC = build_static()
NEON_OUT = (fall(BODY, 8.0) * (1 - aa(BODY))).astype(np.float32)
LET = {n: glyph_mask(LETTER[n], *FACE_POS[n], 20) for n in FACE_POS}


def draw(state, master=1.0, energy=0.25, pulse=0.0):
    c = STATIC.copy()
    pressed = state["btn"]
    c.add(ACCENT, NEON_OUT * 0.30 * energy)
    c.over(ACCENT, line(BODY, 1.9) * (0.10 + 0.55 * energy))

    for name, sd in DOMES.items():
        if name in pressed:
            colr = np.array(FACE[name], np.float32)
            c.add(colr, fall(sd, 10) * 0.5 * (sd > -1))
            c.over(colr, aa(sd) * 0.8)
            c.over((255, 255, 255), line(sd, 1.8) * 0.9)
            c.over((8, 10, 14), LET[name] * 0.9)

    for name, sd in SMALL.items():
        if name in pressed or (name == "guide" and pulse > 0):
            c.add(ACCENT, fall(sd, 12) * 0.55 * (sd > -1))
            c.over(ACCENT, aa(sd) * 0.9)
            c.over((255, 255, 255), line(sd, 1.6) * 0.8)

    for name, sd in BUMP.items():
        if name in pressed:
            c.add(ACCENT, fall(sd, 11) * 0.45 * (sd > -1))
            c.over(ACCENT, aa(sd) * 0.85)
            c.over((255, 255, 255), line(sd, 1.6) * 0.85)

    for key, amt in (("l", state["lt"]), ("r", state["rt"])):
        sd = TRIG[key]
        if amt > 0.02:
            top = 86 - amt * 54
            c.over(ACCENT, aa(sd) * (yy > top) * 0.85)
            c.over((255, 255, 255), line(sd, 1.6) * (0.4 + 0.5 * amt))
            c.add(ACCENT, fall(sd, 11) * 0.35 * amt * (sd > -1))

    for name, sd in ARMS.items():
        if name in pressed:
            c.add(ACCENT, fall(CROSS, 9) * 0.4 * (sd < 4) * (CROSS > -1))
            c.over(ACCENT, np.minimum(aa(CROSS), aa(sd)) * 0.9)
            c.over((255, 255, 255), line(CROSS, 1.6) * (sd < 2) * 0.8)

    for key, (cx, cy), click in (("l", L_C, "l3"), ("r", R_C, "r3")):
        x, y = state[key]
        mag = min(1.0, math.hypot(x, y))
        ox, oy = cx + x * 15, cy + y * 15
        cap = circle(ox, oy, CAP_R)
        live = mag > 0.08
        col = ACCENT if live else WIRE
        c.over((6, 8, 12), aa(cap) * 0.55)                            # knock back what's behind the cap
        c.over(col, line(cap, 1.8) * (0.95 if live else 0.8))
        c.over(col, line(circle(ox, oy, CAP_R * 0.62), 0.9) * (0.55 if live else 0.3))
        c.over(col, line(capsule(ox - CAP_R * 0.62, oy, ox + CAP_R * 0.62, oy, 0.01), 0.8) * 0.3)
        c.over(col, line(capsule(ox, oy - CAP_R * 0.62, ox, oy + CAP_R * 0.62, 0.01), 0.8) * 0.3)
        if live:
            c.add(ACCENT, fall(cap, 8) * 0.40 * mag * (cap > -1))
            c.over(ACCENT, aa(cap) * 0.16 * mag)
            c.over(ACCENT, line(capsule(cx, cy, ox, oy, 0.01), 1.0) * 0.45 * mag)       # tether from centre
        if click in pressed:
            ring = circle(cx, cy, STICK_R)
            c.add(ACCENT, fall(ring, 10) * 0.5 * (ring > -1))
            c.over(ACCENT, line(ring, 3.2) * 0.95)
    return c.rgba(master)


def main():
    screen, out = sys.argv[1:3]
    meta = json.load(open(screen + ".events.json"))
    lead = meta["video_len"] - meta["script_len"]
    vt = {c["key"]: c["t"] + lead for c in meta["cues"] if c.get("key")}
    replay = Replay(meta["pad"], lead)
    plan = build2.plan(vt)
    beat = build2.BEAT
    frames = int(64 * beat * FPS)

    ff = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                           "-s", "%dx%d" % (PW, PH), "-r", str(FPS), "-i", "-", "-c:v", "qtrle", out],
                          stdin=subprocess.PIPE)
    energy = 0.2
    for f in range(frames):
        t = f / FPS
        state, pulse, master = replay.idle, 0.0, 1.0
        if t < 8 * beat:
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
        busy = len(state["btn"]) * 0.22 + max(math.hypot(*state["l"]), math.hypot(*state["r"])) * 0.45 \
            + max(state["lt"], state["rt"]) * 0.3 + pulse * 0.4
        energy += (min(1.0, 0.18 + busy) - energy) * 0.22
        ff.stdin.write(draw(state, master, energy, pulse).tobytes())
    ff.stdin.close()
    ff.wait()
    print("wrote %s (%d frames)" % (out, frames))


if __name__ == "__main__":
    main()

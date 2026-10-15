#!/usr/bin/env python3
"""A glossy controller render that lights up with the recorded pad inputs.

    python3 controller2.py screen2.mp4 overlay2.mov

Same job as controller.py (replay the pad log, map output frames back to the
footage through the speed ramps) but drawn like a product shot: dark glass
body with rim lighting and an engraved seam, recessed wells, domed buttons
with lettering, specular sticks, neon underglow that swells with activity.
Rendered at 1.5x and downscaled by ffmpeg. Pure numpy; ffmpeg encodes.
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
FACE = {"south": (118, 205, 70), "east": (236, 64, 78), "west": (56, 136, 245), "north": (247, 204, 48)}
LETTER = {"south": "A", "east": "B", "west": "X", "north": "Y"}
FONT = "/usr/share/fonts/TTF/FiraCodeNerdFontMono-Bold.ttf"


# ── signed-distance shapes (logical units; S pixels per unit) ──
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


def poly(verts):
    sd = None
    n = len(verts)
    for i in range(n):
        (x0, y0), (x1, y1) = verts[i], verts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        d = ((xx - x0) * ey - (yy - y0) * ex) / ln
        sd = d if sd is None else np.maximum(sd, d)
    return sd


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def aa(sd):
    return np.clip(0.5 - sd * S, 0, 1)


def line(sd, w=1.5):
    return np.clip(0.5 + (w / 2 - np.abs(sd)) * S, 0, 1)


def fall(sd, spread):
    return np.where(sd > 0, np.exp(-np.maximum(sd, 0) / spread), 1.0).astype(np.float32)


def lerp(a, b, t):
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    return a + (b - a) * np.asarray(t, np.float32)[..., None]


def body_sdf(dy=0.0):
    global yy
    keep = yy
    yy = keep - dy
    try:
        return smin(ellipse(380, 238, 258, 118),
                    smin(capsule(238, 280, 186, 424, 62), capsule(522, 280, 574, 424, 62), 30), 42)
    finally:
        yy = keep


# ── layout ──
L_C, R_C, DP_C, FC_C = (240, 208), (470, 312), (300, 306), (536, 208)
FACE_POS = {"south": (FC_C[0], FC_C[1] + 37), "east": (FC_C[0] + 37, FC_C[1]),
            "west": (FC_C[0] - 37, FC_C[1]), "north": (FC_C[0], FC_C[1] - 37)}
BODY = body_sdf()
DOMES = {n: circle(p[0], p[1], 19) for n, p in FACE_POS.items()}
SMALL = {"select": circle(336, 214, 11), "start": circle(424, 214, 11), "guide": circle(380, 168, 18)}
BUMP = {"l1": capsule(186, 104, 304, 94, 15), "r1": capsule(456, 94, 574, 104, 15)}
TRIG = {"l": rrect(222, 50, 56, 30, 15), "r": rrect(538, 50, 56, 30, 15)}
CROSS = np.minimum(rrect(DP_C[0], DP_C[1], 15, 41, 5), rrect(DP_C[0], DP_C[1], 41, 15, 5))
ARMS = {"dpad_up": rrect(DP_C[0], DP_C[1] - 27, 15, 17, 5), "dpad_down": rrect(DP_C[0], DP_C[1] + 27, 15, 17, 5),
        "dpad_left": rrect(DP_C[0] - 27, DP_C[1], 17, 15, 5), "dpad_right": rrect(DP_C[0] + 27, DP_C[1], 17, 15, 5)}
ARROWS = {
    "dpad_up": poly([(DP_C[0], DP_C[1] - 38), (DP_C[0] - 7, DP_C[1] - 27), (DP_C[0] + 7, DP_C[1] - 27)]),
    "dpad_down": poly([(DP_C[0], DP_C[1] + 38), (DP_C[0] + 7, DP_C[1] + 27), (DP_C[0] - 7, DP_C[1] + 27)]),
    "dpad_left": poly([(DP_C[0] - 38, DP_C[1]), (DP_C[0] - 27, DP_C[1] + 7), (DP_C[0] - 27, DP_C[1] - 7)]),
    "dpad_right": poly([(DP_C[0] + 38, DP_C[1]), (DP_C[0] + 27, DP_C[1] - 7), (DP_C[0] + 27, DP_C[1] + 7)]),
}
STICK_R = 26
WELLS = ((*L_C, 54), (*R_C, 54), (*DP_C, 56), (*FC_C, 66))


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
        color = np.asarray(color, np.float32)
        self.prgb = color * mask[..., None] + self.prgb * (1 - mask[..., None])
        self.a = mask + self.a * (1 - mask)

    def add(self, color, mask):                      # light only (additive glow), keeps alpha growing
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


# ── static layer, drawn once ──
def build_static():
    c = Canvas()
    panel = rrect(380, 250, 372, 246, 28)
    c.over((4, 5, 12), aa(panel) * 0.58)
    c.over((255, 255, 255), line(panel, 1.4) * 0.10)

    # drop shadow
    shadow = body_sdf(16)
    c.over((0, 0, 0), fall(shadow, 17) * (1 - aa(BODY)) * 0.55)

    # body: gradient glass, soft sheen, fine weave
    inside = aa(BODY)
    t = np.clip((yy - 110) / 330, 0, 1)
    col = lerp((46, 50, 64), (14, 16, 23), t)
    sheen = np.exp(-(((xx - 300) ** 2) / (2 * 160 ** 2) + ((yy - 165) ** 2) / (2 * 62 ** 2)))[..., None]
    col = col + sheen * np.array([16, 18, 24], np.float32)
    col = col * (1 + 0.03 * np.sin((xx + yy) * 0.95))[..., None]
    c.over(col, inside)

    # rim light: edges facing the up-left light catch it
    gy, gx = np.gradient(BODY)
    norm = np.maximum(np.hypot(gx, gy), 1e-6)
    nl = np.clip((gx * -0.55 + gy * -0.83) / norm, 0, 1)
    d = -BODY
    rim = np.exp(-np.maximum(d, 0) / 4.5) * (0.12 + 0.88 * nl) * inside
    c.over((236, 242, 252), rim * 0.95)
    c.over((0, 0, 0), line(BODY, 1.2) * 0.5)
    # engraved seam
    c.over((255, 255, 255), line(d - 19, 1.0) * 0.09 * inside)
    c.over((0, 0, 0), line(d - 22, 1.2) * 0.35 * inside)

    # wells
    keep = aa(BODY + 9)                   # wells stay inside the shell
    for (cx, cy, r) in WELLS:
        w = circle(cx, cy, r)
        c.over((8, 9, 13), aa(w) * 0.9 * keep)
        ny = np.clip((yy - cy) / r, -1, 1)
        c.over((255, 255, 255), line(w, 1.6) * (0.04 + 0.2 * np.clip(ny, 0, 1)) * keep)
        c.over((0, 0, 0), line(w, 2.2) * np.clip(-ny, 0, 1) * 0.5 * keep)

    # stick bases
    for (cx, cy) in (L_C, R_C):
        base = circle(cx, cy, 44)
        c.over(lerp((30, 33, 42), (12, 13, 18), np.clip(np.hypot(xx - cx, yy - cy) / 44, 0, 1)), aa(base))
        c.over((255, 255, 255), line(base, 1.2) * 0.14)
        c.over((255, 255, 255), line(circle(cx, cy, 36), 0.8) * 0.06)

    # bumpers and trigger housings
    for sd in BUMP.values():
        c.over(lerp((40, 44, 56), (16, 18, 25), np.clip((yy - 80) / 40, 0, 1)), aa(sd))
        g2y, g2x = np.gradient(sd)
        n2 = np.maximum(np.hypot(g2x, g2y), 1e-6)
        c.over((236, 242, 252), np.exp(-np.maximum(-sd, 0) / 3.5) * np.clip((g2x * -0.55 + g2y * -0.83) / n2, 0, 1) * aa(sd) * 0.7)
        c.over((0, 0, 0), line(sd, 1.1) * 0.5)
    for sd in TRIG.values():
        c.over((10, 11, 16), aa(sd) * 0.9)
        c.over((255, 255, 255), line(sd, 1.4) * 0.22)

    # d-pad cross
    c.over(lerp((40, 44, 56), (17, 19, 26), np.clip((yy - 280) / 80, 0, 1)), aa(CROSS))
    g3y, g3x = np.gradient(CROSS)
    n3 = np.maximum(np.hypot(g3x, g3y), 1e-6)
    c.over((236, 242, 252), np.exp(-np.maximum(-CROSS, 0) / 2.8) * np.clip((g3x * -0.55 + g3y * -0.83) / n3, 0, 1) * aa(CROSS) * 0.75)
    c.over((0, 0, 0), line(CROSS, 1.2) * 0.55)
    for sd in ARROWS.values():
        c.over((200, 206, 216), aa(sd) * 0.38)

    # face buttons: dark domes, coloured rim, lettering, specular
    for name, sd in DOMES.items():
        cx, cy = FACE_POS[name]
        colr = np.array(FACE[name], np.float32)
        r = np.clip(np.hypot(xx - cx, yy - cy) / 19, 0, 1)
        base = lerp(lerp((26, 28, 36), colr, 0.10), (12, 13, 18), r ** 2)
        c.over(base, aa(sd))
        c.over(colr, line(sd + 1.0, 1.7) * 0.85)
        spec = np.exp(-(((xx - cx + 6) ** 2 + (yy - cy + 7) ** 2) / (2 * 6.5 ** 2)))
        c.over((255, 255, 255), spec * aa(sd) * 0.20)
        c.over(colr, glyph_mask(LETTER[name], cx, cy + 1, 22) * 0.9)

    # centre buttons
    for name, sd in SMALL.items():
        cx = {"select": 336, "start": 424, "guide": 380}[name]
        cy = 168 if name == "guide" else 214
        r = np.clip(np.hypot(xx - cx, yy - cy) / (18 if name == "guide" else 11), 0, 1)
        c.over(lerp((30, 33, 42), (11, 12, 17), r ** 2), aa(sd))
        c.over((255, 255, 255), line(sd, 1.2) * 0.2)
    c.over((200, 206, 216), aa(rrect(424, 211, 5, 0.9, 0.5)) * 0.55)
    c.over((200, 206, 216), aa(rrect(424, 214, 5, 0.9, 0.5)) * 0.55)
    c.over((200, 206, 216), aa(rrect(424, 217, 5, 0.9, 0.5)) * 0.55)
    c.over((200, 206, 216), line(rrect(334, 212, 4, 3, 1), 0.9) * 0.55)
    c.over((200, 206, 216), line(rrect(338, 216, 4, 3, 1), 0.9) * 0.55)
    c.over(ACCENT, aa(circle(380, 168, 6.5)) * 0.35)
    for text, cx, cy, size in (("LT", 222, 50, 15), ("RT", 538, 50, 15), ("LB", 245, 99, 12), ("RB", 515, 99, 12)):
        c.over((200, 206, 216), glyph_mask(text, cx, cy, size) * 0.38)
    return c


STATIC = build_static()
NEON_OUT = (fall(BODY, 9.0) * (1 - aa(BODY))).astype(np.float32)
_wells = np.max([aa(circle(cx, cy, r + 3)) for (cx, cy, r) in WELLS], axis=0)
NEON_IN = (line(-BODY - 5.0, 1.4) * aa(BODY) * (1 - _wells)).astype(np.float32)
LET = {n: glyph_mask(LETTER[n], FACE_POS[n][0], FACE_POS[n][1] + 1, 22) for n in FACE_POS}
CAP_DIST = {}


def draw(state, master=1.0, energy=0.25, pulse=0.0):
    c = STATIC.copy()
    pressed = state["btn"]
    # underglow follows how busy the pad is
    c.add(ACCENT, NEON_OUT * 0.30 * energy)
    c.over(ACCENT, NEON_IN * (0.18 + 0.6 * energy))

    for name, sd in DOMES.items():
        if name in pressed:
            colr = np.array(FACE[name], np.float32)
            cx, cy = FACE_POS[name]
            spec = np.exp(-(((xx - cx + 5) ** 2 + (yy - cy + 6) ** 2) / (2 * 7 ** 2)))
            c.add(colr, fall(sd, 11) * 0.5 * (sd > -1))
            c.over(lerp(colr * 0.78, np.array([255, 255, 255], np.float32), spec * 0.35), aa(sd))
            c.over((10, 12, 16), LET[name] * 0.85)

    for name, sd in SMALL.items():
        if name in pressed or (name == "guide" and pulse > 0):
            c.add(ACCENT, fall(sd, 13) * 0.55 * (sd > -1))
            c.over(ACCENT, aa(sd) * 0.95)
            c.over((255, 255, 255), line(sd + 3, 1.4) * 0.5)

    for name, sd in BUMP.items():
        if name in pressed:
            c.add(ACCENT, fall(sd, 12) * 0.45 * (sd > -1))
            c.over(ACCENT, aa(sd) * 0.92)
            c.over((255, 255, 255), line(sd + 3, 1.2) * 0.35)

    for key, amt in (("l", state["lt"]), ("r", state["rt"])):
        sd = TRIG[key]
        if amt > 0.02:
            top = 80 - amt * 60
            fillm = aa(sd) * (yy > top)
            grad = lerp((90, 140, 40), ACCENT * 1.15, np.clip((80 - yy) / 60 + 0.4, 0, 1))
            c.over(grad, fillm * 0.95)
            c.add(ACCENT, fall(sd, 12) * 0.35 * amt * (sd > -1))

    for name, sd in ARMS.items():
        if name in pressed:
            m = np.minimum(aa(CROSS), aa(sd))
            c.add(ACCENT, fall(CROSS, 10) * 0.4 * (sd < 4) * (CROSS > -1))
            c.over(ACCENT, m * 0.95)
            c.over((255, 255, 255), aa(ARROWS[name]) * 0.8)

    for key, (cx, cy), click in (("l", L_C, "l3"), ("r", R_C, "r3")):
        x, y = state[key]
        mag = min(1.0, math.hypot(x, y))
        ox, oy = cx + x * 17, cy + y * 17
        dist = np.hypot(xx - ox, yy - oy)
        cap = dist - STICK_R
        rad = np.clip(dist / STICK_R, 0, 1)
        shade = lerp((58, 62, 76), (22, 24, 31), rad ** 1.4)
        spec = np.exp(-(((xx - (ox - 8 - x * 4)) ** 2 + (yy - (oy - 9 - y * 4)) ** 2) / (2 * 8 ** 2)))
        c.over((0, 0, 0), fall(circle(ox + 3, oy + 5, STICK_R), 8) * 0.35 * (1 - aa(cap)))
        c.over(shade, aa(cap))
        c.over((255, 255, 255), line(dist - STICK_R * 0.62, 0.9) * 0.10 * aa(cap))
        c.over((255, 255, 255), line(dist - STICK_R * 0.82, 0.9) * 0.08 * aa(cap))
        c.over((255, 255, 255), spec * aa(cap) * 0.30)
        c.over((255, 255, 255), line(cap + 1, 1.2) * 0.18)
        if mag > 0.08:
            c.add(ACCENT, fall(cap, 9) * 0.40 * mag * (cap > -1))
            c.over(ACCENT, line(cap + 1.2, 2.4) * (0.35 + 0.65 * mag))
        if click in pressed:
            well = circle(cx, cy, 46)
            c.add(ACCENT, fall(well, 11) * 0.5 * (well > -1))
            c.over(ACCENT, line(well, 3.2) * 0.95)
            c.over(ACCENT, aa(cap) * 0.25)
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

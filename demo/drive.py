#!/usr/bin/env python3
"""Choreographed Joyride showcase: a virtual Xbox pad drives the real desktop.

Everything on screen is Joyride reacting to genuine controller events: no
mouse, no keyboard. Set up two empty workspaces (9 and 10), then:

    python3 drive.py [--record out.mp4] [--rehearse]

Writes <out>.events.json with caption cues (seconds into the video).
"""
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from virtualpad import VirtualPad  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE, SIDE = 9, 10
T0 = time.monotonic()
cues = []


def now():
    return time.monotonic() - T0


def say(text, key=None):
    """Mark a caption cue at the current time."""
    cues.append({"t": round(now(), 2), "text": text, "key": key})
    print("%6.2f  %s" % (now(), text), flush=True)


def sh(*argv, **kw):
    return subprocess.run(list(argv), capture_output=True, text=True, **kw).stdout


def hypr(expr):
    sh("hyprctl", "dispatch", expr)


def clients(ws):
    out = json.loads(sh("hyprctl", "clients", "-j"))
    return [c for c in out if c["workspace"]["id"] == ws]


def cursor():
    x, y = sh("hyprctl", "cursorpos").strip().split(",")
    return int(x), int(y)


def status():
    try:
        return json.loads(sh("omarchy-shell", "joyride", "status"))
    except ValueError:
        return {}


def launch(cmd, title, font=16):
    # Popen, not sh(): the terminal inherits the pipes and would block us until it closes.
    subprocess.Popen(["omarchy-launch-terminal", "--title=" + title, "--font-size=%d" % font, "-e", "bash", "-lc", cmd],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def wait_windows(ws, n, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if len(clients(ws)) >= n:
            return
        time.sleep(0.3)
    raise SystemExit("workspace %d never reached %d windows" % (ws, n))


def stage():
    for ws in (STAGE, SIDE):
        if clients(ws):
            raise SystemExit("workspace %d is not empty; aborting" % ws)
    hypr('hl.dsp.focus({ workspace = "%d" })' % STAGE)
    time.sleep(0.8)
    launch("fastfetch; sleep infinity", "demo-fetch", 20)
    wait_windows(STAGE, 1)
    launch("python3 -I -B %s/rain.py" % HERE, "demo-rain")
    wait_windows(STAGE, 2)
    launch("nvim -n -u NONE +'set noswapfile nocp nonumber laststatus=0 noruler noshowmode' "
           "+'syntax on' +startinsert", "demo-nvim", 30)
    wait_windows(STAGE, 3)
    hypr('hl.dsp.focus({ workspace = "%d" })' % SIDE)
    time.sleep(0.6)
    launch("nvim -n -u NONE +'help index' +'only'", "demo-help")
    wait_windows(SIDE, 1)
    hypr('hl.dsp.focus({ workspace = "%d" })' % STAGE)
    time.sleep(1.0)
    # leave the first (leftmost) window focused
    for _ in range(4):
        hypr('hl.dsp.layout("focus l")')
        time.sleep(0.15)


def teardown():
    for ws in (STAGE, SIDE):
        for c in clients(ws):
            hypr('hl.dsp.window.close({ window = "address:%s" })' % c["address"])
    time.sleep(0.5)
    hypr('hl.dsp.focus({ workspace = "1" })')


def window(title):
    for ws in (STAGE, SIDE):
        for c in clients(ws):
            if c["title"].startswith(title) or c["initialTitle"] == title:
                return c
    return None


# ── pad gestures ──
def stick_to(pad, which, x, y, secs=0.0):
    pad.stick(which, x, y)
    if secs:
        time.sleep(secs)


def sweep(pad, target, tol=60, timeout=6.0):
    """Push the right stick toward a screen point, like a thumb would."""
    end = time.time() + timeout
    while time.time() < end:
        cx, cy = cursor()
        dx, dy = target[0] - cx, target[1] - cy
        dist = math.hypot(dx, dy)
        if dist < tol:
            break
        push = min(1.0, 0.35 + dist / 700.0)
        pad.stick("r", dx / dist * push, dy / dist * push)
        time.sleep(0.04)
    pad.stick("r", 0, 0)


def octant_vec(i):
    ang = i * math.pi / 4
    return math.sin(ang), -math.cos(ang)


def load_groups():
    src = open(os.path.join(HERE, "..", "Model.js")).read().replace(".pragma library", "")
    js = src + ";console.log(JSON.stringify({g:GROUPS,s:SHIFTED}))"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True).stdout
    data = json.loads(out)
    return data["g"], data["s"]


def find_char(groups, shifted, ch):
    for gi, row in enumerate(groups):
        if ch in row:
            return gi, row.index(ch), False
    for gi, row in enumerate(shifted):
        if ch in row:
            return gi, row.index(ch), True
    raise KeyError(ch)


def type_text(pad, text, pace=0.34):
    groups, shifted = load_groups()
    for ch in text:
        if ch == " ":
            pad.tap("north")
            time.sleep(pace * 0.6)
            continue
        gi, ki, shift = find_char(groups, shifted, ch)
        lx, ly = octant_vec(gi)
        rx, ry = octant_vec(ki)
        pad.stick("l", lx, ly)
        pad.stick("r", rx, ry)
        if shift:
            pad.trigger("l", 1.0)
        time.sleep(pace * 0.55)
        pad.trigger("r", 1.0)
        time.sleep(0.07)
        pad.trigger("r", 0.0)
        if shift:
            pad.trigger("l", 0.0)
        time.sleep(pace * 0.4)
    pad.stick("l", 0, 0)
    pad.stick("r", 0, 0)


def main():
    out = None
    if "--record" in sys.argv:
        out = os.path.abspath(sys.argv[sys.argv.index("--record") + 1])
    pad = VirtualPad()
    rec = None
    try:
        time.sleep(3.0)    # let joyride's helper notice the new pad
        assert any(p["name"] == "Joyride Demo Pad" for p in status().get("pads", [])), "pad not seen"
        stage()
        if out:
            rec = subprocess.Popen(["gpu-screen-recorder", "-w", "HDMI-A-2", "-f", "30", "-s", "2560x1440",
                                    "-cursor", "yes", "-q", "very_high", "-o", out],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.0)
        global T0
        T0 = time.monotonic()
        scene(pad)
    finally:
        if rec:
            t_stop = now()
            rec.send_signal(2)
            rec.wait()
            vd = float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out).strip() or 0)
            pad_log = [[round(e[0] - T0, 3)] + list(e[1:]) for e in pad.log]
            json.dump({"cues": cues, "script_len": t_stop, "video_len": vd, "pad": pad_log},
                      open(out + ".events.json", "w"), indent=1)
        pad.stick("l", 0, 0)
        pad.stick("r", 0, 0)
        if status().get("mode", "off") != "off":
            sh("omarchy-shell", "joyride", "mode", "off")
        pad.close()
        teardown()


def scene(pad):
    time.sleep(1.5)

    say("Hold Guide to take control", "guide")
    pad.hold("guide", 0.7)
    time.sleep(1.8)

    say("D-pad: move focus", "dpad")
    pad.tap("dpad_right"); time.sleep(0.9)
    pad.tap("dpad_right"); time.sleep(0.9)
    pad.tap("dpad_left"); time.sleep(0.9)
    say("...or the left stick", "stick")
    pad.stick("l", -1, 0); time.sleep(0.5); pad.stick("l", 0, 0); time.sleep(0.8)
    pad.stick("l", 1, 0); time.sleep(0.5); pad.stick("l", 0, 0); time.sleep(1.0)

    say("Bumpers: switch workspace", "ws")
    pad.tap("r1"); time.sleep(1.5)
    pad.tap("l1"); time.sleep(1.4)

    say("Triggers: resize columns", "resize")
    pad.tap("r2"); time.sleep(0.7); pad.tap("r2"); time.sleep(0.9)
    pad.tap("l2"); time.sleep(0.7); pad.tap("l2"); time.sleep(0.7)
    pad.tap("west"); time.sleep(1.2)

    say("Start: the Omarchy menu", "menu")
    pad.tap("start"); time.sleep(1.4)
    for _ in range(3):
        pad.tap("dpad_down"); time.sleep(0.5)
    pad.tap("dpad_up"); time.sleep(0.8)
    pad.tap("east"); time.sleep(1.2)       # Escape

    # point at the left window first so the click visibly moves focus
    pad.tap("dpad_left"); time.sleep(0.8)
    say("L3: your pad is a mouse", "mouse")
    pad.tap("l3"); time.sleep(1.2)
    target = window("demo-nvim")
    cx = target["at"][0] + target["size"][0] // 2
    cy = target["at"][1] + target["size"][1] // 2
    sweep(pad, (cx, cy))
    time.sleep(0.4)
    pad.tap("south"); time.sleep(1.2)      # click
    pad.tap("l3"); time.sleep(0.8)         # back to navigate

    say("Y: type with two thumbsticks", "keyboard")
    pad.tap("north"); time.sleep(1.6)
    type_text(pad, "Hello, Joyride!")
    time.sleep(1.2)
    pad.tap("r3"); time.sleep(1.0)

    say("Hold Guide again: it's all yours", "off")
    pad.hold("guide", 0.7)
    time.sleep(2.5)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The 'trailer' cut: a 27-second, beat-synced gamer/tech ad for Joyride.

    python3 build2.py screen.mp4 press-start.wav out.mp4 [controller-overlay.mov]

Reuses the footage from `drive.py --record` (cue times come from
screen.mp4.events.json) and the 140 BPM track from `music2.py`. Every cut
lands on a beat: 1 beat = 0.4286 s, 64 beats in all.
"""
import json
import os
import subprocess
import sys
import tempfile

FONT = "/usr/share/fonts/TTF/FiraCodeNerdFontMono-Bold.ttf"
ACCENT, MAGENTA, CYAN, BG = "0x8ec63f", "0xff2d95", "0x19f9ff", "0x05060f"
W, H, FPS = 2560, 1440, 30
BEAT = 60.0 / 140
GLYPH = "\U000F02B4"


def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def dt(s, size, color, x, y, extra=""):
    return "drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=%s:x='%s':y='%s'%s" % (
        FONT, esc(s), size, color, x, y, (":" + extra) if extra else "")


def gtext(s, size, y, color, enable="1", x="(w-tw)/2"):
    """Centred headline with a cyan/magenta chromatic-aberration ghost."""
    en = ":enable='%s'" % enable
    return ",".join([
        dt(s, size, CYAN + "@0.75", "%s-7" % x, y, en[1:]),
        dt(s, size, MAGENTA + "@0.75", "%s+7" % x, y, en[1:]),
        dt(s, size, color, x, y, en[1:]),
    ])


def brackets(m=44, ln=90, th=6, color=ACCENT):
    boxes = []
    for (x, y, w, h) in [(m, m, ln, th), (m, m, th, ln),
                         (W - m - ln, m, ln, th), (W - m - th, m, th, ln),
                         (m, H - m - th, ln, th), (m, H - m - ln, th, ln),
                         (W - m - ln, H - m - th, ln, th), (W - m - th, H - m - ln, th, ln)]:
        boxes.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s@0.9:t=fill" % (x, y, w, h, color))
    return ",".join(boxes)


GRID = "drawgrid=w=80:h=80:t=1:c=%s@0.05" % CYAN


def run(cmd):
    subprocess.run(cmd, check=True)


def encode(out, vf, src=None, ss=0.0, t=0.0, lavfi=None):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error"]
    if lavfi:
        cmd += ["-f", "lavfi", "-i", lavfi]
    else:
        cmd += ["-ss", "%.3f" % ss, "-t", "%.3f" % t, "-i", src]
    cmd += ["-vf", vf, "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p", out]
    run(cmd)


def feature(out, src, ss, beats, speed, num, title, sub, zoom_from=None):
    dur = beats * BEAT
    slide = "110+max(0,1-t/0.2)*-700"
    chain = [
        "setpts=(PTS-STARTPTS)/%.3f" % speed, "fps=%d" % FPS, "scale=%d:%d:flags=lanczos" % (W, H),
        "eq=contrast=1.12:saturation=1.25:brightness=-0.02",
    ]
    if zoom_from is not None:
        chain = [chain[0], chain[1], chain[2], "split[a][b]"]
        pre = ",".join(chain[:3]) + ",split[a][b];"
        zoom = ("[b]crop=420:44:655:22,scale=1600:168:flags=lanczos,"
                "drawbox=x=0:y=0:w=iw:h=ih:color=%s:t=6[z];"
                "[a][z]overlay=x=(W-w)/2:y=540:enable='gte(t,%.2f)'," % (ACCENT, zoom_from))
        head = pre + zoom
        tail = []
        vf = head + chain_tail(num, title, sub, slide, dur)
    else:
        vf = ",".join(chain) + "," + chain_tail(num, title, sub, slide, dur)
    encode(out, vf, src=src, ss=ss, t=dur * speed + 0.05)


def chain_tail(num, title, sub, slide, dur):
    parts = [
        "eq=contrast=1.08:saturation=1.3:gamma=1.3",
        "rgbashift=rh=-24:bh=24:gh=6:enable='lt(t,0.16)'",
        "eq=brightness=0.28:enable='lt(t,0.05)'",
        "vignette=PI/5",
        "drawgrid=w=0:h=4:t=1:c=black@0.12",
        "drawbox=x=0:y=50:w=1500:h=210:color=%s@0.78:t=fill" % BG,
        "drawbox=x=0:y=50:w=16:h=210:color=%s:t=fill" % ACCENT,
        dt(num, 170, "#ff2d95", slide, 62),
        dt(title, 112, "white", slide.replace("110", "380"), 52),
        dt(sub, 40, ACCENT, slide.replace("110", "384"), 178),
        dt("P1  ●  CONNECTED", 36, "white", "w-tw-90", 74, "alpha='if(lt(mod(t,0.857),0.6),1,0.35)'"),
        dt(GLYPH + " JOYRIDE", 36, ACCENT, "90", "h-100"),
        brackets(),
        "format=yuv420p",
    ]
    return ",".join(parts)


def intro(out):
    d = 8 * BEAT
    b4 = 4 * BEAT
    vf = ",".join([
        GRID,
        dt("PRESS START", 190, "white", "(w-tw)/2", "(h/2)-150",
           "enable='lt(t,%.3f)':alpha='if(lt(mod(t,%.3f),%.3f),1,0.15)'" % (b4, BEAT * 2, BEAT * 1.4)),
        dt("PLAYER 1   ▪   CONTROLLER CONNECTED", 46, "0x8a8f98", "(w-tw)/2", "(h/2)+90",
           "enable='lt(t,%.3f)'" % b4),
        "rgbashift=rh=-30:bh=30:enable='between(t,0.85,0.92)+between(t,1.28,1.33)+between(t,%.3f,%.3f)'" % (b4, b4 + 0.1),
        gtext("LEVEL UP", 250, "(h/2)-330", "white", "gte(t,%.3f)" % b4),
        gtext("YOUR DESKTOP.", 250, "(h/2)-40", ACCENT, "gte(t,%.3f)" % (b4 + BEAT)),
        brackets(),
        "vignette=PI/4",
        "format=yuv420p",
    ])
    encode(out, vf, lavfi="color=c=%s:s=%dx%d:r=%d:d=%.3f" % (BG, W, H, FPS, d))


def outro(out):
    d = 16 * BEAT
    chips = ["XBOX", "PLAYSTATION", "SWITCH", "GENERIC"]
    cw, gap = 440, 40
    x0 = (W - (len(chips) * cw + (len(chips) - 1) * gap)) // 2
    parts = [GRID]
    parts.append("rgbashift=rh=-34:bh=34:gh=8:enable='lt(t,0.18)+between(t,0.45,0.5)'")
    parts.append(gtext(GLYPH, 230, "(h/2)-470", ACCENT, "gte(t,0)"))
    parts.append(gtext("JOYRIDE", 330, "(h/2)-330", "white", "gte(t,0)"))
    parts.append(dt("FULL GAMEPAD CONTROL FOR OMARCHY", 76, ACCENT, "(w-tw)/2", "(h/2)-20",
                    "enable='gte(t,%.3f)'" % (2 * BEAT)))
    for i, name in enumerate(chips):
        bx = x0 + i * (cw + gap)
        t0 = 4 * BEAT + i * BEAT * 0.5
        parts.append("drawbox=x=%d:y=%d:w=%d:h=104:color=%s@0.9:t=4:enable='gte(t,%.3f)'" % (bx, (H // 2) + 110, cw, ACCENT, t0))
        parts.append(dt(name, 48, "white", "%d+(%d-tw)/2" % (bx, cw), (H // 2) + 142, "enable='gte(t,%.3f)'" % t0))
    parts.append(dt("PLUG IN.  PRESS GUIDE.  RIDE.", 96, "white", "(w-tw)/2", "(h/2)+290",
                    "enable='gte(t,%.3f)'" % (8 * BEAT)))
    parts.append(dt("jgarza.joyride   ·   github.com/jgarza9788/joyride", 44, "0x8a8f98", "(w-tw)/2", "h-250",
                    "enable='gte(t,%.3f)'" % (10 * BEAT)))
    parts.append(dt("PRESS GUIDE TO BEGIN", 56, ACCENT, "(w-tw)/2", "h-120",
                    "enable='gte(t,%.3f)':alpha='if(lt(mod(t,%.3f),%.3f),1,0.1)'" % (12 * BEAT, BEAT * 2, BEAT * 1.4)))
    parts.append(dt("music: Press Start  ·  CC0, made for this video", 28, "0x5d626b", "w-tw-70", "h-80",
                    "enable='gte(t,%.3f)'" % (11 * BEAT)))
    parts += [brackets(), "vignette=PI/4", "format=yuv420p"]
    encode(out, ",".join(parts), lavfi="color=c=%s:s=%dx%d:r=%d:d=%.3f" % (BG, W, H, FPS, d))


def plan(vt):
    """The six feature clips: output start/length in beats, footage start and playback speed."""
    return [
        {"start": 8, "beats": 8, "ss": vt["guide"] - 0.2, "speed": 1.4,
         "num": "01", "title": "TAKE CONTROL", "sub": "HOLD GUIDE  \u00b7  D-PAD  \u00b7  LEFT STICK"},
        {"start": 16, "beats": 4, "ss": vt["ws"] - 0.1, "speed": 1.6,
         "num": "02", "title": "SWITCH WORKSPACES", "sub": "L1  \u00b7  R1"},
        {"start": 20, "beats": 6, "ss": vt["resize"] - 0.1, "speed": 1.55,
         "num": "03", "title": "RESIZE COLUMNS", "sub": "L2  \u00b7  R2  \u00b7  X"},
        {"start": 26, "beats": 4, "ss": vt["menu"] - 0.1, "speed": 1.9,
         "num": "04", "title": "NAVIGATE MENUS", "sub": "START  \u00b7  D-PAD  \u00b7  B"},
        {"start": 30, "beats": 8, "ss": vt["mouse"] - 0.2, "speed": 1.5,
         "num": "05", "title": "MOUSE MODE", "sub": "L3  \u00b7  RIGHT STICK  \u00b7  A"},
        {"start": 38, "beats": 10, "ss": vt["keyboard"] + 0.2, "speed": 1.9,
         "num": "06", "title": "TYPE WITH THUMBSTICKS", "sub": "LEFT STICK  +  RIGHT STICK  +  R2", "typing": vt["keyboard"] + 1.5},
    ]


def main():
    screen, wav, out = sys.argv[1:4]
    controller = sys.argv[4] if len(sys.argv) > 4 else None
    meta = json.load(open(screen + ".events.json"))
    lead = meta["video_len"] - meta["script_len"]
    vt = {c["key"]: c["t"] + lead for c in meta["cues"] if c.get("key")}
    tmp = tempfile.mkdtemp(prefix="joyride-ad-")
    segs = []

    def p(name):
        path = os.path.join(tmp, name)
        segs.append(path)
        return path

    intro(p("00.mp4"))
    for i, seg in enumerate(plan(vt), 1):
        zoom = max(0.0, (seg["typing"] - seg["ss"]) / seg["speed"]) if "typing" in seg else None
        feature(p("%02d.mp4" % i), screen, seg["ss"], seg["beats"], seg["speed"],
                seg["num"], seg["title"], seg["sub"], zoom_from=zoom)
    outro(p("07.mp4"))

    listing = os.path.join(tmp, "list.txt")
    open(listing, "w").write("".join("file '%s'\n" % s for s in segs))
    joined = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", joined])
    total = 64 * BEAT
    intro_end, feat_end = 8 * BEAT, 48 * BEAT
    if controller:
        # the wireframe pad: big and centred in the intro, bottom-right over the features
        graph = ("[2:v]split[s1][s2];[s1]scale=600:-1:flags=lanczos[c1];[s2]scale=900:-1:flags=lanczos[c2];"
                 "[0:v][c1]overlay=x=(W-w)/2:y=H-h-50:enable='lt(t,%.3f)':format=auto[a];"
                 "[a][c2]overlay=x=W-w-60:y=H-h-90:enable='between(t,%.3f,%.3f)':format=auto[v];" % (intro_end, intro_end, feat_end))
        graph += "[1:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,afade=t=out:st=%.2f:d=1.6,loudnorm=I=-13:TP=-1.2:LRA=8[a2]" % (total, total - 1.6)
        run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-i", joined, "-i", wav, "-i", controller,
             "-filter_complex", graph, "-map", "[v]", "-map", "[a2]",
             "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", "%.2f" % total, out])
    else:
        run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-i", joined, "-i", wav,
             "-filter_complex", "[1:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,afade=t=out:st=%.2f:d=1.6,loudnorm=I=-13:TP=-1.2:LRA=8[a]" % (total, total - 1.6),
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-t", "%.2f" % total, out])
    print("wrote %s (%.1fs)" % (out, total))


if __name__ == "__main__":
    main()

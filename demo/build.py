#!/usr/bin/env python3
"""Assemble the showcase: title card + recorded demo + outro + music.

    python3 build.py screen.mp4 joyride.wav out.mp4

screen.mp4 comes from `drive.py --record`, joyride.wav from `music.py`.
Timing is locked to the track (128 BPM, 1.875 s per bar): the demo starts
on bar 4 as the groove kicks in.
"""
import json
import subprocess
import sys

FONT = "/usr/share/fonts/TTF/FiraCodeNerdFontMono-Bold.ttf"
ACCENT, BG = "0x8ec63f", "0x05060f"
W, H, FPS = 2560, 1440, 30
BAR = 60 / 128 * 4
TITLE = 4 * BAR          # 7.5 s
OUTRO = 6.5
GLYPH = "\U000F02B4"      # nf-md-gamepad_variant


def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def text(s, size, color, y, t0, t1, fade=0.18, x="(w-tw)/2"):
    """A centred line that fades in at t0 and (optionally) out at t1."""
    alpha = "if(lt(t,%.3f),0,if(lt(t,%.3f),(t-%.3f)/%.3f,if(lt(t,%.3f),1,if(lt(t,%.3f),(%.3f-t)/%.3f,0))))" % (
        t0, t0 + fade, t0, fade, t1 - fade, t1, t1, fade)
    return ("drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=%s:x=%s:y=%s:alpha='%s'"
            % (FONT, esc(s), size, color, x, y, alpha))


def card(duration, lines):
    chain = ",".join(lines + ["fade=t=in:d=0.25", "fade=t=out:st=%.2f:d=0.35" % (duration - 0.35)])
    return "color=c=%s:s=%dx%d:r=%d:d=%.3f,%s,format=yuv420p" % (BG, W, H, FPS, duration, chain)


def main():
    screen, wav, out = sys.argv[1:4]
    meta = json.load(open(screen + ".events.json"))
    lead = meta["video_len"] - meta["script_len"]   # the recorder started this long before t=0
    cues = meta["cues"]
    demo_len = meta["video_len"]

    beat = BAR / 4
    title = card(TITLE, [
        text("NO MOUSE.", 150, "white", "(h/2)-260", 1 * beat, 3.55),
        text("NO KEYBOARD.", 150, "white", "(h/2)-90", 3 * beat, 3.55),
        text("NO PROBLEM.", 150, ACCENT, "(h/2)+80", 5 * beat, 3.55),
        text(GLYPH + " JOYRIDE", 210, ACCENT, "(h/2)-130", 2 * BAR + 0.25, TITLE, 0.25),
        text("take your machine for a joyride anyways", 56, "white", "(h/2)+130", 2 * BAR + 0.25 + beat * 2, TITLE, 0.25),
    ])

    caps = []
    for i, cue in enumerate(cues):
        t0 = cue["t"] + lead
        t1 = (cues[i + 1]["t"] + lead) if i + 1 < len(cues) else demo_len - 0.2
        if t1 - t0 < 0.3:
            continue
        size = 66
        caps.append(
            "drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=white:x=(w-tw)/2:y=70:"
            "box=1:boxcolor=0x05060fcc:boxborderw=26:alpha='%s'"
            % (FONT, esc(cue["text"]), size,
               "if(lt(t,%.3f),0,if(lt(t,%.3f),(t-%.3f)/0.2,if(lt(t,%.3f),1,if(lt(t,%.3f),(%.3f-t)/0.2,0))))"
               % (t0, t0 + 0.2, t0, t1 - 0.2, t1, t1)))
    # The typed line is tiny at this size, so magnify it while the keyboard is up.
    kb = [c for c in cues if c.get("key") == "keyboard"]
    off = [c for c in cues if c.get("key") == "off"]
    zoom_on, zoom_off = (kb[0]["t"] + lead + 1.3, off[0]["t"] + lead - 0.1) if kb and off else (0, 0)
    zw, zh = 1600, 168
    demo = ("[1:v]fps=%d,scale=%d:%d,split[a][b];"
            "[b]crop=420:44:655:22,scale=%d:%d:flags=lanczos,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=%s:t=6[z];"
            "[a][z]overlay=x=(W-w)/2:y=640:enable='between(t,%.2f,%.2f)',%s,fade=t=in:d=0.3,format=yuv420p"
            % (FPS, W, H, zw, zh, ACCENT, zoom_on, zoom_off, ",".join(caps)))

    outro = card(OUTRO, [
        text(GLYPH + " JOYRIDE", 190, ACCENT, "(h/2)-290", 0.2, OUTRO),
        text("an Omarchy plugin for game controllers", 58, "white", "(h/2)-90", 0.7, OUTRO),
        text("jgarza.joyride", 64, ACCENT, "(h/2)+20", 1.3, OUTRO),
        text("github.com/jgarza9788/joyride", 50, "white", "(h/2)+110", 1.6, OUTRO),
        text("Xbox  ·  PlayStation  ·  Switch  ·  generic", 44, "0xaaaaaa", "(h/2)+210", 2.0, OUTRO),
        text("music: “Joyride (No Mouse, No Keyboard)”  ·  CC0, made for this video", 36, "0x888888",
             "h-110", 2.4, OUTRO),
    ])

    total = TITLE + demo_len + OUTRO
    fc = ("%s[t];%s[d];%s[o];[t][d][o]concat=n=3:v=1:a=0[v];"
          "[2:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,afade=t=out:st=%.2f:d=2.2,loudnorm=I=-14:TP=-1.5:LRA=9[a]"
          % (title, demo, outro, total, total - 2.2))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-stats",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",   # keeps input numbering simple
           "-i", screen, "-i", wav,
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", "%.2f" % total, out]
    print("total %.1fs, lead %.2fs" % (total, lead))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

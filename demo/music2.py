#!/usr/bin/env python3
"""'Press Start': a 140 BPM dark-synth / game-trailer track for the Joyride ad.

Written for this project and released under CC0 / public domain. Reuses the
synth voices in music.py, retuned to 140 BPM, plus a clipped bass, risers and
impacts. E minor, Em-C-G-D.

    python3 music2.py out.wav [bars]
"""
import sys

import numpy as np

import music as m

m.BPM = 140
m.BEAT = 60.0 / m.BPM
m.STEP = m.BEAT / 4
m.BAR = m.BEAT * 4
BEAT, STEP, BAR, SR = m.BEAT, m.STEP, m.BAR, m.SR

CHORDS = [(40, (0, 3, 7)), (36, (0, 4, 7)), (43, (0, 4, 7)), (38, (0, 4, 7))]   # Em C G D


def riser(tr, t0, dur, gain=0.5):
    n = int(dur * SR)
    t = m.tt(n)
    noise = np.random.RandomState(7).randn(n)
    noise = np.diff(noise, prepend=0)
    sweep = np.sin(2 * np.pi * np.cumsum(200 + 3200 * (t / dur) ** 2) / SR)
    sig = (noise * 0.35 + sweep * 0.4) * (t / dur) ** 2.2
    tr.put(tr.drums, t0, sig * gain)


def impact(tr, t0, gain=1.0):
    n = int(2.2 * SR)
    t = m.tt(n)
    boom = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t * 1.6) + 28) / SR) * np.exp(-t * 2.2)
    noise = np.diff(np.random.RandomState(11).randn(n), prepend=0) * np.exp(-t * 3.0) * 0.5
    tr.put(tr.drums, t0, (boom * 0.9 + noise) * gain)
    tr.kicks.append(t0)


def gritty_bass(tr, t0, midi, dur, gain=0.5, drive=3.0):
    n = int(dur * SR)
    sig = m.saw(m.hz(midi), n, 14) + 0.6 * m.pulse(m.hz(midi - 12), n, 0.5)
    sig = np.tanh(sig * drive) * m.env(n, 0.003, 0.05, 1.2)
    tr.put(tr.bus, t0, sig, gain=gain * 0.6)


def blip(tr, t0, midi, dur=0.07, gain=0.18, pan=0.0):
    n = int(dur * SR)
    tr.put(tr.lead, t0, m.pulse(m.hz(midi), n, 0.5) * m.env(n, 0.002, 0.03, 1.0), pan=pan, gain=gain)


def compose(bars):
    tr = m.Track(bars)
    for b in range(bars):
        t0 = b * BAR
        root, tones = CHORDS[b % 4]
        intro = b < 2
        drive = 2 <= b < 12
        outro = b >= 12
        climax = 9 <= b < 12

        if not intro:
            tr.pad(t0, root + 12, tones, BAR * 1.02, gain=0.07 if drive else 0.1)

        for beat in range(4):
            tb = t0 + beat * BEAT
            if drive or (b == 12 and False):
                tr.kick(tb)
                if beat in (1, 3):
                    tr.snare(tb, 0.75)
            if b == 0:
                tr.kick(tb, 0.35 + 0.1 * beat)                       # heartbeat
            if b == 1 and beat < 3:
                tr.kick(tb, 0.55 + 0.1 * beat)
            if outro and beat == 0 and b in (12, 14):
                tr.kick(tb, 0.9)
            if outro and b == 15:
                pass

        if drive:
            for i in range(16):
                tr.hat(t0 + i * STEP, 0.2 if i % 4 == 0 else 0.11)
            for beat in range(4):
                tr.hat(t0 + beat * BEAT + BEAT / 2, 0.24, open_=True)
            for i in range(16):                                      # rolling 16th bass, octave pops
                midi = root - 12 + (12 if i % 8 == 6 else 0) + (7 if i == 15 else 0)
                gritty_bass(tr, t0 + i * STEP, midi, STEP * 0.85, gain=0.55 if i % 4 else 0.7)
            pat = [0, 2, 1, 2, 0, 2, 1, 2]
            for i in range(16):
                tr.arp(t0 + i * STEP, root + 24 + tones[pat[i % 8]] + (12 if i % 8 == 7 else 0),
                       dur=STEP * 0.8, gain=0.13, pan=0.4 if i % 2 else -0.4)
        if climax:
            motif = [(0, 19, 3), (3, 22, 1), (4, 24, 3), (7, 22, 1), (8, 19, 4), (12, 26, 4)]
            for off16, interval, ln in motif:
                tr.lead_note(t0 + off16 * STEP, root + 24 + interval - 19 + 7, ln * STEP * 0.95, gain=0.16)
        if outro:
            for i in range(0, 16, 2):
                tr.arp(t0 + i * STEP, root + 24 + tones[(i // 2) % 3], dur=STEP * 1.6, gain=0.1, pan=0.3)
            if b in (12, 13):
                tr.bass(t0, root - 12, BAR * 0.98, 0.55)

        if intro:
            for i in range(8):   # boot-up blips
                blip(tr, t0 + i * STEP * 2, root + 36 + tones[i % 3] + (12 if i % 4 == 3 else 0),
                     gain=0.08 + 0.01 * b * i, pan=0.3 if i % 2 else -0.3)

    riser(tr, 0.0, 2 * BAR, 0.5)
    for i in range(12):                                              # snare roll into the drop
        tr.snare(1 * BAR + 2 * BEAT + i * STEP * (4 / 3) * 0.75 * 0.0 + i * (2 * BEAT / 12), 0.12 + 0.05 * i)
    impact(tr, 2 * BAR, 1.0)
    impact(tr, 12 * BAR, 1.0)                                         # logo hit
    riser(tr, 14 * BAR, 1 * BAR, 0.45)
    impact(tr, 15 * BAR, 1.1)                                         # last hit; the pad rings out
    for off in (0, 7, 12, 15):
        tr.pad(15 * BAR, 40 + 12, (off,), BAR * 1.9, gain=0.1)
    return tr.render()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "press-start.wav"
    nbars = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    audio = compose(nbars)
    m.write_wav(out, audio)
    print("%s: %.1fs, %d bars at %d BPM" % (out, len(audio) / SR, nbars, m.BPM))

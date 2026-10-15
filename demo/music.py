#!/usr/bin/env python3
"""'Joyride (No Mouse, No Keyboard)': a synthwave track for the Joyride demo.

Written for this project and released under CC0 / public domain. Pure numpy,
no samples: every sound below is a formula. 128 BPM, A minor, Am-F-C-G.

    python3 music.py out.wav [bars]
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 128
BEAT = 60.0 / BPM
STEP = BEAT / 4            # a 16th note
BAR = BEAT * 4

CHORDS = [  # (root MIDI, chord tones as semitone offsets)
    (45, (0, 3, 7)),       # Am
    (41, (0, 4, 7)),       # F
    (48, (0, 4, 7)),       # C
    (43, (0, 4, 7)),       # G
]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def tt(n):
    return np.arange(n) / SR


def saw(f, n, harmonics_cap=16):
    t = tt(n)
    out = np.zeros(n)
    k = 1
    while k <= harmonics_cap and f * k < SR / 2 - 1000:
        out += np.sin(2 * np.pi * f * k * t) / k
        k += 1
    return out * (2 / np.pi)


def pulse(f, n, width=0.25, harmonics_cap=24):
    # difference of two saws gives a band-limited pulse
    t = tt(n)
    out = np.zeros(n)
    k = 1
    while k <= harmonics_cap and f * k < SR / 2 - 1000:
        out += np.sin(np.pi * k * width) * np.cos(2 * np.pi * f * k * t - np.pi * k * width) / k
        k += 1
    return out * (2 / np.pi)


def env(n, attack, release, curve=2.0):
    t = tt(n)
    a = np.minimum(1.0, t / max(attack, 1e-4))
    r = np.minimum(1.0, (n / SR - t) / max(release, 1e-4))
    return a * np.clip(r, 0, 1) ** curve


class Track:
    def __init__(self, bars):
        self.n = int((bars * BAR + 3.0) * SR)
        self.drums = np.zeros((self.n, 2))
        self.bus = np.zeros((self.n, 2))     # bass, pad, arp: ducked by the kick
        self.lead = np.zeros((self.n, 2))
        self.kicks = []

    def put(self, buf, start, sig, pan=0.0, gain=1.0):
        i = int(start * SR)
        if i >= self.n:
            return
        sig = sig[: self.n - i]
        left = gain * (1 - max(0, pan))
        right = gain * (1 + min(0, pan))
        buf[i:i + len(sig), 0] += sig * left
        buf[i:i + len(sig), 1] += sig * right

    # ── drums ──
    def kick(self, t0, gain=1.0):
        n = int(0.32 * SR)
        t = tt(n)
        f = 48 + 120 * np.exp(-t * 28)
        phase = 2 * np.pi * np.cumsum(f) / SR
        sig = np.sin(phase) * np.exp(-t * 9) * 1.0 + np.sin(phase * 0.5) * np.exp(-t * 14) * 0.2
        click = np.random.RandomState(1).randn(n) * np.exp(-t * 400) * 0.25
        self.put(self.drums, t0, (sig + click) * gain)
        self.kicks.append(t0)

    def snare(self, t0, gain=0.7):
        n = int(0.28 * SR)
        t = tt(n)
        noise = np.random.RandomState(int(t0 * 1000) % 9999).randn(n)
        noise = np.diff(noise, prepend=0)   # tilt bright
        tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28)
        sig = (noise * 0.45 + tone * 0.5) * np.exp(-t * 16)
        self.put(self.drums, t0, sig * gain, pan=0.05)

    def hat(self, t0, gain=0.25, open_=False):
        n = int((0.22 if open_ else 0.05) * SR)
        t = tt(n)
        noise = np.random.RandomState(int(t0 * 777) % 9999).randn(n)
        noise = np.diff(noise, 2, prepend=[0, 0])
        sig = noise * np.exp(-t * (14 if open_ else 70))
        self.put(self.drums, t0, sig * gain * 0.5, pan=-0.2 if open_ else 0.2)

    # ── tonal ──
    def bass(self, t0, midi, dur, gain=0.55):
        n = int(dur * SR)
        sig = (saw(hz(midi), n, 10) + 0.5 * np.sin(2 * np.pi * hz(midi) * tt(n))) * env(n, 0.004, 0.06, 1.2)
        self.put(self.bus, t0, sig, gain=gain)

    def pad(self, t0, root, tones, dur, gain=0.11):
        n = int(dur * SR)
        e = env(n, 0.5, 0.6, 1.0)
        for off in tones:
            for det in (-0.12, 0.0, 0.12):
                f = hz(root + 12 + off + det / 12 * 12 * 0.02)
                self.put(self.bus, t0, saw(f * (1 + det * 0.004), n, 8) * e, pan=det * 3, gain=gain)

    def arp(self, t0, midi, dur=STEP * 0.9, gain=0.2, pan=0.0):
        n = int(dur * SR)
        sig = pulse(hz(midi), n, 0.25) * env(n, 0.002, 0.05, 1.5)
        self.put(self.bus, t0, sig, pan=pan, gain=gain)
        # a ghost echo three 16ths later, other side
        self.put(self.bus, t0 + STEP * 3, sig, pan=-pan if pan else 0.5, gain=gain * 0.35)

    def lead_note(self, t0, midi, dur, gain=0.2):
        n = int(dur * SR)
        t = tt(n)
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.25)
        f = hz(midi) * vib
        phase = 2 * np.pi * np.cumsum(f) / SR
        sig = (np.sign(np.sin(phase)) * 0.45 + saw(hz(midi), n, 8) * 0.55) * env(n, 0.01, 0.12, 1.4)
        self.put(self.lead, t0, sig, gain=gain)
        self.put(self.lead, t0 + STEP * 2, sig, pan=0.4, gain=gain * 0.3)

    # ── mixdown ──
    def render(self):
        duck = np.ones(self.n)
        t = tt(self.n)
        for k in self.kicks:
            i = int(k * SR)
            seg = t[i:] - k
            duck[i:] = np.minimum(duck[i:], 1 - 0.65 * np.exp(-seg / 0.11))
        mix = self.drums * 0.9 + self.bus * duck[:, None] + self.lead * 0.9
        # tiny stereo-safe soft clip and normalise
        mix = np.tanh(mix * 1.15)
        peak = np.max(np.abs(mix))
        return mix / peak * 0.89


def compose(bars):
    tr = Track(bars)
    # section map: (first bar, last bar exclusive, flags)
    # section boundaries scale with the length: 32 bars = 4 intro, 6 groove, 8 drive, 4 break, 8 final, 2 outro
    scale = bars / 32.0
    b_groove, b_drive, b_break, b_final = [int(round(x * scale)) for x in (4, 10, 18, 22)]
    br1 = b_final

    def sec(b):
        if b < b_groove:  return "intro"
        if b < b_drive:   return "groove"
        if b < b_break:   return "drive"
        if b < b_final:   return "break"
        if b < bars - 2:  return "final"
        return "outro"

    lead_motif = [  # (16th offset in bar, scale degree offset from A, length in 16ths)
        [(0, 12, 6), (6, 15, 2), (8, 14, 4), (12, 12, 4)],
        [(0, 12, 6), (6, 17, 2), (8, 16, 4), (12, 12, 4)],
        [(0, 19, 6), (6, 16, 2), (8, 14, 4), (12, 12, 4)],
        [(0, 14, 4), (4, 16, 4), (8, 19, 6), (14, 14, 2)],
    ]
    arp_pattern = [0, 1, 2, 1, 2, 1, 0, 1]   # chord-tone indices, doubled to 16 steps

    for b in range(bars):
        s = sec(b)
        t0 = b * BAR
        root, tones = CHORDS[b % 4]
        pat = b % 4

        # pad: everywhere except the very last bars
        if s != "outro":
            tr.pad(t0, root, tones, BAR * 1.02, gain=0.12 if s in ("intro", "break") else 0.085)

        # drums
        has_kick = s in ("groove", "drive", "final") or (s == "break" and b >= br1 - 2) or (s == "intro" and b >= b_groove - 1)
        for beat in range(4):
            tb = t0 + beat * BEAT
            if has_kick and not (s == "break" and b < br1 - 1):
                tr.kick(tb)
            if s in ("groove", "drive", "final") and beat in (1, 3):
                tr.snare(tb)
            if s == "break" and b >= br1 - 4 and beat in (1, 3):
                tr.snare(tb, 0.35 + 0.1 * (b - (br1 - 4)))
        if s in ("intro", "groove", "drive", "final") or (s == "break" and b >= br1 - 2):
            for i in range(8):
                tr.hat(t0 + i * BEAT / 2 + BEAT / 4 * 0, 0.18 if i % 2 == 0 else 0.1)
            if s in ("drive", "final"):
                for beat in range(4):
                    tr.hat(t0 + beat * BEAT + BEAT / 2, 0.22, open_=True)
        if s == "break" and b == br1 - 1:   # snare roll into the final drop
            for i in range(16):
                tr.snare(t0 + i * STEP, 0.15 + 0.04 * i)

        # bass: driving eighths with an octave pop
        if s in ("groove", "drive", "final"):
            for i in range(8):
                m = root - 12 + (12 if i % 4 == 3 else 0)
                tr.bass(t0 + i * BEAT / 2, m, BEAT / 2 * 0.92)
        elif s == "break" and b >= br1 - 4:
            tr.bass(t0, root - 12, BAR * 0.95, 0.5)

        # arp: 16ths, brighter in the final
        if s in ("groove", "drive", "final", "break"):
            octave = 24 if s in ("final", "drive") else 12
            for i in range(16):
                idx = arp_pattern[i % 8]
                tr.arp(t0 + i * STEP, root + octave + tones[idx] + (12 if i % 8 == 7 else 0),
                       gain=0.17 if s != "final" else 0.2, pan=0.35 if i % 2 else -0.35)
        elif s == "intro" and b >= 1:
            for i in range(0, 16, 2):
                tr.arp(t0 + i * STEP, root + 24 + tones[arp_pattern[(i // 2) % 8] % 3], gain=0.12, pan=0.3)

        # lead
        if s in ("drive", "final"):
            for off16, interval, ln in lead_motif[pat]:
                tr.lead_note(t0 + off16 * STEP, 57 + interval - 12 + (12 if s == "final" else 0),
                             ln * STEP * 0.95, gain=0.17)

    # final hit and ring-out on the last downbeat
    end = (bars - 2) * BAR
    tr.kick(end, 1.1)
    tr.snare(end, 0.8)
    for off in (0, 3, 7, 12):
        tr.pad(end, 45, (off,), BAR * 1.8, gain=0.1)
    tr.lead_note(end, 69, BAR * 1.6, gain=0.2)
    return tr.render()


def write_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "joyride.wav"
    nbars = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    audio = compose(nbars)
    write_wav(out, audio)
    print("%s: %.1fs, %d bars at %d BPM" % (out, len(audio) / SR, nbars, BPM))

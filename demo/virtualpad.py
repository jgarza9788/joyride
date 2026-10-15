"""A software Xbox-style controller made through /dev/uinput, for demos and tests.

joyride sees it exactly like a real pad. Usage:

    pad = VirtualPad()           # appears in /dev/input within ~2 s
    pad.tap("south"); pad.hold("guide", 0.6); pad.stick("l", 0, -1); pad.trigger("r", 1)
    pad.close()
"""
import fcntl
import os
import struct
import time

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EVENT = struct.Struct("llHHi")

# Names are physical positions, matching bin/mappings.py's xbox profile
# (xpad reports the west button as BTN_NORTH and the north as BTN_WEST).
BUTTONS = {
    "south": 0x130, "east": 0x131, "west": 0x133, "north": 0x134,
    "l1": 0x136, "r1": 0x137, "select": 0x13A, "start": 0x13B, "guide": 0x13C,
    "l3": 0x13D, "r3": 0x13E,
}
HAT = {"dpad_left": (16, -1), "dpad_right": (16, 1), "dpad_up": (17, -1), "dpad_down": (17, 1)}
STICKS = {"lx": 0, "ly": 1, "rx": 3, "ry": 4}
TRIGGERS = {"lt": 2, "rt": 5}


class VirtualPad:
    def __init__(self, name="Joyride Demo Pad"):
        self.log = []          # (monotonic time, kind, name, value...) for every input, for overlays
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for code in BUTTONS.values():
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
        absmin, absmax = [0] * 64, [0] * 64
        for code in STICKS.values():
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            absmin[code], absmax[code] = -32768, 32767
        for code in TRIGGERS.values():
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            absmin[code], absmax[code] = 0, 255
        for code in (16, 17):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            absmin[code], absmax[code] = -1, 1
        dev = name.encode().ljust(80, b"\0")
        dev += struct.pack("<HHHHi", 0x03, 0x045E, 0x028E, 1, 0)
        dev += struct.pack("<64i", *absmax) + struct.pack("<64i", *absmin) + bytes(64 * 4 * 2)
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def _send(self, typ, code, val):
        os.write(self.fd, EVENT.pack(0, 0, typ, code, val))

    def _sync(self):
        self._send(EV_SYN, 0, 0)

    def button(self, name, down):
        self.log.append((time.monotonic(), "btn", name, 1 if down else 0))
        if name in ("l2", "r2"):
            self.trigger(name[0], 1.0 if down else 0.0)
            return
        if name in HAT:
            axis, direction = HAT[name]
            self._send(EV_ABS, axis, direction if down else 0)
        else:
            self._send(EV_KEY, BUTTONS[name], 1 if down else 0)
        self._sync()

    def tap(self, name, secs=0.08):
        self.button(name, True)
        time.sleep(secs)
        self.button(name, False)

    def hold(self, name, secs):
        self.button(name, True)
        time.sleep(secs)
        self.button(name, False)

    def stick(self, which, x, y):
        """which = 'l' or 'r'; x and y in -1..1 (up is negative y)."""
        self.log.append((time.monotonic(), "stick", which, x, y))
        self._send(EV_ABS, STICKS[which + "x"], int(max(-1, min(1, x)) * 32767))
        self._send(EV_ABS, STICKS[which + "y"], int(max(-1, min(1, y)) * 32767))
        self._sync()

    def trigger(self, which, amount):
        self.log.append((time.monotonic(), "trig", which, amount))
        self._send(EV_ABS, TRIGGERS[which + "t"], int(max(0, min(1, amount)) * 255))
        self._sync()

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)

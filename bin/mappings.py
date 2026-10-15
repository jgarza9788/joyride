"""Controller profiles: evdev codes -> logical joyride names.

Logical buttons are named by physical position, not by label, because the
labels differ per vendor: south east west north, l1 r1 l2 r2, l3 r3,
select start guide, dpad_up dpad_down dpad_left dpad_right.

Logical axes: lx ly rx ry (sticks, -1..1, up is negative) and lt rt (0..1).
"""

# evdev constants
BTN_SOUTH, BTN_EAST, BTN_C = 0x130, 0x131, 0x132
BTN_NORTH, BTN_WEST, BTN_Z = 0x133, 0x134, 0x135
BTN_TL, BTN_TR, BTN_TL2, BTN_TR2 = 0x136, 0x137, 0x138, 0x139
BTN_SELECT, BTN_START, BTN_MODE = 0x13A, 0x13B, 0x13C
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223
BTN_JOYSTICK = 0x120
BTN_TOUCH = 0x14A

ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0, 1, 2, 3, 4, 5
ABS_HAT0X, ABS_HAT0Y = 16, 17

VENDOR_MICROSOFT = 0x045E
VENDOR_SONY = 0x054C
VENDOR_NINTENDO = 0x057E

# The Xbox driver (xpad) reports the *west* button as BTN_X (== BTN_NORTH,
# 0x133) and the *north* button as BTN_Y (== BTN_WEST, 0x134). PlayStation
# and Nintendo drivers report true positions.
_XBOX_FACE = {BTN_SOUTH: "south", BTN_EAST: "east", BTN_NORTH: "west", BTN_WEST: "north"}
_POSITIONAL_FACE = {BTN_SOUTH: "south", BTN_EAST: "east", BTN_NORTH: "north", BTN_WEST: "west"}

_COMMON = {
    BTN_TL: "l1", BTN_TR: "r1", BTN_TL2: "l2", BTN_TR2: "r2",
    BTN_SELECT: "select", BTN_START: "start", BTN_MODE: "guide",
    BTN_THUMBL: "l3", BTN_THUMBR: "r3",
    BTN_DPAD_UP: "dpad_up", BTN_DPAD_DOWN: "dpad_down",
    BTN_DPAD_LEFT: "dpad_left", BTN_DPAD_RIGHT: "dpad_right",
}

# Classic DirectInput pads (no BTN_SOUTH, buttons start at BTN_JOYSTICK).
# Order follows the most common generic layout; override per device in
# ~/.config/jgarza.joyride/mappings.json when yours differs.
_GENERIC_ORDER = ["south", "east", "west", "north", "l1", "r1", "l2", "r2",
                  "select", "start", "l3", "r3"]


def is_gamepad(keys, abs_codes):
    """True for a device that looks like a controller (not a touchpad/IMU)."""
    if ABS_X not in abs_codes or ABS_Y not in abs_codes:
        return False
    if BTN_TOUCH in keys:
        return False
    return BTN_SOUTH in keys or BTN_JOYSTICK in keys or BTN_TL in keys


def classify(vendor, product, keys, abs_codes, overrides=None):
    """Return a profile: {kind, buttons{code:name}, axes{code:(name,type)}}."""
    if vendor == VENDOR_MICROSOFT:
        kind = "xbox"
    elif vendor == VENDOR_SONY:
        kind = "playstation"
    elif vendor == VENDOR_NINTENDO:
        kind = "nintendo"
    else:
        kind = "generic"

    buttons = dict(_COMMON)
    if BTN_SOUTH in keys or BTN_TL in keys:
        buttons.update(_XBOX_FACE if kind == "xbox" else _POSITIONAL_FACE)
    else:
        buttons = {}
        for i, name in enumerate(_GENERIC_ORDER):
            buttons[BTN_JOYSTICK + i] = name

    axes = {ABS_X: ("lx", "stick"), ABS_Y: ("ly", "stick")}
    if ABS_RX in abs_codes and ABS_RY in abs_codes:
        axes[ABS_RX] = ("rx", "stick")
        axes[ABS_RY] = ("ry", "stick")
        if ABS_Z in abs_codes:
            axes[ABS_Z] = ("lt", "trigger")
        if ABS_RZ in abs_codes:
            axes[ABS_RZ] = ("rt", "trigger")
    elif ABS_Z in abs_codes and ABS_RZ in abs_codes:
        # DirectInput: Z/RZ are the right stick, triggers are buttons.
        axes[ABS_Z] = ("rx", "stick")
        axes[ABS_RZ] = ("ry", "stick")
    axes[ABS_HAT0X] = ("hat_x", "hat")
    axes[ABS_HAT0Y] = ("hat_y", "hat")

    if overrides:
        for code, name in (overrides.get("buttons") or {}).items():
            buttons[int(code)] = name
        for code, spec in (overrides.get("axes") or {}).items():
            axes[int(code)] = (spec[0], spec[1])
    return {"kind": kind, "buttons": buttons, "axes": axes}


def normalize(value, lo, hi, axis_type):
    """Scale a raw axis reading. sticks -1..1, triggers 0..1, hats -1..1."""
    if axis_type == "hat":
        return -1 if value < 0 else (1 if value > 0 else 0)
    span = hi - lo
    if span <= 0:
        return 0.0
    unit = (value - lo) / float(span)
    if axis_type == "trigger":
        return max(0.0, min(1.0, unit))
    return max(-1.0, min(1.0, unit * 2.0 - 1.0))

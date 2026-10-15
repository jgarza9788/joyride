import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import mappings as m  # noqa: E402

PAD_KEYS = {m.BTN_SOUTH, m.BTN_EAST, m.BTN_NORTH, m.BTN_WEST, m.BTN_TL, m.BTN_TR,
            m.BTN_SELECT, m.BTN_START, m.BTN_MODE, m.BTN_THUMBL, m.BTN_THUMBR}
STD_ABS = {0, 1, 2, 3, 4, 5, 16, 17}


class Classify(unittest.TestCase):
    def test_xbox_face_buttons_swap(self):
        p = m.classify(0x045E, 0x028E, PAD_KEYS, STD_ABS)
        self.assertEqual(p["kind"], "xbox")
        self.assertEqual(p["buttons"][m.BTN_NORTH], "west")   # Xbox X
        self.assertEqual(p["buttons"][m.BTN_WEST], "north")   # Xbox Y

    def test_playstation_positional(self):
        p = m.classify(0x054C, 0x09CC, PAD_KEYS, STD_ABS)
        self.assertEqual(p["kind"], "playstation")
        self.assertEqual(p["buttons"][m.BTN_NORTH], "north")
        self.assertEqual(p["axes"][m.ABS_Z], ("lt", "trigger"))

    def test_nintendo_kind(self):
        p = m.classify(0x057E, 0x2009, PAD_KEYS, STD_ABS)
        self.assertEqual(p["kind"], "nintendo")
        self.assertEqual(p["buttons"][m.BTN_SOUTH], "south")

    def test_directinput_pad(self):
        p = m.classify(0x0079, 0x0122, {0x120 + i for i in range(12)}, {0, 1, 2, 5, 16, 17})
        self.assertEqual(p["kind"], "generic")
        self.assertEqual(p["buttons"][0x120], "south")
        self.assertEqual(p["axes"][m.ABS_Z], ("rx", "stick"))
        self.assertNotIn(m.ABS_RX, p["axes"])

    def test_override(self):
        p = m.classify(1, 2, {0x120}, {0, 1}, {"buttons": {"288": "north"}})
        self.assertEqual(p["buttons"][0x120], "north")

    def test_is_gamepad(self):
        self.assertTrue(m.is_gamepad(PAD_KEYS, STD_ABS))
        self.assertFalse(m.is_gamepad(PAD_KEYS | {m.BTN_TOUCH}, STD_ABS))
        self.assertFalse(m.is_gamepad({0x110}, {0, 1}))
        self.assertFalse(m.is_gamepad(PAD_KEYS, set()))


class Normalize(unittest.TestCase):
    def test_stick(self):
        self.assertAlmostEqual(m.normalize(0, 0, 255, "stick"), -1.0)
        self.assertAlmostEqual(m.normalize(255, 0, 255, "stick"), 1.0)
        self.assertAlmostEqual(m.normalize(127.5, 0, 255, "stick"), 0.0)

    def test_trigger_and_hat(self):
        self.assertEqual(m.normalize(255, 0, 255, "trigger"), 1.0)
        self.assertEqual(m.normalize(-1, -1, 1, "hat"), -1)
        self.assertEqual(m.normalize(0, 0, 0, "stick"), 0.0)


if __name__ == "__main__":
    unittest.main()

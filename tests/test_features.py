"""Functional checks independent of Windows and Qt installation."""
from io import BytesIO
import unittest
import wave

from heerlen.connect import SERVER, make_uri
from heerlen.hotkeys import PTT_CHOICES
from heerlen.roger import generate_three_tone_wav


class FeaturesTests(unittest.TestCase):
    def test_server_is_fixed(self):
        self.assertEqual(SERVER, "heerlen.mijnts3.nl")
        self.assertEqual(make_uri("Michiel"), "ts3server://heerlen.mijnts3.nl?nickname=Michiel")

    def test_encode_nickname_safely(self):
        self.assertEqual(make_uri("Jan & Piet"),
                         "ts3server://heerlen.mijnts3.nl?nickname=Jan%20%26%20Piet")
        for invalid in ("a", "", "x" * 31, "abc\nx"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                make_uri(invalid)

    def test_ptt_choices(self):
        self.assertEqual(PTT_CHOICES["F9"], 0x78)
        self.assertIn("Muis zijknop 1", PTT_CHOICES)

    def test_three_tone_wave(self):
        raw = generate_three_tone_wav()
        with wave.open(BytesIO(raw), "rb") as f:
            self.assertEqual(f.getnchannels(), 1)
            self.assertEqual(f.getsampwidth(), 2)
            self.assertEqual(f.getframerate(), 24000)
            self.assertEqual(f.getnframes(), 9000)


if __name__ == "__main__":
    unittest.main()

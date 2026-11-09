"""Headless check of the real Windows UI; requires PySide6 (provided in CI)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from heerlen.ui import MainWindow, SettingsDialog


class UISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_initializes_without_clientquery(self):
        window = MainWindow()
        try:
            self.assertEqual(window.windowTitle(), "Teamspeak Heerlen PC")
            self.assertIn("Verbinden met Heerlen", window.join_server_btn.text())
            self.assertFalse(window.ptt_button.isEnabled())
            self.assertEqual(window.background_view.preset, window.cfg.get("background", "Nachtblauw"))
        finally:
            window.close()

    def test_user_settings(self):
        dialog = SettingsDialog({"ptt_key": "F10", "roger": False, "background": "Neon paars"})
        result = dialog.values()
        self.assertEqual(result["ptt_key"], "F10")
        self.assertFalse(result["roger"])
        self.assertEqual(result["background"], "Neon paars")
        dialog.close()


if __name__ == "__main__":
    unittest.main()

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

    @classmethod
    def tearDownClass(cls):
        cls.app.processEvents()
        cls.app.quit()

    def test_main_window_initializes_without_clientquery(self):
        window = MainWindow()
        try:
            self.assertEqual(window.windowTitle(), "Teamspeak Heerlen PC")
            self.assertIn("Verbinden met Heerlen", window.join_server_btn.text())
            self.assertFalse(window.ptt_button.isEnabled())
            self.assertEqual(window.background_view.preset, window.cfg.get("background", "Nachtblauw"))
        finally:
            window.ptt_timer.stop()
            window.close()
            window.deleteLater()

    def test_without_microphone_server_stays_connected(self):
        window = MainWindow()
        try:
            window.show_snapshot({
                "connected": True, "server_name": "Heerlen", "mic_ready": False,
                "output_ready": False, "channels": [], "users": [], "talking": [],
            })
            self.assertFalse(window.ptt_button.isEnabled())
            self.assertIn("NIET GEVONDEN", window.mic_indicator.text())
            self.assertIn("Verbonden", window.status_label.text())
            window.press_ptt()
            self.assertFalse(window._ptt_pressed)
        finally:
            window.ptt_timer.stop()
            window.close()
            window.deleteLater()

    def test_user_settings(self):
        dialog = SettingsDialog({"ptt_key": "F10", "roger": False, "background": "Neon paars"})
        result = dialog.values()
        self.assertEqual(result["ptt_key"], "F10")
        self.assertEqual(result["microphone"], "Standaard (Windows)")
        self.assertFalse(result["roger"])
        self.assertEqual(result["background"], "Neon paars")
        dialog.close()


if __name__ == "__main__":
    unittest.main()

"""Confirm local JSON protocol and no installed TS3 dependency."""
import unittest

from heerlen.connect import make_uri
from heerlen.native import NativeWorker


class NativeTests(unittest.TestCase):
    def test_worker_commands(self):
        worker = NativeWorker("HeerlenTest", lambda _: None, lambda _: None)
        worker.send("join", "123")
        worker.send("chat", "Hallo!")
        worker.send("ptt_on")
        worker.send("roger", "1")
        self.assertEqual(worker.commands.get_nowait(), {"action": "join", "cid": 123})
        self.assertEqual(worker.commands.get_nowait(), {"action": "chat", "text": "Hallo!"})
        self.assertEqual(worker.commands.get_nowait(), {"action": "ptt_on"})
        self.assertEqual(worker.commands.get_nowait(), {"action": "roger", "enabled": True})

    def test_validation(self):
        with self.assertRaises(ValueError):
            NativeWorker("A", lambda _: None, lambda _: None)


if __name__ == "__main__":
    unittest.main()

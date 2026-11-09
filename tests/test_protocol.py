"""Run via python -m unittest discover -s tests -v."""
import unittest

from heerlen.query import parse_fields, parse_rows, sort_channel_tree, ts_escape, ts_unescape


class TeamSpeakQueryTests(unittest.TestCase):
    def test_escape_round_trip(self):
        value = "Hallo \n TeamSpeak | test \\ x /"
        self.assertEqual(ts_unescape(ts_escape(value)), value)

    def test_parse_multirow(self):
        rows = parse_rows(r"clid=1 client_nickname=Jan\sHeerlen|clid=2 client_nickname=Anna\pPC")
        self.assertEqual(rows[0]["client_nickname"], "Jan Heerlen")
        self.assertEqual(rows[1]["client_nickname"], "Anna|PC")

    def test_unknown_escape_preserved(self):
        self.assertEqual(ts_unescape(r"test\q"), r"test\q")

    def test_parse_error_fields(self):
        self.assertEqual(parse_fields(r"error id=256 msg=command\snot\sfound")["msg"], "command not found")

    def test_channel_tree_nested(self):
        items = [
            {"cid": "3", "pid": "1", "channel_name": "Sub"},
            {"cid": "2", "pid": "0", "channel_name": "B", "channel_order": "1"},
            {"cid": "1", "pid": "0", "channel_name": "A", "channel_order": "0"},
        ]
        self.assertEqual([(x["cid"], depth) for x, depth in sort_channel_tree(items)],
                         [("1", 0), ("3", 1), ("2", 0)])

    def test_channel_tree_cycle(self):
        items = [{"cid": "1", "pid": "2"}, {"cid": "2", "pid": "1"}]
        self.assertEqual(len(sort_channel_tree(items)), 2)


if __name__ == "__main__":
    unittest.main()

"""Local TeamSpeak 3 ClientQuery protocol and background polling.

The TeamSpeak desktop client owns all audio and server connections.
Only the loopback ClientQuery port is contacted; we do NOT send keys over WAN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import queue
import socket
import threading
import time
from typing import Callable

CLIENTQUERY_HOST = "127.0.0.1"
CLIENTQUERY_PORT = 25639


def ts_unescape(value: str) -> str:
    """Decode TeamSpeak query values without treating other escapes specially."""
    mapping = {"s": " ", "p": "|", "/": "/", "\\": "\\", "a": "\a",
               "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            if nxt in mapping:
                result.append(mapping[nxt])
                index += 2
                continue
        result.append(value[index])
        index += 1
    return "".join(result)


def ts_escape(value: str) -> str:
    """Query-safe encoding; never insert untrusted text as raw commands."""
    mapping = {"\\": "\\\\", "/": "\\/", " ": "\\s", "|": "\\p",
               "\a": "\\a", "\b": "\\b", "\f": "\\f", "\n": "\\n",
               "\r": "\\r", "\t": "\\t", "\v": "\\v"}
    return "".join(mapping.get(c, c) for c in value)


def parse_fields(text: str) -> dict[str, str]:
    result = {}
    for chunk in text.split(" "):
        if not chunk:
            continue
        name, sep, value = chunk.partition("=")
        if sep:
            result[name] = ts_unescape(value)
    return result


def parse_rows(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    return [parse_fields(row) for row in text.split("|") if row.strip()]


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


@dataclass
class Snapshot:
    connected: bool = False
    server_name: str = "TeamSpeak 3"
    channel_id: int = 0
    my_id: int = 0
    channels: list[dict[str, str]] = field(default_factory=list)
    users: list[dict[str, str]] = field(default_factory=list)
    talking: list[int] = field(default_factory=list)
    problem: str = ""

    def as_dict(self) -> dict:
        return {
            "connected": self.connected, "server_name": self.server_name,
            "channel_id": self.channel_id, "my_id": self.my_id,
            "channels": self.channels, "users": self.users,
            "talking": self.talking, "problem": self.problem,
        }


def sort_channel_tree(channels: list[dict[str, str]]) -> list[tuple[dict[str, str], int]]:
    """Flatten channels in parent/sibling order, protecting against cycles."""
    by_parent: dict[int, list[dict[str, str]]] = {}
    ids = {_int(ch.get("cid")) for ch in channels}
    for channel in channels:
        parent = _int(channel.get("pid"))
        if parent not in ids or parent == _int(channel.get("cid")):
            parent = 0
        by_parent.setdefault(parent, []).append(channel)
    def sibling_sort(items: list[dict[str, str]]) -> list[dict[str, str]]:
        pending = list(items)
        ordered = []
        previous = 0
        while pending:
            matching = [ch for ch in pending if _int(ch.get("channel_order")) == previous]
            chosen = min(matching or pending, key=lambda ch: _int(ch.get("cid")))
            pending.remove(chosen)
            ordered.append(chosen)
            previous = _int(chosen.get("cid"))
        return ordered
    result: list[tuple[dict[str, str], int]] = []
    visited: set[int] = set()
    def descend(parent: int, depth: int) -> None:
        for channel in sibling_sort(by_parent.get(parent, [])):
            cid = _int(channel.get("cid"))
            if cid in visited:
                continue
            visited.add(cid)
            result.append((channel, depth))
            descend(cid, depth + 1)
    descend(0, 0)
    # Isolated/cyclic graph entries should remain visible.
    for channel in channels:
        cid = _int(channel.get("cid"))
        if cid not in visited:
            visited.add(cid)
            result.append((channel, 0))
    return result


class QueryError(RuntimeError):
    pass


class ClientQueryConnection:
    """Persistent, one-thread-at-a-time line protocol session."""

    def __init__(self, on_event: Callable[[str], None] | None = None):
        self.socket: socket.socket | None = None
        self.buffer = b""
        self.lines: list[str] = []
        self.on_event = on_event or (lambda _: None)

    def connect(self) -> None:
        self.socket = socket.create_connection(
            (CLIENTQUERY_HOST, CLIENTQUERY_PORT), timeout=4
        )
        self.socket.settimeout(4)

    def close(self) -> None:
        s, self.socket = self.socket, None
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()

    def _get_line(self) -> str:
        while not self.lines:
            if self.socket is None:
                raise QueryError("ClientQuery-verbinding gesloten.")
            block = self.socket.recv(16384)
            if not block:
                raise QueryError("TeamSpeak ClientQuery heeft de verbinding gesloten.")
            self.buffer += block
            if len(self.buffer) > 2_000_000:
                raise QueryError("Te grote ClientQuery-reactie.")
            while b"\n" in self.buffer:
                first, self.buffer = self.buffer.split(b"\n", 1)
                self.lines.append(first.rstrip(b"\r").decode("utf-8", errors="replace"))
        return self.lines.pop(0)

    def command(self, request: str) -> list[dict[str, str]]:
        if "\n" in request or "\r" in request:
            raise ValueError("Ongeldige ClientQuery-opdracht.")
        if self.socket is None:
            raise QueryError("Niet verbonden met ClientQuery.")
        self.socket.sendall((request + "\n").encode("utf-8"))
        response = []
        while True:
            line = self._get_line()
            if not line:
                continue
            if line.startswith("notify"):
                self.on_event(line)
                continue
            if line.startswith("error "):
                status = parse_fields(line)
                if status.get("id") != "0":
                    raise QueryError(status.get("msg", "Onbekende ClientQuery-fout"))
                return parse_rows("".join(response))
            # The plugin writes a welcome banner when connected.
            if line.startswith(("TS3 Client", "Welcome to", "Copyright")):
                continue
            response.append(line)


class ClientQueryWorker(threading.Thread):
    """Collects live ClientQuery data off the Qt UI thread."""

    def __init__(self, api_key: str, publish: Callable[[dict], None],
                 notify: Callable[[str], None], *, interval: float = 2.0):
        super().__init__(daemon=True, name="TS-Heerlen-ClientQuery")
        self.api_key = api_key
        self.publish = publish
        self.notify = notify
        self.interval = interval
        self.commands: queue.Queue[tuple[str, str]] = queue.Queue()
        self.stop_event = threading.Event()
        self.connection: ClientQueryConnection | None = None
        self.my_id = 0
        self.channel_id = 0
        self.talking: set[int] = set()
        self.ptt_down = False
        self.ptt_ever_used = False

    def send(self, kind: str, payload: str = "") -> None:
        self.commands.put((kind, payload))

    def stop(self) -> None:
        self.stop_event.set()
        # Allow command read to finish; don't force-close socket across threads.

    def _event(self, line: str) -> None:
        if line.startswith("notifytalkstatuschange "):
            fields = parse_fields(line.partition(" ")[2])
            clid = _int(fields.get("clid"))
            if clid:
                if fields.get("status") == "1":
                    self.talking.add(clid)
                else:
                    self.talking.discard(clid)

    def _execute(self, conn: ClientQueryConnection, kind: str, payload: str) -> None:
        if kind == "join":
            if not self.my_id:
                raise QueryError("Nog geen actieve TeamSpeak-verbinding.")
            cid = _int(payload)
            if cid <= 0:
                return
            conn.command(f"clientmove clid={self.my_id} cid={cid}")
            self.notify("Kanaalwissel uitgevoerd.")
        elif kind == "chat":
            if not self.channel_id:
                raise QueryError("Open eerst een TeamSpeak-kanaal.")
            if not payload.strip():
                return
            conn.command(
                f"sendtextmessage targetmode=2 target={self.channel_id} msg={ts_escape(payload)}"
            )
            self.notify("Bericht naar kanaal verzonden.")
        elif kind == "ptt_on":
            if self.my_id and not self.ptt_down:
                conn.command("clientupdate client_input_muted=0")
                self.ptt_down = True
                self.ptt_ever_used = True
        elif kind == "ptt_off":
            if self.ptt_down:
                conn.command("clientupdate client_input_muted=1")
                self.ptt_down = False

    def _snapshot(self, conn: ClientQueryConnection) -> dict:
        conn.command("use")
        who = conn.command("whoami")
        identity = who[0] if who else {}
        self.my_id = _int(identity.get("clid") or identity.get("client_id"))
        self.channel_id = _int(identity.get("cid") or identity.get("client_channel_id"))
        channels = conn.command("channellist")
        try:
            users = conn.command("clientlist -voice -away")
        except QueryError:
            users = conn.command("clientlist")
        users = [u for u in users if u.get("client_type", "0") == "0"]
        current_ids = {_int(u.get("clid")) for u in users}
        self.talking.intersection_update(current_ids)
        for u in users:
            if u.get("client_flag_talking") == "1":
                self.talking.add(_int(u.get("clid")))
        name = "TeamSpeak 3"
        try:
            server = conn.command("servervariable virtualserver_name")
            if server:
                name = server[0].get("virtualserver_name", name)
        except QueryError:
            pass
        return Snapshot(True, name, self.channel_id, self.my_id,
                        channels, users, sorted(self.talking)).as_dict()

    def run(self) -> None:
        if not self.api_key.strip():
            self.publish(Snapshot(problem="Vul de ClientQuery API-sleutel in bij Instellingen.").as_dict())
            return
        while not self.stop_event.is_set():
            conn = ClientQueryConnection(self._event)
            self.connection = conn
            try:
                conn.connect()
                conn.command(f"auth apikey={ts_escape(self.api_key)}")
                # Notifications are optional; polling continues if unavailable.
                try:
                    conn.command("clientnotifyregister schandlerid=0 event=notifytalkstatuschange")
                except QueryError:
                    pass
                self.notify("Verbonden met TeamSpeak ClientQuery.")
                next_poll = 0.0
                while not self.stop_event.is_set():
                    # Process PTT/key events promptly; never wait for the polling interval.
                    timeout = max(0.0, min(0.1, next_poll - time.monotonic()))
                    try:
                        kind, payload = self.commands.get(timeout=timeout)
                    except queue.Empty:
                        kind, payload = None, ""
                    if kind:
                        try:
                            self._execute(conn, kind, payload)
                        except (QueryError, OSError) as exc:
                            self.notify(f"Actie mislukt: {exc}")
                    if time.monotonic() >= next_poll:
                        try:
                            self.publish(self._snapshot(conn))
                        except QueryError as exc:
                            self.my_id = 0
                            self.channel_id = 0
                            self.talking.clear()
                            self.publish(Snapshot(problem=(
                                "TeamSpeak 3 draait, maar er is nog geen actief server-tabblad: "
                                + str(exc)
                            )).as_dict())
                        next_poll = time.monotonic() + self.interval
            except (QueryError, OSError, TimeoutError) as exc:
                self.publish(Snapshot(problem=(
                    "ClientQuery niet bereikbaar: " + str(exc)
                    + " — start TeamSpeak 3 en controleer de ClientQuery-plugin/API-sleutel."
                )).as_dict())
                self.stop_event.wait(4.0)
            finally:
                if self.ptt_down:
                    # A best-effort restore to muted, including when closing.
                    try:
                        conn.command("clientupdate client_input_muted=1")
                    except (QueryError, OSError):
                        pass
                self.ptt_down = False
                self.my_id = 0
                self.channel_id = 0
                self.talking.clear()
                conn.close()
        self.connection = None

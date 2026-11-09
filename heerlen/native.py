"""Run the standalone Rust tslib audio engine as an app-internal child process.

No installed TeamSpeak client, ClientQuery plugin or API key is required.
The Windows executable is packaged inside the app by GitHub Actions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Callable

from heerlen.connect import make_uri
from heerlen.storage import settings_path


def engine_path() -> Path:
    binary = "heerlen-native.exe" if os.name == "nt" else "heerlen-native"
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [
        root / binary, root / "native" / binary,
        Path(sys.executable).resolve().parent / binary,
    ]
    return next((p for p in candidates if p.is_file()), candidates[0])


class NativeWorker(threading.Thread):
    """A single connection with UI-thread-safe snapshot and status callbacks."""

    def __init__(self, nickname: str, publish: Callable[[dict], None],
                 notify: Callable[[str], None], *, roger_enabled: bool = False):
        super().__init__(daemon=True, name="HeerlenNativeEngine")
        # Nickname validation uses the same rules as our connection link helper.
        make_uri(nickname)
        self.nickname = nickname.strip()
        self.publish = publish
        self.notify = notify
        self.roger_enabled = roger_enabled
        self.commands: queue.Queue[dict] = queue.Queue()
        self.stop_event = threading.Event()
        self.proc: subprocess.Popen | None = None
        self.connected = False
        self.problem = ""

    def send(self, kind: str, payload: str = ""):
        if kind == "join":
            try:
                event = {"action": "join", "cid": int(payload)}
            except (ValueError, TypeError):
                return
        elif kind == "chat":
            event = {"action": "chat", "text": payload}
        elif kind == "roger":
            event = {"action": "roger", "enabled": payload == "1"}
        elif kind in {"ptt_on", "ptt_off", "disconnect"}:
            event = {"action": kind}
        else:
            return
        self.commands.put(event)

    def stop(self):
        self.send("ptt_off")
        self.send("disconnect")
        self.stop_event.set()

    def _read_stdout(self):
        assert self.proc is not None
        stream = self.proc.stdout
        if stream is None:
            return
        try:
            for line in stream:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                kind = event.get("type")
                if kind == "snapshot":
                    self.connected = bool(event.get("connected"))
                    self.publish(event)
                elif kind in ("notice", "chat"):
                    self.notify(str(event.get("message", ""))[:1500])
                elif kind == "error":
                    self.problem = str(event.get("message", "Onbekende fout"))[:600]
                    self.notify("Verbinding mislukt: " + self.problem)
                elif kind == "closed":
                    self.connected = False
        except (OSError, UnicodeError) as exc:
            self.problem = str(exc)

    def run(self):
        exe = engine_path()
        if not exe.is_file():
            self.publish({
                "connected": False, "problem":
                    "De zelfstandige TeamSpeak audio-engine ontbreekt. "
                    "Download het complete officiële Windows ZIP-artifact en pak het uit."
            })
            return
        identity = settings_path().parent / "identity.json"
        identity.parent.mkdir(parents=True, exist_ok=True)
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.proc = subprocess.Popen(
                [str(exe), self.nickname, str(identity)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            self.publish({"connected": False, "problem": str(exc)})
            return
        reader = threading.Thread(target=self._read_stdout, daemon=True)
        reader.start()
        self.send("roger", "1" if self.roger_enabled else "0")
        try:
            while not self.stop_event.is_set() and self.proc.poll() is None:
                try:
                    action = self.commands.get(timeout=0.045)
                except queue.Empty:
                    continue
                try:
                    if self.proc.stdin is not None:
                        self.proc.stdin.write(json.dumps(action, ensure_ascii=False) + "\n")
                        self.proc.stdin.flush()
                except (OSError, BrokenPipeError):
                    break
        finally:
            if self.proc.poll() is None and self.proc.stdin is not None:
                try:
                    # Shut down in the child's protocol thread if possible.
                    self.proc.stdin.write('{"action":"ptt_off"}\n{"action":"disconnect"}\n')
                    self.proc.stdin.flush()
                except OSError:
                    pass
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2.0)
            reader.join(timeout=1.0)
            self.connected = False
            self.publish({
                "connected": False,
                "problem": self.problem or "Verbinding gesloten.",
            })

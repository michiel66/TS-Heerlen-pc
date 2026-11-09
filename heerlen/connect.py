"""Single-server TeamSpeak 3 launcher, without a server password or API token."""
from __future__ import annotations

import os
from urllib.parse import quote

SERVER = "heerlen.mijnts3.nl"


def make_uri(nickname: str) -> str:
    """Build the officially supported ts3server:// link from a user nickname."""
    nickname = nickname.strip()
    if not 3 <= len(nickname) <= 30:
        raise ValueError("Vul een gebruikersnaam van 3 tot en met 30 tekens in.")
    if any(ord(char) < 32 or ord(char) == 127 for char in nickname):
        raise ValueError("De gebruikersnaam bevat ongeldige tekens.")
    return f"ts3server://{SERVER}?nickname={quote(nickname, safe='')}"


def open_teamspeak(nickname: str) -> None:
    """Windows launches TeamSpeak's registered URL handler; nothing goes via HTTP."""
    if os.name != "nt":
        raise OSError("Start TeamSpeak op een Windows 10/11-computer.")
    os.startfile(make_uri(nickname))

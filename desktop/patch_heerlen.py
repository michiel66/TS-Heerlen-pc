"""Make a Heerlen build on top of the pinned, green PTTConnect-PC patch.
Never change PTTConnect itself or its working voice module.
The browser handles getUserMedia(), device enumeration, PCM and PTT. The Rust
WebSpeak3 connector handles TeamSpeak Opus send/receive.
"""
from pathlib import Path
import re

ROOT = Path("ptt-template/upstream/web")
APP = ROOT / "src" / "App.tsx"
CSS = ROOT / "src" / "App.css"
app = APP.read_text(encoding="utf-8")
css = CSS.read_text(encoding="utf-8")


def exactly_once(before: str, after: str, context: str):
    global app
    count = app.count(before)
    if count != 1:
        raise RuntimeError(f"Heerlen patch mislukt: {context}: {count} matches")
    app = app.replace(before, after, 1)


# Preserve the working PTTConnect core; only adjust branding and default view.
app = app.replace("PTT Connect", "TeamSpeak Heerlen PC")
app = app.replace("PTT CONNECT", "TEAMSPEAK HEERLEN")

layout = '''  const [
    pttLayoutMode,
    setPttLayoutMode
  ] = useState<
    "normal" |
    "cb"
  >(
    "normal"
  );'''
exactly_once(layout, layout.replace('"normal"\n  );', '"cb"\n  );'), "start in Heerlen layout")

# PTTConnect already provides the microphone picker, WebAudio microphone tests,
# configurable hotkey, echo cancellation, mic level and actual TeamSpeak voice.
# Our extra UI exposes a one-field join to the hard-locked Heerlen address.
anchor = '<section className="ptt-android-view">'
connect = r'''<section className={"ptt-android-view heerlen-bg-" + heerlenBackground}>
          {!connected && (
            <div className="heerlen-connect-form">
              <span><strong>TEAMSPEAK HEERLEN</strong> • heerlen.mijnts3.nl</span>
              <input
                aria-label="Gebruikersnaam"
                type="text"
                maxLength={30}
                placeholder="Vul jouw gebruikersnaam in"
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && nickname.trim().length >= 3 && !connecting) {
                    handleConnect({ host: "heerlen.mijnts3.nl", nickname: nickname.trim() });
                  }
                }}
              />
              <button
                type="button"
                disabled={connecting || nickname.trim().length < 3}
                onClick={() => handleConnect({ host: "heerlen.mijnts3.nl", nickname: nickname.trim() })}
              >{connecting ? "Verbinden…" : "Verbinden met Heerlen"}</button>
              {connectError && <span className="heerlen-connect-error">{String(connectError)}</span>}
            </div>
          )}'''
exactly_once(anchor, connect, "eenvoudig inloggen met alleen naam")

# The color choices are local to this Windows app and never affect the mic path.
state_anchor = '''  const [
    pttAndroidSettingsOpen,
    setPttAndroidSettingsOpen
  ] = useState(
    false
  );'''
state_extra = state_anchor + r'''

  const [heerlenRogerEnabled, setHeerlenRogerEnabled] = useState(
    () => localStorage.getItem("tsheerlen:roger") !== "off"
  );
  const [heerlenBackground, setHeerlenBackground] = useState(
    () => localStorage.getItem("tsheerlen:background") || "midnight"
  );
  useEffect(() => {
    localStorage.setItem("tsheerlen:roger", heerlenRogerEnabled ? "on" : "off");
  }, [heerlenRogerEnabled]);
  useEffect(() => {
    localStorage.setItem("tsheerlen:background", heerlenBackground);
  }, [heerlenBackground]);'''
exactly_once(state_anchor, state_extra, "persoonlijke instellingen")

# Important: roger frames take the same tested sendAudio->Opus route as mic frames.
# Nothing plays on the PC itself. They are optional (user toggle).
roger = r'''  const sendHeerlenRoger = async () => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || inputMutedRef.current) return;
    const frequencies = [740, 980, 1240];
    const rate = 48000;
    const frameSize = 960;
    for (let frame = 0; frame < 18; frame++) {
      if (socket.readyState !== WebSocket.OPEN || inputMutedRef.current) break;
      const idx = Math.floor(frame / 6);
      const pcm = new Int16Array(frameSize);
      for (let i = 0; i < frameSize; i++) {
        const t = (frame % 6) * frameSize + i;
        const env = Math.min(1, t / 480, (6 * frameSize - 1 - t) / 480);
        pcm[i] = Math.round(
          Math.sin(2 * Math.PI * frequencies[idx] * t / rate) * env * 9500
        );
      }
      const bytes = new Uint8Array(pcm.buffer);
      let binary = "";
      for (const byte of bytes) binary += String.fromCharCode(byte);
      socket.send(JSON.stringify({ type: "sendAudio", pcm: btoa(binary) }));
      await new Promise<void>((resolve) => window.setTimeout(resolve, 20));
    }
  };

'''
start_anchor = '''  const handleAndroidPttStart =
    async () => {'''
exactly_once(start_anchor, roger + start_anchor, "rogerpiep generator")
stop_anchor = '''      pttAndroidPressedRef.current =
        false;

      micCaptureRef.current
        ?.setPushToTalk(
          false
        );'''
stop_replacement = '''      const wasPressed = pttAndroidPressedRef.current;
      pttAndroidPressedRef.current =
        false;

      micCaptureRef.current
        ?.setPushToTalk(
          false
        );
      if (wasPressed && heerlenRogerEnabled && connected) {
        void sendHeerlenRoger();
      }'''
exactly_once(stop_anchor, stop_replacement, "PTT loslaten en optionele remote roger")

# Visible preference selectors in the Heerlen titlebar, while the existing
# PTTConnect settings menu still provides mic/output devices and PTT hotkeys.
actions = '<div className="ptt-android-top-actions">'
actions_repl = r'''<div className="ptt-android-top-actions">
              <label className="heerlen-roger-choice" title="Rogerpiep wordt in het TeamSpeak-kanaal verzonden">
                <input type="checkbox" checked={heerlenRogerEnabled}
                  onChange={(e) => setHeerlenRogerEnabled(e.target.checked)} />
                3-tonige rogerpiep
              </label>
              <select aria-label="Achtergrond" className="heerlen-background-choice"
                value={heerlenBackground}
                onChange={(e) => setHeerlenBackground(e.target.value)}>
                <option value="midnight">Nachtblauw</option>
                <option value="green">Radio groen</option>
                <option value="purple">Neon paars</option>
                <option value="black">Zwart</option>
              </select>'''
exactly_once(actions, actions_repl, "Heerlen roger en achtergrond schakelaars")
APP.write_text(app, encoding="utf-8")

css += r'''

/* Heerlen settings: this is visual-only; do not change PTT/audio internals. */
.ptt-android-view.heerlen-bg-midnight { background: linear-gradient(145deg, #041124, #071c35) !important; }
.ptt-android-view.heerlen-bg-green { background: linear-gradient(145deg, #031b14, #082e25) !important; }
.ptt-android-view.heerlen-bg-purple { background: linear-gradient(145deg, #110d27, #201139) !important; }
.ptt-android-view.heerlen-bg-black { background: #05080d !important; }
.heerlen-connect-form {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 12px 18px; background: #081d32; color: #e0f7ff;
  border-bottom: 1px solid #195a84; z-index: 2;
}
.heerlen-connect-form strong { color: #21d9ff; }
.heerlen-connect-form input {
  min-width: 180px; flex: 1; max-width: 340px;
  color: white; background: #09263c; padding: 10px; border: 1px solid #3192bc;
  border-radius: 9px; font: inherit;
}
.heerlen-connect-form button {
  padding: 10px 16px; border-radius: 9px; border: 1px solid #20d7ff;
  background: #0868a0; color: white; cursor: pointer; font-weight: bold;
}
.heerlen-connect-form button:disabled { cursor: default; opacity: .5; }
.heerlen-connect-error { color: #ffba99; }
.heerlen-roger-choice {
  display: flex; gap: 5px; align-items: center; white-space: nowrap;
  font-size: 12px; cursor: pointer; color: #d9f6ff;
}
.heerlen-background-choice {
  color: #def6ff; background: #0b2740; border: 1px solid #275b80;
  border-radius: 8px; padding: 6px; max-width: 138px;
}
'''
CSS.write_text(css, encoding="utf-8")

# Avoid silent bypass if PTTConnect changed its API.
assert "navigator.mediaDevices.getUserMedia" in (ROOT / "src" / "voice.ts").read_text(encoding="utf-8")
assert 'setPushToTalk' in app
assert 'handleConnect({ host: "heerlen.mijnts3.nl"' in app
assert 'sendHeerlenRoger' in app
print("Heerlen-branded PTTConnect microphone/PTT app prepared; default server heerlen.mijnts3.nl")

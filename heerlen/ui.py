"""Native Qt 6 midnight-neon user interface for TeamSpeak 3 ClientQuery."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from heerlen.query import ClientQueryWorker, sort_channel_tree
from heerlen.storage import get_api_key, load_settings, save_settings, set_api_key

CYAN = "#16d6ff"
GREEN = "#37ef7f"
TEXT = "#f2f9ff"

STYLES = """
* { font-family: "Segoe UI"; font-size: 13px; color: #f2f9ff; }
QMainWindow, QDialog { background: #030c1b; }
QWidget#AppRoot { background: #030c1b; }
QFrame#Panel { background: #0a2038; border: 1px solid #21547b;
                border-radius: 15px; }
QFrame#Top { background: #06182d; border-bottom: 1px solid #19527b; }
QLabel#Title { font-size: 23px; font-weight: 800; color: #f2f9ff; }
QLabel#SubTitle { font-size: 13px; color: #16d6ff; }
QLabel#Counter { font-size: 27px; color: #37ef7f; font-weight: 800; }
QLabel#Hint { font-size: 12px; color: #b5cde2; }
QLabel#Section { font-size: 17px; font-weight: 700; color: #16d6ff; }
QPushButton { background: #0a2e51; border: 1px solid #2975aa;
              border-radius: 10px; padding: 10px 15px; color: white; font-weight: 600; }
QPushButton:hover { background: #114675; border-color: #16d6ff; }
QPushButton:pressed { background: #0878bb; }
QPushButton:checked { background: #07549d; border: 2px solid #16d6ff; }
QPushButton:disabled { color: #65798d; border-color: #25384e; background: #101b2c; }
QPushButton#PTT { border: 4px solid #37ef7f; background: #0c4c38;
                  color: #dfffe9; border-radius: 35px; padding: 8px 45px;
                  font-size: 21px; font-weight: 900; }
QPushButton#PTT:pressed { background: #1ab45d; border-color: #c8ffdf; color: #031c11; }
QPushButton#PTT:disabled { background: #162d2c; color: #607b71;
                           border-color: #2f6250; }
QTreeWidget, QListWidget, QTextEdit { background: #071729; alternate-background-color: #0a2038;
                          border: 1px solid #20496f; border-radius: 9px;
                          padding: 7px; outline: none; }
QTreeWidget::item, QListWidget::item { padding: 6px; border-radius: 6px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #07549d; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #123656; }
QLineEdit { background: #081a30; color: white; border: 1px solid #2b668e;
            border-radius: 9px; padding: 10px; }
QLineEdit:focus { border: 1px solid #16d6ff; }
QScrollBar:vertical { width: 10px; background: #071729; }
QScrollBar::handle:vertical { background: #236089; border-radius: 4px; min-height: 18px; }
QSplitter::handle { background: #123656; width: 8px; }
QLabel#Status { background: #0a2038; border: 1px solid #245782;
                border-radius: 9px; padding: 10px; }
"""


def box(parent: QWidget | None = None, *, vertical: bool = True,
        spacing: int = 10, margins: tuple[int, int, int, int] = (0, 0, 0, 0)):
    layout = QVBoxLayout(parent) if vertical else QHBoxLayout(parent)
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    return layout


def panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Panel")
    return frame, box(frame, margins=(16, 16, 16, 16))


class Bridge(QObject):
    snapshot = Signal(dict)
    notice = Signal(str)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instellingen — Teamspeak Heerlen PC")
        self.setMinimumWidth(510)
        self.setStyleSheet(STYLES)
        layout = box(self, spacing=16, margins=(22, 22, 22, 22))
        title = QLabel("TeamSpeak 3 • ClientQuery")
        title.setObjectName("Section")
        layout.addWidget(title)
        help_text = QLabel(
            "Start TeamSpeak 3 en zet de ClientQuery-plugin aan.\n"
            "Open in TS3: Extra/Tools → Opties/Options → Addons →\n"
            "ClientQuery → Instellingen/Settings. Kopieer daar de API-sleutel.\n\n"
            "De PC-app werkt via je bestaande TeamSpeak 3-client."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addWidget(QLabel("ClientQuery API-sleutel"))
        self.key_field = QLineEdit(get_api_key())
        self.key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_field.setPlaceholderText("Plak je ClientQuery API-sleutel")
        layout.addWidget(self.key_field)
        self.show_key = QCheckBox("Toon sleutel")
        self.show_key.toggled.connect(
            lambda visible: self.key_field.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(self.show_key)
        info = QLabel("De sleutel wordt opgeslagen in Windows Credential Manager, niet in een tekstbestand.")
        info.setObjectName("Hint")
        info.setWordWrap(True)
        layout.addWidget(info)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_key(self) -> bool:
        return set_api_key(self.key_field.text())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teamspeak Heerlen PC")
        self.resize(1120, 780)
        self.setMinimumSize(830, 620)
        self.setStyleSheet(STYLES)
        self.setWindowIcon(QIcon(str(self._asset("logo.svg"))))
        self.cfg = load_settings()
        self.current_view = self.cfg.get("view", "kanalen")
        self.latest: dict = {}
        self.talking: set[int] = set()
        self.worker: ClientQueryWorker | None = None
        self.bridge = Bridge()
        self.bridge.snapshot.connect(self.show_snapshot)
        self.bridge.notice.connect(self.show_notice)
        self._tree_signature = None
        self._ptt_pressed = False
        self._create_ui()
        self.switch_view(self.current_view)
        self.start_worker()

    @staticmethod
    def _asset(filename: str) -> Path:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        return root / "assets" / filename

    def _create_ui(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = box(root, spacing=0)

        top = QFrame()
        top.setObjectName("Top")
        top_layout = box(top, margins=(20, 16, 20, 15), spacing=12)
        branding = box(vertical=False, spacing=10)
        title_col = box(spacing=3)
        title = QLabel("TEAMSPEAK  HEERLEN")
        title.setObjectName("Title")
        title_col.addWidget(title)
        subtitle = QLabel("PC EDITION  •  WINDOWS  •  LIVE VERBINDING")
        subtitle.setObjectName("SubTitle")
        title_col.addWidget(subtitle)
        branding.addLayout(title_col, 1)
        self.setup_btn = QPushButton("⚙  Instellingen")
        self.setup_btn.clicked.connect(self.open_settings)
        branding.addWidget(self.setup_btn)
        top_layout.addLayout(branding)

        head_controls = box(vertical=False)
        self.status_label = QLabel("●  Wachten op TeamSpeak 3...")
        self.status_label.setObjectName("Status")
        head_controls.addWidget(self.status_label, 1)
        self.channels_btn = QPushButton("◫  Kanalen")
        self.monitor_btn = QPushButton("◉  Live monitor")
        for button in (self.channels_btn, self.monitor_btn):
            button.setCheckable(True)
            head_controls.addWidget(button)
        self.channels_btn.clicked.connect(lambda: self.switch_view("kanalen"))
        self.monitor_btn.clicked.connect(lambda: self.switch_view("monitor"))
        top_layout.addLayout(head_controls)
        layout.addWidget(top)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        channel_page = QWidget()
        channel_layout = box(channel_page, margins=(18, 17, 18, 8))
        splitter = QSplitter(Qt.Orientation.Horizontal)
        channels_panel, channel_panel_layout = panel()
        label = QLabel("SERVERKANALEN")
        label.setObjectName("Section")
        channel_panel_layout.addWidget(label)
        hint = QLabel("Dubbelklik op een kanaal om over te schakelen. Spacerregels zijn aanklikbaar.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        channel_panel_layout.addWidget(hint)
        self.channel_tree = QTreeWidget()
        self.channel_tree.setHeaderHidden(True)
        self.channel_tree.setAlternatingRowColors(True)
        self.channel_tree.itemDoubleClicked.connect(self.on_channel_doubleclick)
        channel_panel_layout.addWidget(self.channel_tree, 1)
        splitter.addWidget(channels_panel)

        right_panel, right_layout = panel()
        right_title = QLabel("ONLINE GEBRUIKERS")
        right_title.setObjectName("Section")
        right_layout.addWidget(right_title)
        self.quick_count = QLabel("0 online")
        self.quick_count.setObjectName("Counter")
        right_layout.addWidget(self.quick_count)
        self.quick_users = QListWidget()
        right_layout.addWidget(self.quick_users, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([630, 360])
        channel_layout.addWidget(splitter, 1)
        self.pages.addWidget(channel_page)

        monitor_page = QWidget()
        monitor_layout = box(monitor_page, margins=(18, 17, 18, 8), spacing=12)
        head, head_layout = panel()
        monitor_title = QLabel("LIVE GEBRUIKERSMONITOR")
        monitor_title.setObjectName("Section")
        head_layout.addWidget(monitor_title)
        stats = box(vertical=False, spacing=30)
        self.online_count = QLabel("0 ONLINE")
        self.online_count.setObjectName("Counter")
        self.speaking_count = QLabel("0 SPREKERS")
        self.speaking_count.setObjectName("Counter")
        stats.addWidget(self.online_count)
        stats.addWidget(self.speaking_count)
        stats.addStretch(1)
        head_layout.addLayout(stats)
        monitor_layout.addWidget(head)
        filters = box(vertical=False)
        self.filters: dict[str, QPushButton] = {}
        for key, text in [("all", "Iedereen"), ("talking", "Sprekers"), ("mine", "Mijn kanaal")]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.clicked.connect(lambda _, name=key: self.set_filter(name))
            self.filters[key] = button
            filters.addWidget(button)
        filters.addStretch(1)
        monitor_layout.addLayout(filters)
        self.monitor_list = QListWidget()
        self.monitor_list.setAlternatingRowColors(True)
        monitor_layout.addWidget(self.monitor_list, 1)
        self.pages.addWidget(monitor_page)

        lower = QFrame()
        lower.setObjectName("Top")
        lower_layout = box(lower, spacing=9, margins=(18, 10, 18, 16))
        self.rx_tx = QLabel("RX  ○  RUST       TX  ○  RUST")
        self.rx_tx.setObjectName("SubTitle")
        lower_layout.addWidget(self.rx_tx)
        row = box(vertical=False, spacing=16)
        chat_col = box(spacing=6)
        chat_title = QLabel("KANAALCHAT")
        chat_title.setObjectName("Section")
        chat_col.addWidget(chat_title)
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setMaximumHeight(85)
        self.chat_log.setPlaceholderText("Kanaalberichten en meldingen verschijnen hier.")
        chat_col.addWidget(self.chat_log)
        chat_row = box(vertical=False, spacing=8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Typ een bericht voor je huidige kanaal...")
        self.chat_input.returnPressed.connect(self.send_chat)
        self.send_chat_btn = QPushButton("Verstuur")
        self.send_chat_btn.clicked.connect(self.send_chat)
        chat_row.addWidget(self.chat_input, 1)
        chat_row.addWidget(self.send_chat_btn)
        chat_col.addLayout(chat_row)
        row.addLayout(chat_col, 1)
        ptt_col = box(spacing=6)
        hint = QLabel("HOUD INGEDRUKT • OF F9")
        hint.setObjectName("Hint")
        ptt_col.addWidget(hint, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ptt_button = QPushButton("PTT")
        self.ptt_button.setObjectName("PTT")
        self.ptt_button.setMinimumSize(200, 92)
        self.ptt_button.pressed.connect(self.press_ptt)
        self.ptt_button.released.connect(self.release_ptt)
        ptt_col.addWidget(self.ptt_button)
        row.addLayout(ptt_col)
        lower_layout.addLayout(row)
        layout.addWidget(lower)
        self.statusBar().showMessage("TeamSpeak 3 met ClientQuery-plugin vereist.")
        self._set_connected(False)

    def switch_view(self, view: str):
        self.current_view = view if view in ("kanalen", "monitor") else "kanalen"
        self.pages.setCurrentIndex(0 if self.current_view == "kanalen" else 1)
        self.channels_btn.setChecked(self.current_view == "kanalen")
        self.monitor_btn.setChecked(self.current_view == "monitor")
        self.cfg["view"] = self.current_view
        save_settings(self.cfg)

    def set_filter(self, name: str):
        self.filter_name = name
        for key, button in self.filters.items():
            button.setChecked(key == name)
        self.refresh_monitor()

    def start_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=6.0)
        self.worker = ClientQueryWorker(
            get_api_key(), self.bridge.snapshot.emit, self.bridge.notice.emit
        )
        self.worker.start()

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if not dialog.save_key():
                QMessageBox.warning(
                    self, "Opslaan mislukt",
                    "De API-sleutel kon niet in Windows Credential Manager worden opgeslagen."
                )
                return
            self.start_worker()

    def send_command(self, kind: str, payload: str = ""):
        if self.worker is not None:
            self.worker.send(kind, payload)

    def on_channel_doubleclick(self, item: QTreeWidgetItem, column: int):
        if not self.latest.get("connected"):
            return
        cid = item.data(0, Qt.ItemDataRole.UserRole)
        if cid is not None:
            self.send_command("join", str(cid))

    def press_ptt(self):
        if not self.latest.get("connected") or self._ptt_pressed:
            return
        self._ptt_pressed = True
        self.send_command("ptt_on")
        self.ptt_button.setText("PTT ●")
        self.statusBar().showMessage("PTT ingedrukt: TeamSpeak-microfoon tijdelijk open.")

    def release_ptt(self):
        if not self._ptt_pressed:
            return
        self._ptt_pressed = False
        self.send_command("ptt_off")
        self.ptt_button.setText("PTT")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_F9 and not event.isAutoRepeat():
            self.press_ptt()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_F9 and not event.isAutoRepeat():
            self.release_ptt()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def send_chat(self):
        value = self.chat_input.text().strip()
        if value and self.latest.get("connected"):
            self.send_command("chat", value)
            self.chat_log.append(f"Jij: {value}")
            self.chat_input.clear()

    def show_notice(self, message: str):
        self.statusBar().showMessage(message, 8000)
        self.chat_log.append(message)

    def _set_connected(self, connected: bool):
        self.ptt_button.setEnabled(connected)
        self.send_chat_btn.setEnabled(connected)
        self.chat_input.setEnabled(connected)
        if not connected and self._ptt_pressed:
            self.release_ptt()

    def show_snapshot(self, snapshot: dict):
        self.latest = snapshot
        connected = bool(snapshot.get("connected"))
        self._set_connected(connected)
        name = snapshot.get("server_name") or "TeamSpeak 3"
        self.status_label.setText(
            f"●  Verbonden: {name}" if connected
            else "●  Niet verbonden — " + snapshot.get("problem", "Controleer ClientQuery.")
        )
        self.status_label.setStyleSheet(
            f"color:{GREEN if connected else '#ffb74d'};"
        )
        users = snapshot.get("users", [])
        speaking = set(snapshot.get("talking", []))
        my_id = snapshot.get("my_id", 0)
        self.talking = speaking
        self.online_count.setText(f"{len(users)} ONLINE")
        self.speaking_count.setText(f"{len(speaking)} SPREKERS")
        self.quick_count.setText(f"{len(users)} online")
        is_tx = my_id in speaking
        my_channel_id = int(snapshot.get("channel_id", 0))
        audible_users = {
            int(user.get("clid", 0))
            for user in users
            if int(user.get("cid", 0)) == my_channel_id
        }
        is_rx = any(uid != my_id and uid in audible_users for uid in speaking)
        self.rx_tx.setText(
            f"RX  {'● ACTIEF' if is_rx else '○ RUST'}"
            f"       TX  {'● ACTIEF' if is_tx else '○ RUST'}"
            "       • LIVE TEAMSPEAK"
        )
        new_sig = (
            repr(snapshot.get("channels")), repr(users), tuple(sorted(speaking)), my_id
        )
        if new_sig != self._tree_signature:
            self._tree_signature = new_sig
            self.refresh_channels()
            self.refresh_monitor()

    def refresh_channels(self):
        channels = self.latest.get("channels", [])
        users = self.latest.get("users", [])
        users_by_channel = defaultdict(list)
        for user in users:
            try:
                cid = int(user.get("cid", 0))
            except (ValueError, TypeError):
                continue
            users_by_channel[cid].append(user)
        self.channel_tree.clear()
        items: dict[int, QTreeWidgetItem] = {}
        for channel, depth in sort_channel_tree(channels):
            cid = int(channel.get("cid", 0))
            pid = int(channel.get("pid", 0))
            parent = items.get(pid)
            name = channel.get("channel_name", f"Kanaal {cid}")
            entry = QTreeWidgetItem([f"▣  {name}"])
            entry.setData(0, Qt.ItemDataRole.UserRole, cid)
            entry.setForeground(0, QColor(CYAN))
            if parent is None:
                self.channel_tree.addTopLevelItem(entry)
            else:
                parent.addChild(entry)
            items[cid] = entry
            for user in sorted(users_by_channel.get(cid, []),
                               key=lambda u: u.get("client_nickname", "").lower()):
                username = user.get("client_nickname", "Onbekend")
                uid = int(user.get("clid", 0))
                active = uid in self.talking
                child = QTreeWidgetItem([f"{'●' if active else '○'}  {username}"])
                child.setForeground(0, QColor(GREEN if active else TEXT))
                entry.addChild(child)
            entry.setExpanded(True)
        self.quick_users.clear()
        for user in sorted(users, key=lambda u: u.get("client_nickname", "").lower()):
            uid = int(user.get("clid", 0))
            self.quick_users.addItem(
                f"{'●' if uid in self.talking else '○'}  "
                f"{user.get('client_nickname', 'Onbekend')}"
            )

    def refresh_monitor(self):
        users = self.latest.get("users", [])
        channel_names = {
            int(c.get("cid", 0)): c.get("channel_name", "")
            for c in self.latest.get("channels", [])
        }
        my_channel = int(self.latest.get("channel_id", 0))
        speaking = self.talking
        filtered = sorted(users, key=lambda u: (
            0 if int(u.get("clid", 0)) in speaking else 1,
            u.get("client_nickname", "").lower()
        ))
        self.monitor_list.clear()
        for u in filtered:
            clid = int(u.get("clid", 0))
            cid = int(u.get("cid", 0))
            active = clid in speaking
            if self.filter_name == "talking" and not active:
                continue
            if self.filter_name == "mine" and cid != my_channel:
                continue
            name = u.get("client_nickname", "Onbekend")
            label = "SPREEKT" if active else "ONLINE"
            if u.get("client_input_muted") == "1":
                label = "MIC UIT"
            channel = channel_names.get(cid, "Onbekend kanaal")
            item = QListWidgetItem(
                f"{'●' if active else '○'}   {name}     • {label}\n      {channel}"
            )
            item.setForeground(QColor(GREEN if active else TEXT))
            self.monitor_list.addItem(item)

    def closeEvent(self, event):
        self.release_ptt()
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=5.0)
        super().closeEvent(event)

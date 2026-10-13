"""
Live Stream TL: live speech transcription and translation.

Speech is recognised offline with Vosk, and each finished sentence is sent to
an OpenAI chat model for translation.

Setup
    pip install -r requirements.txt
    Unzip Vosk models (https://alphacephei.com/vosk/models) into ./models/
    Put OPENAI_API_KEY=... in a .env file next to this script
    python wattys_translations.py
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI
from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)
from vosk import KaldiRecognizer, Model, SetLogLevel

APP_NAME = "Live Stream TL"
APP_VERSION = "0.2"
APP_DIR = Path(__file__).resolve().parent
MODEL_DIRS = (APP_DIR / "models", APP_DIR)  # searched for vosk-model-* folders
LOG_DIR = APP_DIR / "logs"

load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

BLOCK_SECONDS = 0.25        # audio chunk size; smaller means snappier live text
CONTEXT_TURNS = 4           # earlier lines sent along so the translator has context
BACKLOG_WARN_SECONDS = 5    # warn when recognition falls this far behind real time

SYSTEM_PROMPT = (
    "You are a professional interpreter translating live speech into {target}. "
    "Each user message is the next line of an automatic speech-recognition "
    "transcript (recogniser language code: {source}). Expect missing punctuation, "
    "odd spacing and the occasional misheard word; infer the most likely intended "
    "meaning from context. Preserve tone, cultural references and wordplay where "
    "you can. Reply with the {target} translation only: no notes, quotes or "
    "explanations."
)


# ---------------------------------------------------------------------- models

MODEL_NAME_RE = re.compile(r"^vosk-model-(?P<small>small-)?(?P<lang>.+?)-\d")


@dataclass(frozen=True)
class VoskModelInfo:
    path: Path
    lang: str
    small: bool


def model_info(path: Path) -> VoskModelInfo:
    path = path.resolve()
    match = MODEL_NAME_RE.match(path.name)
    if match:
        return VoskModelInfo(path, match["lang"], bool(match["small"]))
    return VoskModelInfo(path, path.name, False)


def find_models() -> list[VoskModelInfo]:
    found: dict[Path, VoskModelInfo] = {}
    for folder in MODEL_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            match = MODEL_NAME_RE.match(path.name)
            if path.is_dir() and match and match["lang"] != "spk":  # skip speaker-ID models
                info = model_info(path)
                found.setdefault(info.path, info)
    return sorted(found.values(), key=lambda m: (m.lang, m.small, m.path.name))


# --------------------------------------------------------------------- session

class TranslationSession(QThread):
    """Captures audio, runs Vosk on it, and hands finished lines to a translator thread."""

    status = pyqtSignal(str)                  # short status-bar messages
    partial = pyqtSignal(str)                 # words heard so far in the current sentence
    utterance = pyqtSignal(int, str)          # (line id, recognised text)
    translation = pyqtSignal(int, str, bool)  # (line id, translated text, succeeded)
    error = pyqtSignal(str)

    def __init__(self, model: VoskModelInfo, device: int | None, target_lang: str,
                 client: OpenAI | None, log_path: Path | None):
        super().__init__()
        self.model_info = model
        self.device = device
        self.target_lang = target_lang
        self.client = client
        self.log_path = log_path
        self._stop = threading.Event()
        self._discard_pending = False
        self._audio: queue.Queue[bytes] = queue.Queue()
        self._ids = itertools.count(1)
        self._history: list[tuple[str, str]] = []
        self._translator: ThreadPoolExecutor | None = None
        self._log = None
        self._log_lock = threading.Lock()

    def stop(self, discard_pending: bool = False):
        """Ask the session to finish. Queued translations still complete unless discarded."""
        self._discard_pending = discard_pending
        self._stop.set()

    # Runs on PortAudio's thread, so it only copies the audio and returns at once.
    def _on_audio(self, indata, frames, time_info, status):
        if status:
            self.status.emit(f"Audio warning: {status}")
        self._audio.put(bytes(indata))

    def run(self):
        SetLogLevel(-1)
        try:
            self.status.emit(f"Loading {self.model_info.path.name}…")
            model = Model(str(self.model_info.path))
            if self._stop.is_set():
                return

            # Record at the device's own rate; Vosk resamples internally.
            device = sd.query_devices(self.device, "input")
            rate = int(device["default_samplerate"])
            recogniser = KaldiRecognizer(model, rate)

            if self.client:
                # One worker keeps translations in order without blocking recognition.
                self._translator = ThreadPoolExecutor(max_workers=1)
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log = self.log_path.open("a", encoding="utf-8")

            backlog_limit = int(BACKLOG_WARN_SECONDS / BLOCK_SECONDS)
            warned = False
            with sd.RawInputStream(samplerate=rate, blocksize=int(rate * BLOCK_SECONDS),
                                   device=self.device, dtype="int16", channels=1,
                                   callback=self._on_audio):
                self.status.emit(f"Listening on {device['name']}")
                while not self._stop.is_set():
                    try:
                        data = self._audio.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if recogniser.AcceptWaveform(data):
                        self._finish_line(recogniser.Result())
                    else:
                        self.partial.emit(json.loads(recogniser.PartialResult()).get("partial", ""))
                    if not warned and self._audio.qsize() > backlog_limit:
                        warned = True
                        self.status.emit("Recognition is falling behind real time. "
                                         "A small model may keep up better.")
            self._finish_line(recogniser.FinalResult())  # whatever was mid-sentence at Stop
        except Exception as exc:  # anything that goes wrong here should reach the user
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if self._translator:
                self._translator.shutdown(wait=not self._discard_pending,
                                          cancel_futures=self._discard_pending)
            with self._log_lock:
                if self._log:
                    self._log.close()
            self.partial.emit("")

    def _finish_line(self, result_json: str):
        self.partial.emit("")
        text = json.loads(result_json).get("text", "").strip()
        if not text:
            return
        uid = next(self._ids)
        self.utterance.emit(uid, text)
        if self._translator and not self._discard_pending:
            self._translator.submit(self._translate, uid, text)
        elif not self.client:
            self._write_log(text)

    # Runs on the translator thread, one line at a time.
    def _translate(self, uid: int, text: str):
        prompt = SYSTEM_PROMPT.format(target=self.target_lang, source=self.model_info.lang)
        messages = [{"role": "system", "content": prompt}]
        for source, translated in self._history:
            messages += [{"role": "user", "content": source},
                         {"role": "assistant", "content": translated}]
        messages.append({"role": "user", "content": text})
        try:
            response = self.client.chat.completions.create(model=OPENAI_MODEL, messages=messages)
            translated = (response.choices[0].message.content or "").strip()
            self._history.append((text, translated))
            del self._history[:-CONTEXT_TURNS]
            self.translation.emit(uid, translated, True)
        except Exception as exc:
            translated = f"[translation failed: {exc}]"
            self.translation.emit(uid, f"Translation failed ({type(exc).__name__}: {exc})", False)
        self._write_log(text, translated)

    def _write_log(self, text: str, translated: str | None = None):
        with self._log_lock:
            if not self._log or self._log.closed:
                return
            stamp = datetime.now().strftime("%H:%M:%S")
            self._log.write(f"[{stamp}] {self.model_info.lang.upper()}: {text}\n")
            if translated is not None:
                self._log.write(f"[{stamp}] {self.target_lang}: {translated}\n")
            self._log.flush()


# ------------------------------------------------------------------ transcript

class TranscriptView(QTextEdit):
    """Read-only transcript where each translation lands directly under its source line."""

    def __init__(self, source_label: str, target_label: str, translating: bool):
        super().__init__()
        self.setReadOnly(True)
        self.source_label = source_label
        self.target_label = target_label
        self.translating = translating
        self._pending: dict[int, int] = {}  # line id -> block number of its placeholder

        muted = self.palette().color(QPalette.ColorRole.PlaceholderText)
        self._fmt_source = QTextCharFormat()
        self._fmt_source.setForeground(muted)
        self._fmt_target = QTextCharFormat()
        self._fmt_info = QTextCharFormat()
        self._fmt_info.setForeground(muted)
        self._fmt_info.setFontItalic(True)
        self._fmt_error = QTextCharFormat()
        self._fmt_error.setForeground(QColor("#d9534f"))

    def add_info(self, text: str):
        self._append(text, self._fmt_info)

    def add_error(self, text: str):
        self._append(text, self._fmt_error, top_margin=8)

    def add_utterance(self, uid: int, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{stamp}] {self.source_label}: {text}", self._fmt_source, top_margin=8)
        if self.translating:
            self._pending[uid] = self._append(f"{self.target_label}: …", self._fmt_info)

    def set_translation(self, uid: int, text: str, ok: bool):
        block_number = self._pending.pop(uid, None)
        if block_number is None:
            return
        stick = self._at_bottom()
        cursor = QTextCursor(self.document().findBlockByNumber(block_number))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(self._one_block(f"{self.target_label}: {text}"),
                          self._fmt_target if ok else self._fmt_error)
        if stick:
            self._scroll_to_bottom()

    def _append(self, text: str, fmt: QTextCharFormat, top_margin: int = 0) -> int:
        stick = self._at_bottom()
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        block_format = QTextBlockFormat()
        block_format.setTopMargin(top_margin)
        if self.document().isEmpty():
            cursor.setBlockFormat(block_format)
        else:
            cursor.insertBlock(block_format)
        cursor.insertText(self._one_block(text), fmt)
        if stick:
            self._scroll_to_bottom()
        return cursor.blockNumber()

    @staticmethod
    def _one_block(text: str) -> str:
        # Line separators keep multi-line text in one block, so stored block numbers stay valid.
        return text.replace("\r\n", "\n").replace("\n", "\u2028")

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())


# ---------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self, client: OpenAI | None):
        super().__init__()
        self.client = client
        self.session: TranslationSession | None = None
        self.session_view: TranscriptView | None = None
        self._custom_models: dict[Path, VoskModelInfo] = {}
        self.settings = QSettings("Watty", "WattysTranslations")

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(780, 580)

        self.model_combo = QComboBox()
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.browse_model)
        refresh_button = QPushButton("Refresh")
        refresh_button.setToolTip("Rescan the models folder and audio devices")
        refresh_button.clicked.connect(lambda: self.refresh_lists(rescan_audio=True))
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(browse_button)
        model_row.addWidget(refresh_button)

        self.device_combo = QComboBox()

        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("English")
        self.translate_check = QCheckBox("Translate")
        self.log_check = QCheckBox("Save transcript")
        self.log_check.setToolTip(f"Writes a text file to {LOG_DIR}")
        target_row = QHBoxLayout()
        target_row.addWidget(self.target_edit, 1)
        target_row.addWidget(self.translate_check)
        target_row.addWidget(self.log_check)

        form = QFormLayout()
        form.addRow("Speech model", model_row)
        form.addRow("Microphone", self.device_combo)
        form.addRow("Translate into", target_row)

        self.start_button = QPushButton("Start listening")
        self.start_button.clicked.connect(self.toggle_session)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        self.partial_label = QLabel()
        self.partial_label.setWordWrap(True)
        self.partial_label.setMinimumHeight(self.partial_label.fontMetrics().lineSpacing() * 2)
        palette = self.partial_label.palette()
        palette.setColor(QPalette.ColorRole.WindowText,
                         palette.color(QPalette.ColorRole.PlaceholderText))
        self.partial_label.setPalette(palette)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.start_button)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.partial_label)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._config_widgets = [self.model_combo, browse_button, refresh_button,
                                self.device_combo, self.target_edit, self.log_check]
        if client is None:
            self.translate_check.setToolTip("Add OPENAI_API_KEY to .env to turn on translation")

        self.refresh_lists()
        self.restore_settings()
        self._set_running(False)
        self.statusBar().showMessage(
            "Ready" if client else "No OPENAI_API_KEY found, so translation is off. Transcription still works.")

    # ---- model and device lists

    def refresh_lists(self, rescan_audio: bool = False):
        current = self.model_combo.currentData()
        self.model_combo.clear()
        models = {m.path: m for m in find_models()}
        models.update(self._custom_models)
        for info in sorted(models.values(), key=lambda m: (m.lang, m.small, m.path.name)):
            self.model_combo.addItem(info.path.name, info)
            self.model_combo.setItemData(self.model_combo.count() - 1, str(info.path),
                                         Qt.ItemDataRole.ToolTipRole)
        if self.model_combo.count() == 0:
            self.model_combo.addItem("No models found. Unzip a Vosk model into the models folder.", None)
        if current:
            self._select_model(current.path)

        current_device = self.device_combo.currentText()
        self.device_combo.clear()
        self.device_combo.addItem("System default", None)
        try:
            if rescan_audio:  # PortAudio only sees newly plugged-in devices after a reinit
                sd._terminate()
                sd._initialize()
            hostapis = sd.query_hostapis()
            for index, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    api = hostapis[dev["hostapi"]]["name"]
                    self.device_combo.addItem(f"{dev['name']} ({api})", index)
        except Exception as exc:
            self.statusBar().showMessage(f"Couldn't list audio devices: {exc}")
        self._select_text(self.device_combo, current_device)

    def browse_model(self):
        start = MODEL_DIRS[0] if MODEL_DIRS[0].is_dir() else APP_DIR
        folder = QFileDialog.getExistingDirectory(self, "Choose a Vosk model folder", str(start))
        if folder:
            self._select_model(Path(folder), add_if_missing=True)

    def _select_model(self, path: Path, add_if_missing: bool = False):
        path = path.resolve()
        for i in range(self.model_combo.count()):
            info = self.model_combo.itemData(i)
            if info and info.path == path:
                self.model_combo.setCurrentIndex(i)
                return
        if add_if_missing and path.is_dir():
            self._custom_models[path] = model_info(path)
            self.refresh_lists()
            self._select_model(path)

    @staticmethod
    def _select_text(combo: QComboBox, text: str):
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    # ---- sessions

    def toggle_session(self):
        if self.session:
            self.session.stop()
            self.start_button.setEnabled(False)
            self.start_button.setText("Stopping…")
        else:
            self.start_session()

    def start_session(self):
        info: VoskModelInfo | None = self.model_combo.currentData()
        if info is None:
            QMessageBox.information(
                self, APP_NAME,
                "Choose a speech model first.\n\nDownload one from "
                "https://alphacephei.com/vosk/models, unzip it into the models folder "
                "next to this script, then press Refresh. Or pick a folder with Browse.")
            return

        target = self.target_edit.text().strip() or "English"
        translating = self.translate_check.isChecked() and self.client is not None
        started = datetime.now()
        log_path = None
        if self.log_check.isChecked():
            log_path = LOG_DIR / f"transcript_{started:%Y-%m-%d_%H-%M-%S}_{info.lang}.txt"

        view = TranscriptView(info.lang.upper(), target, translating)
        self.tabs.setCurrentIndex(self.tabs.addTab(view, f"{info.lang.upper()} {started:%H:%M}"))
        view.add_info(f"Model: {info.path.name}")
        view.add_info(f"Microphone: {self.device_combo.currentText()}")
        view.add_info(f"Translating into {target} with {OPENAI_MODEL}" if translating
                      else "Transcribing only (translation is off)")

        session = TranslationSession(info, self.device_combo.currentData(), target,
                                     self.client if translating else None, log_path)
        session.status.connect(self.statusBar().showMessage)
        session.partial.connect(self.show_partial)
        session.utterance.connect(view.add_utterance)
        session.translation.connect(view.set_translation)
        session.error.connect(view.add_error)
        session.finished.connect(self.on_session_finished)
        self.session, self.session_view = session, view
        self._set_running(True)
        session.start()

    def on_session_finished(self):
        session, view = self.session, self.session_view
        self.session = self.session_view = None
        if view is not None:
            message = "Stopped."
            if session.log_path and session.log_path.exists():
                message += f" Transcript saved to {session.log_path}"
            view.add_info(message)
        session.deleteLater()
        self.show_partial("")
        self._set_running(False)
        self.statusBar().showMessage("Stopped")

    def show_partial(self, text: str):
        if len(text) > 200:
            text = "…" + text[-200:]
        self.partial_label.setText(f"Hearing: {text}" if text else "")

    def close_tab(self, index: int):
        widget = self.tabs.widget(index)
        if widget is self.session_view:
            self.statusBar().showMessage("Stop listening before closing this tab.", 4000)
            return
        self.tabs.removeTab(index)
        widget.deleteLater()

    def _set_running(self, running: bool):
        for widget in self._config_widgets:
            widget.setEnabled(not running)
        self.translate_check.setEnabled(not running and self.client is not None)
        self.start_button.setEnabled(True)
        self.start_button.setText("Stop listening" if running else "Start listening")

    # ---- settings and shutdown

    def restore_settings(self):
        s = self.settings
        geometry = s.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        model_path = s.value("model_path", "", type=str)
        if model_path:
            self._select_model(Path(model_path), add_if_missing=True)
        self._select_text(self.device_combo, s.value("device", "", type=str))
        self.target_edit.setText(s.value("target", "English", type=str))
        self.translate_check.setChecked(self.client is not None and s.value("translate", True, type=bool))
        self.log_check.setChecked(s.value("logging", False, type=bool))

    def save_settings(self):
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        info = self.model_combo.currentData()
        s.setValue("model_path", str(info.path) if info else "")
        s.setValue("device", self.device_combo.currentText())
        s.setValue("target", self.target_edit.text())
        if self.client is not None:
            s.setValue("translate", self.translate_check.isChecked())
        s.setValue("logging", self.log_check.isChecked())

    def closeEvent(self, event):
        self.save_settings()
        if self.session:
            self.session.stop(discard_pending=True)
            self.session.wait()
        super().closeEvent(event)


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key, timeout=20, max_retries=1) if api_key else None

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow(client)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

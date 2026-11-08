"""
Rafiq Voice AI - Modern Minimalist PyQt6 Application
Supports:
- Dual Modes: PC Direct Mode vs ESP32 Hardware Companion Mode
- 3 Voice Personas: Shakir (شاكر), Salma (سلمى), Kareem (كريم)
- Bilingual Arabic (RTL) & English (LTR)
- Fluid high-DPI sound sphere with dynamic state lighting and real audio frequency reactivity
- Auto-starts backend server if not running
"""
import sys
import os

# Fix Windows console UTF-8 encoding for Arabic text
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import math
import time
import socket
import asyncio
import subprocess
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import websockets

from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QBrush, QPen,
    QFont, QPainterPath, QKeyEvent, QCursor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QDialog, QLineEdit, QGraphicsDropShadowEffect,
    QScrollArea
)

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    from server import config
except ImportError:
    config = None


# Audio Constants
SAMPLE_RATE = 16000
CHUNK_MS = 40
BLOCK_SIZE = SAMPLE_RATE * CHUNK_MS // 1000  # 640 samples = 1280 bytes


def is_port_in_use(port: int = 8765, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


def ensure_server_running(port: int = 8765, host: str = "127.0.0.1"):
    if is_port_in_use(port, host):
        print(f"[+] Rafiq WebSocket server detected on ws://{host}:{port}", flush=True)
        return None
    print(f"[*] Starting Rafiq WebSocket server on ws://{host}:{port} ...", flush=True)
    python_exe = sys.executable
    proc = subprocess.Popen(
        [python_exe, "-m", "server.server"],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(6):
        time.sleep(0.2)
        if is_port_in_use(port, host):
            print(f"[+] Rafiq server started successfully (PID: {proc.pid})", flush=True)
            return proc
    print("[!] Warning: Server did not respond immediately, continuing...", flush=True)
    return proc


# ============================================================================
# Background WebSocket & Audio Thread
# ============================================================================
class VoiceWorker(QThread):
    sig_connected = pyqtSignal(bool, str)
    sig_state = pyqtSignal(str)
    sig_transcript = pyqtSignal(str, str)  # role, text
    sig_energy = pyqtSignal(float)
    sig_language = pyqtSignal(str)
    sig_voice = pyqtSignal(str)

    def __init__(self, ws_url: str = "ws://127.0.0.1:8765"):
        super().__init__()
        self.ws_url = ws_url
        self.loop = None
        self.running = True
        self.mode = "pc"  # "pc" or "esp"
        self.current_lang = "ar"
        self.current_voice = "v1"

        self.send_queue = None
        self.is_recording = False
        self.mic_stream = None
        self.speaker_stream = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.send_queue = asyncio.Queue()
        self.loop.run_until_complete(self._main_loop())

    async def _main_loop(self):
        # Open speaker stream for PC output
        try:
            self.speaker_stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16"
            )
            self.speaker_stream.start()
        except Exception as e:
            print(f"[!] Speaker init error: {e}")

        while self.running:
            try:
                self.sig_connected.emit(False, "Connecting...")
                async with websockets.connect(self.ws_url, max_size=None) as ws:
                    self.sig_connected.emit(True, "Connected")
                    # Send initial setup
                    await ws.send(json.dumps({"type": "set_language", "language": self.current_lang}))
                    await ws.send(json.dumps({"type": "set_voice", "voice": self.current_voice}))

                    recv_task = asyncio.create_task(self._receiver(ws))
                    send_task = asyncio.create_task(self._sender(ws))

                    done, pending = await asyncio.wait(
                        [recv_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
            except Exception as e:
                self.sig_connected.emit(False, f"Disconnected ({e})")
                await asyncio.sleep(2.5)

    async def _receiver(self, ws):
        async for msg in ws:
            if isinstance(msg, bytes):
                # Only play audio out on PC if in PC Mode!
                if self.mode == "pc" and self.speaker_stream:
                    try:
                        samples = np.frombuffer(msg, dtype=np.int16).astype(np.float32)
                        rms = float(np.sqrt(np.mean(np.square(samples))) / 16384.0)
                        self.sig_energy.emit(min(1.0, max(0.1, rms * 1.5)))
                        await asyncio.to_thread(self.speaker_stream.write, msg)
                    except Exception:
                        pass
            else:
                try:
                    d = json.loads(msg)
                    msg_type = d.get("type")
                    if msg_type == "state":
                        self.sig_state.emit(d.get("state", "idle"))
                    elif msg_type == "transcript":
                        self.sig_transcript.emit(d.get("role", "assistant"), d.get("text", ""))
                    elif msg_type == "language_changed":
                        self.sig_language.emit(d.get("language", "ar"))
                    elif msg_type == "voice_changed":
                        self.sig_voice.emit(d.get("voice", "v1"))
                    elif msg_type == "tts_end":
                        self.sig_energy.emit(0.08)
                except Exception:
                    pass

    async def _sender(self, ws):
        while self.running:
            item = await self.send_queue.get()
            if isinstance(item, bytes):
                await ws.send(item)
            elif isinstance(item, dict):
                await ws.send(json.dumps(item))

    def set_mode(self, mode: str):
        self.mode = mode
        if mode == "esp" and self.is_recording:
            self.stop_recording()

    def set_language(self, lang: str):
        self.current_lang = lang
        if self.loop and self.send_queue:
            self.loop.call_soon_threadsafe(
                self.send_queue.put_nowait,
                {"type": "set_language", "language": lang}
            )

    def set_voice(self, voice: str):
        self.current_voice = voice
        if self.loop and self.send_queue:
            self.loop.call_soon_threadsafe(
                self.send_queue.put_nowait,
                {"type": "set_voice", "voice": voice}
            )

    def start_recording(self):
        if self.mode != "pc" or self.is_recording:
            return
        self.is_recording = True

        def audio_cb(indata, frames, t, status):
            if not self.is_recording:
                return
            raw_bytes = bytes(indata)
            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(np.square(samples))) / 16384.0)
            self.sig_energy.emit(min(1.0, max(0.12, rms * 2.0)))
            if self.loop and self.send_queue:
                self.loop.call_soon_threadsafe(self.send_queue.put_nowait, raw_bytes)

        try:
            self.mic_stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=BLOCK_SIZE, callback=audio_cb
            )
            self.mic_stream.start()
            if self.loop and self.send_queue:
                self.loop.call_soon_threadsafe(
                    self.send_queue.put_nowait,
                    {"type": "start", "language": self.current_lang, "voice": self.current_voice}
                )
        except Exception as e:
            print(f"[!] Mic error: {e}")
            self.is_recording = False

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        if self.loop and self.send_queue:
            self.loop.call_soon_threadsafe(
                self.send_queue.put_nowait,
                {"type": "end"}
            )

    def send_text(self, text: str):
        if self.loop and self.send_queue:
            self.loop.call_soon_threadsafe(
                self.send_queue.put_nowait,
                {"type": "text", "text": text}
            )

    def stop(self):
        self.running = False
        self.stop_recording()
        if self.speaker_stream:
            try:
                self.speaker_stream.stop()
                self.speaker_stream.close()
            except Exception:
                pass


# ============================================================================
# Luminous 3D Sound Sphere Widget (QPainter 60 FPS)
# ============================================================================
class SoundSphereWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(340, 340)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.current_state = "idle"  # idle, listening, thinking, speaking
        self.current_energy = 0.1
        self.target_energy = 0.1
        self.orbit_angle = 0.0

        # Animation timer ~60 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)

    def set_state(self, state: str):
        self.current_state = state
        self.update()

    def set_energy(self, energy: float):
        self.target_energy = energy

    def update_animation(self):
        # Smooth lerp
        self.current_energy += (self.target_energy - self.current_energy) * 0.12

        if self.current_state == "idle":
            self.target_energy = 0.08 + math.sin(time.time() * 2.5) * 0.03
        elif self.current_state == "thinking":
            self.orbit_angle += 0.05
            self.target_energy = 0.2 + math.sin(time.time() * 4.0) * 0.08

        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base_radius = 78.0
        current_radius = base_radius + (self.current_energy * 22.0)

        # Pick color palette based on state
        if self.current_state == "listening":
            c_core = QColor(255, 255, 255, 245)
            c_mid = QColor(6, 182, 212, 220)       # Cyan
            c_edge = QColor(16, 185, 129, 90)      # Emerald
            c_ring = QColor(6, 182, 212)
        elif self.current_state == "thinking":
            c_core = QColor(255, 255, 255, 245)
            c_mid = QColor(168, 85, 247, 220)     # Purple
            c_edge = QColor(236, 72, 153, 90)     # Pink
            c_ring = QColor(168, 85, 247)
        elif self.current_state == "speaking":
            c_core = QColor(255, 255, 255, 245)
            c_mid = QColor(59, 130, 246, 230)      # Electric Blue
            c_edge = QColor(99, 102, 241, 100)     # Indigo
            c_ring = QColor(96, 165, 250)
        else:  # Idle
            c_core = QColor(255, 255, 255, 220)
            c_mid = QColor(99, 102, 241, 190)      # Indigo
            c_edge = QColor(14, 165, 233, 60)      # Sky Blue
            c_ring = QColor(99, 102, 241)

        # 1. Concentric acoustic ripple rings (Listening or Speaking)
        if self.current_state in ("listening", "speaking"):
            for i in range(1, 4):
                r = current_radius + (i * 24.0 * (self.current_energy + 0.35))
                alpha = int(max(0.0, (1.0 - (i / 3.8)) * 110 * self.current_energy))
                if alpha > 0:
                    pen = QPen(QColor(c_ring.red(), c_ring.green(), c_ring.blue(), alpha), 1.8)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), r, r)

        # 2. Celestial orbital light beam (Thinking)
        if self.current_state == "thinking":
            orbit_r = current_radius + 15.0
            pen = QPen(QColor(216, 180, 254, 180), 3.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(cx - orbit_r, cy - orbit_r, orbit_r * 2, orbit_r * 2)
            start_angle = int(math.degrees(self.orbit_angle) * 16)
            span_angle = int(140 * 16)
            p.drawArc(rect, start_angle, span_angle)

        # 3. Outer Ambient Diffuse Glow
        glow_grad = QRadialGradient(cx, cy, current_radius + 45.0)
        glow_grad.setColorAt(0.0, QColor(c_mid.red(), c_mid.green(), c_mid.blue(), 50))
        glow_grad.setColorAt(0.7, QColor(c_edge.red(), c_edge.green(), c_edge.blue(), 20))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow_grad))
        p.drawEllipse(QPointF(cx, cy), current_radius + 45.0, current_radius + 45.0)

        # 4. Pristine Main Luminous Sphere (Perfect Geometry with 3-Stop Radial Lighting)
        sphere_grad = QRadialGradient(
            cx - current_radius * 0.32,
            cy - current_radius * 0.32,
            current_radius
        )
        sphere_grad.setColorAt(0.0, c_core)
        sphere_grad.setColorAt(0.35, c_mid)
        sphere_grad.setColorAt(0.85, c_edge)
        sphere_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sphere_grad))
        p.drawEllipse(QPointF(cx, cy), current_radius, current_radius)

        # 5. Center Microphone Icon
        p.setPen(QPen(QColor(255, 255, 255, 200), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Mic body capsule
        mic_top = cy - 14
        mic_w, mic_h = 10, 16
        p.drawRoundedRect(QRectF(cx - mic_w / 2, mic_top, mic_w, mic_h), 5, 5)
        # Mic stand arc
        arc_rect = QRectF(cx - 10, cy - 8, 20, 16)
        p.drawArc(arc_rect, 0, -180 * 16)
        # Stem & base
        p.drawLine(QPointF(cx, cy + 8), QPointF(cx, cy + 14))
        p.drawLine(QPointF(cx - 6, cy + 14), QPointF(cx + 6, cy + 14))


# ============================================================================
# Main PyQt6 Window
# ============================================================================
class RafiqApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("رفيق | Rafiq Voice Assistant")
        self.resize(1160, 790)
        self.setMinimumSize(880, 640)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #09090b;
                color: #f4f4f5;
            }
            QLabel {
                color: #f4f4f5;
            }
        """)

        # Operational state
        self.current_mode = "pc"  # "pc" or "esp"
        self.current_lang = "ar"  # "ar" or "en"
        self.current_voice = "v1"  # "v1", "v2", "v3"
        self.current_state = "idle"

        # Content Dictionary for Seamless Localization
        self.i18n = {
            "ar": {
                "dir": Qt.LayoutDirection.RightToLeft,
                "title": "رفيق",
                "sub": "مساعدك الصوتي الذكي",
                "mode_badge_pc": "وضع الحاسوب",
                "mode_badge_esp": "وضع جهاز رفيق",
                "btn_pc": "💻 الكمبيوتر (مباشر)",
                "btn_esp": "📟 جهاز ESP32",
                "btn_history": "💬 السجل",
                "sidebar_title": "سجل المحادثة الفوري",
                "btn_clear": "مسح",
                "empty_history": "لا توجد رسائل سابقة بعد.\nتحدث لاختبار التعرف على الصوت (STT) والاستماع للرد الصوتي (TTS).",
                "stt_badge": "🎤 صوتك (STT)",
                "tts_badge": "✨ رفيق (TTS)",
                "input_placeholder": "اكتب رسالة لتجربة الرد الصوتي...",
                "btn_send": "إرسال",
                "ready": "جاهز للتحدث",
                "listening": "أستمع إليك الآن...",
                "thinking": "جاري التفكير...",
                "speaking": "يتحدث الآن...",
                "prompt_pc": "اضغط على الدائرة أو استمر بالضغط على المسافة للتحدث",
                "prompt_esp": "تحكّم عبر زر الجهاز الفيزيائي أو كلمة التنبيه",
                "routing_pc": "● الصوت والميكروفون نشطين عبر هذا التطبيق",
                "routing_esp": "● الصوت والميكروفون يعملان عبر عتاد ESP32 فقط",
                "voice_header": "صوت رفيق",
                "sync_hint": "يُحفظ تلقائياً للجهاز",
                "v1_name": "شاكر", "v1_desc": "ودود ومصري",
                "v2_name": "سلمى", "v2_desc": "مشرقة ونقية",
                "v3_name": "كريم", "v3_desc": "رصين وفصيح",
                "key_hint_pc": "[Space] للتحدث",
                "key_hint_esp": "المدخلات من أزرار ESP32",
                "bargein_hint": "يدعم المقاطعة التلقائية المباشرة",
                "device_bar": "جهاز رفيق (ESP32-S3) متصل بالسيرفر",
            },
            "en": {
                "dir": Qt.LayoutDirection.LeftToRight,
                "title": "Rafiq",
                "sub": "Intelligent Voice Companion",
                "mode_badge_pc": "PC Mode",
                "mode_badge_esp": "ESP32 Companion Mode",
                "btn_pc": "💻 PC Direct",
                "btn_esp": "📟 ESP32 Device",
                "btn_history": "💬 History",
                "sidebar_title": "Dialogue History",
                "btn_clear": "Clear",
                "empty_history": "No messages yet.\nSpeak to test speech recognition (STT) and voice response (TTS).",
                "stt_badge": "🎤 You (STT)",
                "tts_badge": "✨ Rafiq (TTS)",
                "input_placeholder": "Type a message to test voice response...",
                "btn_send": "Send",
                "ready": "Ready",
                "listening": "Listening to you...",
                "thinking": "Thinking & Processing...",
                "speaking": "Speaking...",
                "prompt_pc": "Tap the sphere or hold Space to talk",
                "prompt_esp": "Control via physical ESP32 button or wake word",
                "routing_pc": "● Audio input/output active via this application",
                "routing_esp": "● Audio input & output routed via ESP32 hardware only",
                "voice_header": "RAFIQ'S VOICE PERSONA",
                "sync_hint": "Auto-syncs with server",
                "v1_name": "Guy", "v1_desc": "Casual & Warm",
                "v2_name": "Jenny", "v2_desc": "Bright & Clear",
                "v3_name": "Kareem", "v3_desc": "Calm & Articulate",
                "key_hint_pc": "[Space] to talk",
                "key_hint_esp": "Input via ESP32 buttons",
                "bargein_hint": "Barge-in enabled",
                "device_bar": "Rafiq ESP32-S3 Connected to Server",
            }
        }

        # Initialize UI Components
        self.init_ui()

        # Launch Worker Thread
        self.worker = VoiceWorker(ws_url="ws://127.0.0.1:8765")
        self.worker.sig_connected.connect(self.on_ws_connected)
        self.worker.sig_state.connect(self.on_state_changed)
        self.worker.sig_transcript.connect(self.on_transcript)
        self.worker.sig_energy.connect(self.sphere.set_energy)
        self.worker.sig_language.connect(self.on_server_language)
        self.worker.sig_voice.connect(self.on_server_voice)
        self.worker.start()

        # Apply initial language and mode
        self.apply_language("ar")
        self.apply_mode("pc")

    def init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root_hlayout = QHBoxLayout(central)
        root_hlayout.setContentsMargins(0, 0, 0, 0)
        root_hlayout.setSpacing(0)

        # ---------------------------------------------------------
        # Main Voice Interaction Widget (Center Stage)
        # ---------------------------------------------------------
        self.main_voice_widget = QWidget()
        main_layout = QVBoxLayout(self.main_voice_widget)
        main_layout.setContentsMargins(36, 26, 36, 26)
        main_layout.setSpacing(14)

        # 1. Top Header (Brand, Mode Switcher, Language Switcher, History Toggle)
        header_layout = QHBoxLayout()

        # Brand
        brand_box = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #f59e0b; font-size: 16px;")
        
        brand_text_box = QVBoxLayout()
        brand_title_box = QHBoxLayout()
        self.brand_title = QLabel("رفيق")
        self.brand_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        self.mode_badge = QLabel("وضع الحاسوب")
        self.mode_badge.setStyleSheet("""
            background-color: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
        """)
        brand_title_box.addWidget(self.brand_title)
        brand_title_box.addWidget(self.mode_badge)
        brand_title_box.addStretch()

        self.brand_sub = QLabel("مساعدك الصوتي الذكي")
        self.brand_sub.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        brand_text_box.addLayout(brand_title_box)
        brand_text_box.addWidget(self.brand_sub)

        brand_box.addWidget(self.status_dot)
        brand_box.addLayout(brand_text_box)
        header_layout.addLayout(brand_box)

        header_layout.addStretch()

        # Operational Mode Pill (PC vs ESP32)
        mode_pill = QFrame()
        mode_pill.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 2px;
            }
        """)
        mode_pill_layout = QHBoxLayout(mode_pill)
        mode_pill_layout.setContentsMargins(4, 4, 4, 4)
        mode_pill_layout.setSpacing(4)

        self.btn_mode_pc = QPushButton("💻 الكمبيوتر (مباشر)")
        self.btn_mode_pc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_mode_pc.clicked.connect(lambda: self.apply_mode("pc"))

        self.btn_mode_esp = QPushButton("📟 جهاز ESP32")
        self.btn_mode_esp.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_mode_esp.clicked.connect(lambda: self.apply_mode("esp"))

        mode_pill_layout.addWidget(self.btn_mode_pc)
        mode_pill_layout.addWidget(self.btn_mode_esp)
        header_layout.addWidget(mode_pill)

        # Language Switcher Pill
        lang_pill = QFrame()
        lang_pill.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 2px;
            }
        """)
        lang_pill_layout = QHBoxLayout(lang_pill)
        lang_pill_layout.setContentsMargins(4, 4, 4, 4)
        lang_pill_layout.setSpacing(4)

        self.btn_lang_ar = QPushButton("العربية")
        self.btn_lang_ar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_lang_ar.clicked.connect(lambda: self.apply_language("ar"))

        self.btn_lang_en = QPushButton("English")
        self.btn_lang_en.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_lang_en.clicked.connect(lambda: self.apply_language("en"))

        lang_pill_layout.addWidget(self.btn_lang_ar)
        lang_pill_layout.addWidget(self.btn_lang_en)
        header_layout.addWidget(lang_pill)

        # History Toggle Button
        self.btn_toggle_sidebar = QPushButton("💬 السجل")
        self.btn_toggle_sidebar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle_sidebar.setCheckable(True)
        self.btn_toggle_sidebar.setChecked(True)
        self.btn_toggle_sidebar.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.04);
                color: #e4e4e7;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 18px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.09);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.16);
            }
            QPushButton:checked {
                background-color: rgba(6, 182, 212, 0.15);
                color: #22d3ee;
                border-color: rgba(6, 182, 212, 0.35);
            }
        """)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.btn_toggle_sidebar)

        main_layout.addLayout(header_layout)

        # ESP32 Device Banner (Visible only in ESP32 mode)
        self.esp_banner = QFrame()
        self.esp_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.25);
                border-radius: 14px;
                padding: 6px 16px;
            }
        """)
        esp_layout = QHBoxLayout(self.esp_banner)
        esp_dot = QLabel("●")
        esp_dot.setStyleSheet("color: #34d399; font-size: 14px;")
        self.esp_label = QLabel("جهاز رفيق (ESP32-S3) متصل بالسيرفر")
        self.esp_label.setStyleSheet("color: #f4f4f5; font-size: 12px; font-weight: 500;")
        esp_ip = QLabel("ws://127.0.0.1:8765")
        esp_ip.setStyleSheet("color: #a1a1aa; font-family: monospace; font-size: 11px;")
        esp_layout.addWidget(esp_dot)
        esp_layout.addWidget(self.esp_label)
        esp_layout.addWidget(esp_ip)
        esp_layout.addStretch()
        self.esp_banner.hide()
        main_layout.addWidget(self.esp_banner)

        main_layout.addStretch()

        # 2. Central Stage: Sound Sphere Visualizer
        stage_layout = QVBoxLayout()
        stage_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sphere = SoundSphereWidget(self)
        self.sphere.clicked.connect(self.on_sphere_clicked)
        stage_layout.addWidget(self.sphere, alignment=Qt.AlignmentFlag.AlignCenter)

        # State Pill Badge
        self.state_badge = QLabel("جاهز للتحدث")
        self.state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.04);
            color: #38bdf8;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 4px 16px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        stage_layout.addWidget(self.state_badge, alignment=Qt.AlignmentFlag.AlignCenter)

        # Dialogue Subtitle Stream (Teleprompter active line)
        self.subtitle_label = QLabel("اضغط على الدائرة أو استمر بالضغط على المسافة للتحدث")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMaximumWidth(640)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 300;
            color: #e4e4e7;
            padding: 8px 12px;
            line-height: 1.5;
        """)
        stage_layout.addWidget(self.subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Audio Routing Indicator Hint
        self.routing_hint = QLabel("● الصوت والميكروفون نشطين عبر هذا التطبيق")
        self.routing_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.routing_hint.setStyleSheet("font-size: 11px; color: #71717a; font-family: monospace;")
        stage_layout.addWidget(self.routing_hint, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addLayout(stage_layout)

        main_layout.addStretch()

        # 3. Bottom Controls: 3 Voice Personas Selector
        bottom_layout = QVBoxLayout()
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Voice header
        voice_header_widget = QWidget()
        voice_header_widget.setMaximumWidth(540)
        voice_header_box = QHBoxLayout(voice_header_widget)
        voice_header_box.setContentsMargins(6, 0, 6, 0)
        self.voice_header_label = QLabel("صوت رفيق")
        self.voice_header_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #a1a1aa; letter-spacing: 1px;")
        self.sync_hint_label = QLabel("يُحفظ تلقائياً للجهاز")
        self.sync_hint_label.setStyleSheet("font-size: 11px; color: #71717a;")
        voice_header_box.addWidget(self.voice_header_label)
        voice_header_box.addStretch()
        voice_header_box.addWidget(self.sync_hint_label)
        bottom_layout.addWidget(voice_header_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Voice Selector Dock
        voice_dock = QFrame()
        voice_dock.setMaximumWidth(540)
        voice_dock.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 26px;
                padding: 4px;
            }
        """)
        voice_dock_layout = QHBoxLayout(voice_dock)
        voice_dock_layout.setContentsMargins(6, 6, 6, 6)
        voice_dock_layout.setSpacing(6)

        self.btn_v1 = QPushButton("شاكر\nودود ومصري")
        self.btn_v1.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_v1.clicked.connect(lambda: self.apply_voice("v1"))

        self.btn_v2 = QPushButton("سلمى\nمشرقة ونقية")
        self.btn_v2.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_v2.clicked.connect(lambda: self.apply_voice("v2"))

        self.btn_v3 = QPushButton("كريم\nرصين وفصيح")
        self.btn_v3.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_v3.clicked.connect(lambda: self.apply_voice("v3"))

        voice_dock_layout.addWidget(self.btn_v1)
        voice_dock_layout.addWidget(self.btn_v2)
        voice_dock_layout.addWidget(self.btn_v3)
        bottom_layout.addWidget(voice_dock, alignment=Qt.AlignmentFlag.AlignCenter)

        # Hints & Shortcuts
        hints_box = QHBoxLayout()
        self.key_hint_label = QLabel("[Space] للتحدث")
        self.key_hint_label.setStyleSheet("font-size: 11px; color: #71717a; font-family: monospace;")
        bullet = QLabel("•")
        bullet.setStyleSheet("color: #52525b;")
        self.bargein_hint_label = QLabel("يدعم المقاطعة التلقائية المباشرة")
        self.bargein_hint_label.setStyleSheet("font-size: 11px; color: #71717a; font-family: monospace;")
        hints_box.addStretch()
        hints_box.addWidget(self.key_hint_label)
        hints_box.addWidget(bullet)
        hints_box.addWidget(self.bargein_hint_label)
        hints_box.addStretch()
        bottom_layout.addLayout(hints_box)

        main_layout.addLayout(bottom_layout)

        root_hlayout.addWidget(self.main_voice_widget, stretch=1)

        # ---------------------------------------------------------
        # Collapsible Chat History Sidebar
        # ---------------------------------------------------------
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("chatSidebar")
        self.sidebar_frame.setFixedWidth(380)
        self.sidebar_frame.setStyleSheet("""
            QFrame#chatSidebar {
                background-color: #0c0c0e;
                border-inline-start: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(18, 20, 18, 20)
        sidebar_layout.setSpacing(12)

        # Sidebar Header
        sb_header = QHBoxLayout()
        self.sb_title = QLabel("سجل المحادثة الفوري")
        self.sb_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff;")
        
        self.btn_clear_chat = QPushButton("مسح")
        self.btn_clear_chat.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear_chat.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #71717a;
                border: none;
                font-size: 11px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        self.btn_clear_chat.clicked.connect(self.clear_chat)

        self.btn_close_sidebar = QPushButton("✕")
        self.btn_close_sidebar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close_sidebar.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #a1a1aa;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.12);
            }
        """)
        self.btn_close_sidebar.clicked.connect(self.toggle_sidebar)

        sb_header.addWidget(self.sb_title)
        sb_header.addStretch()
        sb_header.addWidget(self.btn_clear_chat)
        sb_header.addWidget(self.btn_close_sidebar)
        sidebar_layout.addLayout(sb_header)

        # Scrollable Chat Bubbles Container
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(4, 8, 4, 8)
        self.chat_layout.setSpacing(12)

        # Empty state label
        self.empty_label = QLabel("لا توجد رسائل سابقة بعد.\nتحدث لاختبار التعرف على الصوت (STT) والاستماع للرد الصوتي (TTS).")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #52525b; font-size: 12px; line-height: 1.6; padding: 50px 16px;")
        self.chat_layout.addWidget(self.empty_label)

        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        sidebar_layout.addWidget(self.chat_scroll, stretch=1)

        # Bottom Text Test Input Bar (To test LLM & TTS without speaking)
        sb_input_box = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("اكتب رسالة لتجربة الرد الصوتي...")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                padding: 8px 14px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #06b6d4;
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)
        self.chat_input.returnPressed.connect(self.on_send_text_clicked)

        self.btn_send_text = QPushButton("إرسال")
        self.btn_send_text.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_send_text.setStyleSheet("""
            QPushButton {
                background-color: #06b6d4;
                color: #09090b;
                border: none;
                border-radius: 16px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #22d3ee;
            }
        """)
        self.btn_send_text.clicked.connect(self.on_send_text_clicked)

        sb_input_box.addWidget(self.chat_input, stretch=1)
        sb_input_box.addWidget(self.btn_send_text)
        sidebar_layout.addLayout(sb_input_box)

        root_hlayout.addWidget(self.sidebar_frame)

    def toggle_sidebar(self):
        visible = not self.sidebar_frame.isVisible()
        self.sidebar_frame.setVisible(visible)
        self.btn_toggle_sidebar.setChecked(visible)

    def add_chat_message(self, role: str, text: str):
        if not text.strip():
            return
        self.empty_label.hide()

        bubble_widget = QWidget()
        bubble_layout = QVBoxLayout(bubble_widget)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(4)

        t = self.i18n[self.current_lang]
        now_str = time.strftime("%I:%M %p")

        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)

        if role == "user":
            badge = QLabel(t["stt_badge"])
            badge.setStyleSheet("color: #22d3ee; font-size: 11px; font-weight: 600;")
            bubble_style = """
                background-color: rgba(6, 182, 212, 0.12);
                border: 1px solid rgba(6, 182, 212, 0.25);
                border-radius: 14px;
                color: #e0f2fe;
                padding: 10px 14px;
                font-size: 13px;
                line-height: 1.4;
            """
        else:
            badge = QLabel(t["tts_badge"])
            badge.setStyleSheet("color: #a78bfa; font-size: 11px; font-weight: 600;")
            bubble_style = """
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 14px;
                color: #f4f4f5;
                padding: 10px 14px;
                font-size: 13px;
                line-height: 1.4;
            """

        time_lbl = QLabel(now_str)
        time_lbl.setStyleSheet("color: #52525b; font-size: 10px; font-family: monospace;")

        header_row.addWidget(badge)
        header_row.addStretch()
        header_row.addWidget(time_lbl)
        bubble_layout.addLayout(header_row)

        msg_card = QLabel(text.strip())
        msg_card.setWordWrap(True)
        msg_card.setStyleSheet(bubble_style)
        bubble_layout.addWidget(msg_card)

        # Insert before stretch item at end
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(max(0, count - 1), bubble_widget)

        # Smooth scroll to bottom
        QTimer.singleShot(60, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def clear_chat(self):
        # Remove all message widgets
        while self.chat_layout.count() > 2:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.empty_label.show()

    def on_send_text_clicked(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.worker.send_text(text)

    # -------------------------------------------------------------
    # Interaction Logic
    # -------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.on_sphere_clicked()
        else:
            super().keyPressEvent(event)

    def on_sphere_clicked(self):
        if self.current_mode == "esp":
            # In ESP32 hardware mode, inform user that buttons on physical hardware handle audio
            msg = "التحكم الصوتي نشط من أزرار جهاز ESP32" if self.current_lang == "ar" else "Audio input is controlled via ESP32 hardware buttons"
            self.subtitle_label.setText(f"« {msg} »")
            return

        # In PC Mode: Toggle Push-to-Talk or Barge-In
        if self.current_state == "idle":
            self.worker.start_recording()
            self.on_state_changed("listening")
        elif self.current_state == "listening":
            self.worker.stop_recording()
        elif self.current_state in ("speaking", "thinking"):
            # Instant Barge-In
            self.worker.start_recording()
            self.on_state_changed("listening")

    def apply_mode(self, mode: str):
        self.current_mode = mode
        self.worker.set_mode(mode)
        t = self.i18n[self.current_lang]

        active_btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
                border: none;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
        """
        inactive_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #a1a1aa;
                border: none;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """

        if mode == "esp":
            self.btn_mode_esp.setStyleSheet(active_btn_style)
            self.btn_mode_pc.setStyleSheet(inactive_btn_style)
            self.mode_badge.setText(t["mode_badge_esp"])
            self.mode_badge.setStyleSheet("""
                background-color: rgba(16, 185, 129, 0.15);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.esp_banner.show()
            self.routing_hint.setText(t["routing_esp"])
            self.key_hint_label.setText(t["key_hint_esp"])
            self.subtitle_label.setText(t["prompt_esp"])
        else:
            self.btn_mode_pc.setStyleSheet(active_btn_style)
            self.btn_mode_esp.setStyleSheet(inactive_btn_style)
            self.mode_badge.setText(t["mode_badge_pc"])
            self.mode_badge.setStyleSheet("""
                background-color: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.esp_banner.hide()
            self.routing_hint.setText(t["routing_pc"])
            self.key_hint_label.setText(t["key_hint_pc"])
            self.subtitle_label.setText(t["prompt_pc"])

    def apply_language(self, lang: str):
        self.current_lang = lang
        self.worker.set_language(lang)
        t = self.i18n[lang]

        # Layout direction
        self.setLayoutDirection(t["dir"])

        active_btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
                border: none;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
        """
        inactive_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #a1a1aa;
                border: none;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """

        if lang == "ar":
            self.btn_lang_ar.setStyleSheet(active_btn_style)
            self.btn_lang_en.setStyleSheet(inactive_btn_style)
        else:
            self.btn_lang_en.setStyleSheet(active_btn_style)
            self.btn_lang_ar.setStyleSheet(inactive_btn_style)

        # Update labels
        self.brand_title.setText(t["title"])
        self.brand_sub.setText(t["sub"])
        self.btn_mode_pc.setText(t["btn_pc"])
        self.btn_mode_esp.setText(t["btn_esp"])
        self.voice_header_label.setText(t["voice_header"])
        self.sync_hint_label.setText(t["sync_hint"])
        self.esp_label.setText(t["device_bar"])
        self.bargein_hint_label.setText(t["bargein_hint"])

        self.btn_v1.setText(f"{t['v1_name']}\n{t['v1_desc']}")
        self.btn_v2.setText(f"{t['v2_name']}\n{t['v2_desc']}")
        self.btn_v3.setText(f"{t['v3_name']}\n{t['v3_desc']}")

        self.btn_toggle_sidebar.setText(t["btn_history"])
        self.sb_title.setText(t["sidebar_title"])
        self.btn_clear_chat.setText(t["btn_clear"])
        self.empty_label.setText(t["empty_history"])
        self.chat_input.setPlaceholderText(t["input_placeholder"])
        self.btn_send_text.setText(t["btn_send"])

        self.apply_mode(self.current_mode)
        self.apply_voice(self.current_voice)
        self.on_state_changed(self.current_state)

    def apply_voice(self, voice: str):
        self.current_voice = voice
        self.worker.set_voice(voice)

        active_voice_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 20px;
                padding: 10px 16px;
                font-size: 12px;
                font-weight: 600;
                line-height: 1.3;
            }
        """
        inactive_voice_style = """
            QPushButton {
                background-color: transparent;
                color: #a1a1aa;
                border: 1px solid transparent;
                border-radius: 20px;
                padding: 10px 16px;
                font-size: 12px;
                font-weight: 500;
                line-height: 1.3;
            }
            QPushButton:hover {
                color: #f4f4f5;
                background-color: rgba(255, 255, 255, 0.04);
            }
        """

        self.btn_v1.setStyleSheet(active_voice_style if voice == "v1" else inactive_voice_style)
        self.btn_v2.setStyleSheet(active_voice_style if voice == "v2" else inactive_voice_style)
        self.btn_v3.setStyleSheet(active_voice_style if voice == "v3" else inactive_voice_style)

    # -------------------------------------------------------------
    # Worker Signals Handling
    # -------------------------------------------------------------
    def on_ws_connected(self, connected: bool, msg: str):
        if connected:
            self.status_dot.setStyleSheet("color: #34d399; font-size: 16px;")
            self.status_dot.setToolTip("Connected to Rafiq Server")
        else:
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 16px;")
            self.status_dot.setToolTip(f"Offline: {msg}")

    def on_state_changed(self, state: str):
        self.current_state = state
        self.sphere.set_state(state)
        t = self.i18n[self.current_lang]

        if state == "listening":
            self.state_badge.setText(t["listening"])
            self.state_badge.setStyleSheet("""
                background-color: rgba(6, 182, 212, 0.15);
                color: #22d3ee;
                border: 1px solid rgba(6, 182, 212, 0.3);
                border-radius: 14px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: 600;
            """)
        elif state == "thinking":
            self.state_badge.setText(t["thinking"])
            self.state_badge.setStyleSheet("""
                background-color: rgba(168, 85, 247, 0.15);
                color: #c084fc;
                border: 1px solid rgba(168, 85, 247, 0.3);
                border-radius: 14px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: 600;
            """)
        elif state == "speaking":
            self.state_badge.setText(t["speaking"])
            self.state_badge.setStyleSheet("""
                background-color: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 14px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: 600;
            """)
        else:  # idle
            self.state_badge.setText(t["ready"])
            self.state_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.04);
                color: #38bdf8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 4px 16px;
                font-size: 12px;
                font-weight: 600;
            """)
            if self.current_mode == "esp":
                self.subtitle_label.setText(t["prompt_esp"])
            else:
                self.subtitle_label.setText(t["prompt_pc"])

    def on_transcript(self, role: str, text: str):
        if text.strip():
            self.subtitle_label.setText(f"« {text.strip()} »")
            self.add_chat_message(role, text.strip())

    def on_server_language(self, lang: str):
        if lang != self.current_lang:
            self.apply_language(lang)

    def on_server_voice(self, voice: str):
        if voice != self.current_voice:
            self.apply_voice(voice)

    def closeEvent(self, event):
        self.worker.stop()
        self.worker.wait(1500)
        event.accept()


# ============================================================================
# Main Entry Point
# ============================================================================
def main():
    # Set Windows App ID for proper taskbar icon and foreground elevation
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("rafiq.voice.assistant.ui")
        except Exception:
            pass

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    print("\n" + "=" * 58, flush=True)
    print("  Rafiq Voice Assistant (PyQt6 Desktop Window)", flush=True)
    print("  Active Mode: PC Direct (Click Sphere or [Space] to talk)", flush=True)
    print("  Target Backend: ws://127.0.0.1:8765", flush=True)
    print("=" * 58 + "\n", flush=True)

    server_proc = ensure_server_running(port=8765)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Font setup
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    window = RafiqApp()

    # Center window on primary monitor
    primary_screen = app.primaryScreen()
    if primary_screen:
        geom = primary_screen.availableGeometry()
        x = max(20, (geom.width() - window.width()) // 2 + geom.x())
        y = max(20, (geom.height() - window.height()) // 2 + geom.y())
        window.move(x, y)

    # Show and force window to foreground
    window.setWindowFlags(window.windowFlags() | Qt.WindowType.Window)
    window.show()
    window.raise_()
    window.activateWindow()

    # Heartbeat timer to keep Python interpreter responsive to signals
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    print("[+] PyQt6 Window rendered successfully on desktop. Event loop started.", flush=True)
    exit_code = app.exec()

    if server_proc:
        try:
            server_proc.terminate()
        except Exception:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

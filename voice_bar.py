#!/usr/bin/env python3
"""
voice-bar: Minimalist Voice-to-Text Dictation & Wayland Input Injector.
Built with GTK4, Gtk4LayerShell, PipeWire, and Whisper for Hyprland / Omarchy.
"""

import os
import sys
import json
import time
import signal
import subprocess
import threading
import urllib.request
import urllib.parse
from pathlib import Path

# Auto-reexec with libgtk4-layer-shell LD_PRELOAD if needed
LAYER_SHELL_LIB = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(LAYER_SHELL_LIB) and "LD_PRELOAD" not in os.environ:
    os.environ["LD_PRELOAD"] = LAYER_SHELL_LIB
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        sys.stderr.write(f"Warning: LD_PRELOAD reexec failed: {e}\n")

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

from gi.repository import Gtk, Gdk, GLib

CONFIG_DIR = Path.home() / ".config/voice-bar"
CONFIG_FILE = CONFIG_DIR / "config.json"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
STATE_FILE = RUNTIME_DIR / "voice-bar.state"
PID_FILE = RUNTIME_DIR / "voice-bar.pid"
RECORD_WAV = RUNTIME_DIR / "voice-bar-input.wav"


DEFAULT_CONFIG = {
    "backend": "groq",  # "groq", "openai", "local_whisper"
    "language": "pl",   # "pl", "en", or "" (auto)
    "groq_api_key": "",
    "openai_api_key": "",
    "groq_model": "whisper-large-v3-turbo",
    "openai_model": "whisper-1",
    "local_whisper_bin": "whisper-cli",
    "local_model_path": "",
    "auto_type": True,
    "copy_to_clipboard": True
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULT_CONFIG.copy()

    # Also check environment variables for API keys
    if "GROQ_API_KEY" in os.environ:
        cfg["groq_api_key"] = os.environ["GROQ_API_KEY"]
    if "OPENAI_API_KEY" in os.environ:
        cfg["openai_api_key"] = os.environ["OPENAI_API_KEY"]

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                user_cfg = json.load(f)
                cfg.update(user_cfg)
        except Exception:
            pass
    else:
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    return cfg


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Could not save config: {e}\n")


def is_recording_process_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        return False


def start_pipewire_recording():
    if RECORD_WAV.exists():
        RECORD_WAV.unlink(missing_ok=True)

    # Use pw-record for native PipeWire 16kHz mono capture
    cmd = [
        "pw-record",
        "--channels", "1",
        "--rate", "16000",
        str(RECORD_WAV)
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PID_FILE.write_text(str(proc.pid))
    return proc.pid


def stop_pipewire_recording():
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGINT)
        time.sleep(0.15)
        if is_recording_process_running():
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    finally:
        PID_FILE.unlink(missing_ok=True)
    return True


def build_multipart_form(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = f"----WebKitFormBoundary{int(time.time()*1000)}"
    body = bytearray()

    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.extend(f"{v}\r\n".encode())

    for k, (filename, file_bytes, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'.encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(file_bytes)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def transcribe_audio(wav_path: Path, cfg: dict) -> str:
    if not wav_path.exists() or wav_path.stat().st_size < 1000:
        return ""

    backend = cfg.get("backend", "groq")
    lang = cfg.get("language", "pl")
    wav_bytes = wav_path.read_bytes()

    # 1. Groq Whisper API
    if backend == "groq" or (backend == "auto" and cfg.get("groq_api_key")):
        key = cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if key:
            try:
                fields = {
                    "model": cfg.get("groq_model", "whisper-large-v3-turbo"),
                    "response_format": "json"
                }
                if lang:
                    fields["language"] = lang

                files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                body, content_type = build_multipart_form(fields, files)

                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": content_type
                    }
                )
                with urllib.request.urlopen(req, timeout=12) as res:
                    data = json.loads(res.read().decode())
                    return data.get("text", "").strip()
            except Exception as e:
                sys.stderr.write(f"Groq API error: {e}\n")

    # 2. OpenAI Whisper API
    if backend == "openai" or (backend == "auto" and cfg.get("openai_api_key")):
        key = cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        if key:
            try:
                fields = {
                    "model": cfg.get("openai_model", "whisper-1"),
                    "response_format": "json"
                }
                if lang:
                    fields["language"] = lang

                files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                body, content_type = build_multipart_form(fields, files)

                req = urllib.request.Request(
                    "https://api.openai.com/v1/audio/transcriptions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": content_type
                    }
                )
                with urllib.request.urlopen(req, timeout=15) as res:
                    data = json.loads(res.read().decode())
                    return data.get("text", "").strip()
            except Exception as e:
                sys.stderr.write(f"OpenAI API error: {e}\n")

    # 3. Local whisper.cpp fallback if binary exists
    whisper_bin = cfg.get("local_whisper_bin", "whisper-cli")
    model_path = cfg.get("local_model_path", "")
    if subprocess.run(["which", whisper_bin], capture_output=True).returncode == 0 and model_path and os.path.exists(model_path):
        try:
            cmd = [whisper_bin, "-m", model_path, "-f", str(wav_path), "-nt"]
            if lang:
                cmd.extend(["-l", lang])
            out = subprocess.check_output(cmd, text=True, timeout=20)
            return out.strip()
        except Exception as e:
            sys.stderr.write(f"Local whisper error: {e}\n")

    return ""


def inject_text(text: str, cfg: dict):
    if not text:
        return

    # Copy to clipboard as backup
    if cfg.get("copy_to_clipboard", True):
        try:
            subprocess.run(["wl-copy", text], check=False)
        except Exception:
            pass

    # Type into active window using wtype
    if cfg.get("auto_type", True):
        try:
            # Type text followed by space
            subprocess.run(["wtype", text + " "], check=True)
        except Exception as e:
            sys.stderr.write(f"wtype injection failed: {e}\n")


class VoiceBarWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("voice-bar")
        self.set_default_size(360, 56)
        self.cfg = load_config()
        self.recording_start_time = None
        self.timer_source = None

        if HAS_LAYER_SHELL:
            Gtk4LayerShell.init_for_window(self)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, True)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 32)
            Gtk4LayerShell.set_namespace(self, "voice-bar")

        self.apply_css()
        self.build_ui()

    def apply_css(self):
        css_data = b"""
        window {
            background-color: transparent;
        }
        .voice-pill {
            background-color: #1a1a24;
            border: 1px solid #3b3b4f;
            border-radius: 28px;
            padding: 6px 14px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
        }
        .mic-btn {
            background: #ff4757;
            color: #ffffff;
            border-radius: 20px;
            padding: 6px 16px;
            font-weight: bold;
            font-size: 13px;
            border: none;
        }
        .mic-btn.idle {
            background: #2f3542;
            color: #f1f2f6;
        }
        .mic-btn:hover {
            opacity: 0.9;
        }
        .status-label {
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
        }
        .lang-btn {
            background: #2f3542;
            color: #70a1ff;
            border-radius: 14px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: bold;
            border: none;
        }
        .close-btn {
            background: transparent;
            color: #747d8c;
            border-radius: 14px;
            padding: 4px 8px;
            border: none;
        }
        .close-btn:hover {
            color: #ff6b81;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def build_ui(self):
        pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pill.add_css_class("voice-pill")

        # Pulse indicator / Mic button
        self.btn_mic = Gtk.Button(label="🎙️ Record")
        self.btn_mic.add_css_class("mic-btn")
        self.btn_mic.add_css_class("idle")
        self.btn_mic.connect("clicked", self.on_mic_toggle)
        pill.append(self.btn_mic)

        # Status / Timer label
        self.lbl_status = Gtk.Label(label="Ready")
        self.lbl_status.add_css_class("status-label")
        pill.append(self.lbl_status)

        # Language chip (PL / EN)
        lang = self.cfg.get("language", "pl").upper() or "AUTO"
        self.btn_lang = Gtk.Button(label=lang)
        self.btn_lang.add_css_class("lang-btn")
        self.btn_lang.connect("clicked", self.on_lang_toggle)
        pill.append(self.btn_lang)

        # Close / Dismiss button
        btn_close = Gtk.Button(label="✕")
        btn_close.add_css_class("close-btn")
        btn_close.connect("clicked", lambda _: self.close())
        pill.append(btn_close)

        self.set_child(pill)

    def on_mic_toggle(self, _):
        if is_recording_process_running():
            self.stop_and_transcribe()
        else:
            self.start_recording()

    def start_recording(self):
        start_pipewire_recording()
        self.recording_start_time = time.time()
        self.btn_mic.remove_css_class("idle")
        self.btn_mic.set_label("⏹ Stop & Type")
        self.lbl_status.set_text("Listening...")

        if self.timer_source:
            GLib.source_remove(self.timer_source)
        self.timer_source = GLib.timeout_add(100, self.update_timer)

    def update_timer(self):
        if not is_recording_process_running() or not self.recording_start_time:
            return False
        elapsed = time.time() - self.recording_start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self.lbl_status.set_text(f"🔴 {mins:02d}:{secs:02d}")
        return True

    def stop_and_transcribe(self):
        stop_pipewire_recording()
        if self.timer_source:
            GLib.source_remove(self.timer_source)
            self.timer_source = None

        self.btn_mic.add_css_class("idle")
        self.btn_mic.set_label("🎙️ Record")
        self.lbl_status.set_text("Transcribing...")

        # Run transcription in background thread to keep GTK responsive
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    def _transcribe_worker(self):
        text = transcribe_audio(RECORD_WAV, self.cfg)
        if text:
            inject_text(text, self.cfg)
            GLib.idle_add(lambda: self.lbl_status.set_text(f"Typed: {text[:20]}..."))
        else:
            has_keys = bool(self.cfg.get("groq_api_key") or self.cfg.get("openai_api_key"))
            msg = "No speech detected" if has_keys else "Configure API Key in config.json"
            GLib.idle_add(lambda: self.lbl_status.set_text(msg))

        GLib.timeout_add(2500, lambda: self.lbl_status.set_text("Ready"))

    def on_lang_toggle(self, _):
        cur = self.cfg.get("language", "pl")
        new_lang = "en" if cur == "pl" else "pl"
        self.cfg["language"] = new_lang
        save_config(self.cfg)
        self.btn_lang.set_label(new_lang.upper())


def cmd_toggle():
    cfg = load_config()
    if is_recording_process_running():
        # Stop and transcribe directly
        stop_pipewire_recording()
        text = transcribe_audio(RECORD_WAV, cfg)
        if text:
            inject_text(text, cfg)
            print(f"Transcribed: {text}")
        else:
            print("No speech or API key missing.")
    else:
        # Start recording
        start_pipewire_recording()
        print("Recording started...")


def cmd_status(json_output=False):
    recording = is_recording_process_running()
    cfg = load_config()
    lang = cfg.get("language", "pl").upper()

    icon = "󰍭" if recording else "󰍬"
    status_text = "Recording" if recording else "Idle"

    if json_output:
        print(json.dumps({
            "recording": recording,
            "language": lang,
            "icon": icon,
            "text": f"{icon} [{lang}]",
            "tooltip": f"Voice Dictation: {status_text} ({lang})\nClick: Toggle Record & Type\nRight-Click: Switch Language"
        }))
    else:
        print(f"Status: {status_text} | Lang: {lang}")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("toggle", "t"):
            cmd_toggle()
            return
        elif arg in ("status", "s"):
            cmd_status(json_output="--json" in sys.argv or "-j" in sys.argv)
            return
        elif arg in ("lang-toggle", "lt"):
            cfg = load_config()
            cfg["language"] = "en" if cfg.get("language", "pl") == "pl" else "pl"
            save_config(cfg)
            print(f"Language set to: {cfg['language'].upper()}")
            return

    # Launch GTK layer shell UI
    app = Gtk.Application(application_id="com.mateusz.voicebar")
    app.connect("activate", lambda a: VoiceBarWindow(a).present())
    app.run(None)


if __name__ == "__main__":
    main()

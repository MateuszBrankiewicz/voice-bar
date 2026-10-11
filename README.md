# 🎙️ voice-bar

A minimalist, high-speed voice-to-text dictation bar and Wayland input injector for **Hyprland** and **Omarchy**. Engineered for 2-in-1 convertible laptops, tablets, and keyboard-free workflows.

Speak naturally in Polish, English, or your native language, and watch your words typed directly into your active input field (browser, terminal, editor, chat) without losing window focus.

---

## ✨ Features

* **Wayland Layer Shell (`gtk4-layer-shell`):**
  * Minimalist floating recording pill docked unobtrusively on screen.
  * **Zero Focus Stealing (`KeyboardMode.NONE`):** The cursor remains inside your active application (Zen Browser, Alacritty, VS Code) while you record and transcribe.
* **Native PipeWire Capture (`pw-record`):**
  * Ultra-low latency 16kHz mono audio recording without heavy third-party audio dependencies.
* **Multi-Backend Speech Engine:**
  * **Groq Whisper API (Default / Recommended):** Sub-300ms transcription speed powered by `whisper-large-v3-turbo`.
  * **OpenAI Whisper API:** Direct support for `whisper-1`.
  * **Local Whisper (`whisper.cpp`):** 100% offline, private transcription running locally on CPU.
* **Automatic Bilingual Support:**
  * Fast 1-click toggling between Polish (`PL`) and English (`EN`) or automatic language detection.
  * Accurately preserves Polish diacritics (`ą`, `ć`, `ę`, `ł`, `ń`, `ó`, `ś`, `ź`, `ż`) and sentence punctuation.
* **Wayland Text Injection (`wtype`):**
  * Injects transcribed text straight into the focused input field, followed by an automatic trailing space.
  * Also copies transcribed text to Wayland clipboard (`wl-copy`) as a safety backup.
* **Desktop & Top Bar Integration:**
  * Omarchy top bar widget (`mateusz.voice`):
    * `󰍬` Idle / Ready
    * `󰍭` Recording (live visual state)
    * **Left-click:** Toggle Record / Insert
    * **Right-click:** Switch language (`PL` ↔ `EN`)
  * Hyprland hotkey: <kbd>SUPER + V</kbd>.

---

## 📦 Requirements

* **Python 3.10+**
* **GTK4** (`python-gobject`)
* **gtk4-layer-shell**
* **pipewire** (`pw-record`)
* **wtype** (virtual keyboard input injector)
* **wl-clipboard** (`wl-copy`)

### Arch Linux / Omarchy
```bash
sudo pacman -S python-gobject gtk4 gtk4-layer-shell pipewire wtype wl-clipboard
```

---

## 🚀 Usage

### 1. Direct CLI Commands
```bash
# Toggle recording (starts recording if idle, stops and types if recording)
voice-bar toggle

# Switch language between PL and EN
voice-bar lang-toggle

# JSON status for status bars
voice-bar status --json

# Launch floating GTK4 layer shell pill
voice-bar
```

### 2. Configuration (`~/.config/voice-bar/config.json`)
```json
{
  "backend": "groq",
  "language": "pl",
  "groq_api_key": "YOUR_GROQ_API_KEY",
  "openai_api_key": "",
  "groq_model": "whisper-large-v3-turbo",
  "openai_model": "whisper-1",
  "auto_type": true,
  "copy_to_clipboard": true
}
```
> **Tip:** You can also set `GROQ_API_KEY` or `OPENAI_API_KEY` in your environment variables.

### 3. Hyprland Keybinding
Add to your `~/.config/hypr/bindings.lua`:
```lua
o.bind("SUPER + V", "Voice Dictation", "voice-bar toggle")
```

---

## 🧩 Architecture

```
User Voice / Speech
        │
        ▼
pw-record (PipeWire 16kHz Mono WAV)
        │
        ├──► Cloud: Groq / OpenAI Whisper API (~300ms)
        └──► Offline: whisper.cpp / local model
        │
        ▼
Transcribed Text
        │
        ├──► wl-copy (Wayland Clipboard Backup)
        │
        ▼
wtype (Wayland virtual-keyboard-v1)
        │
        ▼
Active Application Text Input (Browser, Terminal, Editor)
```

---

## 📄 License
MIT License. Created by [Mateusz Brankiewicz](https://github.com/MateuszBrankiewicz).

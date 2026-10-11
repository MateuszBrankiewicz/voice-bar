# Technical Specification: voice-bar

## 1. Overview
`voice-bar` is a modern, lightweight voice-to-text dictation bar and Wayland input injector designed for **Hyprland** and **Omarchy**.
It allows users—especially on 2-in-1 tablets and laptops—to dictate speech in Polish, English, or any other language and have it transcribed and typed automatically into the active text field of any Wayland application (browser, terminal, editor, chat) without stealing window focus.

---

## 2. Architecture & Tech Stack

### 2.1 Audio Capture & Wayland Layer Shell
* **Audio Server:** PipeWire via native `pw-record` capturing 16kHz mono 16-bit PCM WAV.
* **UI Toolkit:** GTK4 via PyGObject (`gi.repository.Gtk`, `Gdk`).
* **Wayland Layer Shell:** `gtk4-layer-shell`.
  * **Anchoring:** Floating pill / status bar docked at bottom or top of the screen.
  * **Keyboard Mode:** `Gtk4LayerShell.KeyboardMode.NONE` — ensures touching or clicking recording controls never steals keyboard focus from the target text input.
* **Status Feedback:** Pulsing recording indicator, live recording duration, audio status wave, and one-tap Stop & Insert button.

### 2.2 Transcription Pipeline
`voice-bar` features a modular multi-backend transcription engine:
1. **Groq Whisper API (Ultra-Fast Cloud):**
   * Model: `whisper-large-v3-turbo` or `whisper-large-v3`.
   * Latency: ~250–400ms end-to-end.
2. **OpenAI Whisper API:**
   * Model: `whisper-1`.
   * Standard compatibility with any OpenAI-compatible audio endpoint.
3. **Local Offline Engine (`whisper.cpp`):**
   * Uses local quantized GGML/GGUF models (`tiny`, `base`, or `small`).
   * Zero network dependency, 100% private.
4. **Automatic Language Support:**
   * Full bilingual Polish (`pl`) and English (`en`) transcription with punctuation and capitalization.

### 2.3 Wayland Text Injection
* **Protocol:** `virtual-keyboard-v1`.
* **Injector:** `/usr/bin/wtype` typing recognized text directly into the focused Wayland window followed by a space.

---

## 3. Definition of Done (DoD)
1. **Core Application (`voice_bar.py`):**
   * Floating minimalist GTK4 layer shell recording pill.
   * PipeWire capture process management with clean start/stop.
   * Speech-to-text API dispatcher with fallback handling.
   * Direct text typing via `wtype`.
2. **Configuration & Customization:**
   * Configuration file at `~/.config/voice-bar/config.json`.
   * Configurable backend, API keys, language (`pl`/`en`/`auto`), and model.
3. **Omarchy Bar Widget (`mateusz.voice`):**
   * Top bar toggle widget showing microphone state (`󰍬` idle, `󰍭` recording).
   * Left-click: Toggle recording on/off.
   * Right-click: Switch language (PL ↔ EN).
4. **Hyprland Keybinding:**
   * Hotkey binding in `~/.config/hypr/bindings.lua` (e.g. `SUPER + V`).
5. **Git Repository & Documentation:**
   * Dedicated Git repository in `/home/mateusz/Projects/voice-bar/`.
   * Clean English `README.md`, `SPEC.md`, `LICENSE` (MIT), and `.gitignore`.
   * Pushed to GitHub under `MateuszBrankiewicz/voice-bar`.

---

## 4. Acceptance Criteria (AC)
* **AC1:** Triggering `voice-bar toggle` launches the recording UI without stealing focus from active windows.
* **AC2:** `pw-record` records clean 16kHz audio from the default PipeWire source.
* **AC3:** Stopping recording sends the audio to the transcription engine and injects the transcribed text via `wtype`.
* **AC4:** Polish diacritics (ą, ę, ś, ć, ż, ź, etc.) and punctuation are accurately preserved.
* **AC5:** Omarchy status bar widget displays current state in real-time.

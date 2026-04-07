#!/usr/bin/env python3
"""
Meeting Recorder UI — QuickTime backend
錄音引擎：QuickTime Player（AppleScript 控制）
轉錄引擎：faster-whisper（本地）
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import time
import signal
from datetime import datetime
from pathlib import Path

# ─── 設定 ───
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"


class MeetingRecorderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Meeting Recorder")
        self.root.geometry("340x500")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.is_recording = False
        self.is_transcribing = False
        self.start_time = None
        self.current_audio: Path | None = None  # .m4a from QuickTime

        OUTPUT_DIR.mkdir(exist_ok=True)

        self._build_ui()
        self._log("就緒。按 Space 或點按鈕開始錄音。")

    # ─── UI ───
    def _build_ui(self):
        bg = "#1e1e2e"; fg = "#cdd6f4"; accent = "#f38ba8"
        green = "#a6e3a1"; yellow = "#f9e2af"; surface = "#313244"
        self.root.configure(bg=bg)

        # 狀態列
        sf = tk.Frame(self.root, bg=bg)
        sf.pack(pady=(20, 8))
        self.status_dot = tk.Canvas(sf, width=16, height=16, bg=bg, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self.dot = self.status_dot.create_oval(2, 2, 14, 14, fill="#585b70")
        self.status_label = tk.Label(sf, text="待機中", font=("SF Pro", 14), fg=fg, bg=bg)
        self.status_label.pack(side=tk.LEFT)

        # 計時器
        self.timer_label = tk.Label(
            self.root, text="00:00:00", font=("SF Mono", 36, "bold"), fg=fg, bg=bg
        )
        self.timer_label.pack(pady=(4, 12))

        # 錄音按鈕
        self.rec_btn = tk.Button(
            self.root, text="● 開始錄音",
            font=("SF Pro", 15, "bold"), fg="#1e1e2e", bg=accent,
            activebackground="#eba0ac", activeforeground="#1e1e2e",
            relief=tk.FLAT, width=20, height=2,
            command=self._toggle_recording,
        )
        self.rec_btn.pack(pady=(0, 8))

        # 轉錄按鈕
        self.transcribe_btn = tk.Button(
            self.root, text="📝 轉逐字稿",
            font=("SF Pro", 13), fg="#1e1e2e", bg=yellow,
            activebackground="#f9e2af", relief=tk.FLAT,
            width=20, height=2,
            command=self._start_transcribe,
            state=tk.DISABLED,
        )
        self.transcribe_btn.pack(pady=(0, 8))

        # 進度條
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=280)
        self.progress.pack(pady=(0, 8))

        # 日誌區
        lf = tk.Frame(self.root, bg=surface, padx=8, pady=8)
        lf.pack(fill=tk.X, padx=20, pady=(4, 12))
        self.log_text = tk.Text(
            lf, height=7, width=36, font=("SF Mono", 10),
            fg="#a6adc8", bg=surface, relief=tk.FLAT, wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_text.pack()

        # 提示
        tk.Label(
            self.root, text="Space: 錄音開/停  |  T: 轉逐字稿",
            font=("SF Pro", 10), fg="#585b70", bg=bg
        ).pack()

        self.colors = {"bg": bg, "green": green, "accent": accent, "yellow": yellow}

    # ─── 日誌 / 狀態 ───
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_status(self, text: str, color: str):
        self.status_label.config(text=text)
        self.status_dot.itemconfig(self.dot, fill=color)

    # ─── 錄音（QuickTime） ───
    def _toggle_recording(self):
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        self.is_recording = True
        self.start_time = time.time()
        self.current_audio = None

        self.rec_btn.config(text="■ 停止錄音")
        self.transcribe_btn.config(state=tk.DISABLED)
        self._set_status("錄音中", self.colors["accent"])
        self._log("▶ 啟動 QuickTime 錄音...")
        self._update_timer()

        def _run():
            # 開啟 QuickTime 並開始新音訊錄製
            script = '''
tell application "QuickTime Player"
    activate
    set rec to (new audio recording)
    start rec
end tell
'''
            result = subprocess.run(["osascript", "-e", script],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                self.root.after(0, lambda: self._log(f"✗ QuickTime 啟動失敗: {result.stderr.strip()}"))
                self.root.after(0, self._reset_recording_ui)
            else:
                self.root.after(0, lambda: self._log("  QuickTime 錄音中（視窗會在桌面顯示）"))

        threading.Thread(target=_run, daemon=True).start()

    def _stop_recording(self):
        self.is_recording = False
        elapsed = time.time() - self.start_time if self.start_time else 0
        h, r = divmod(int(elapsed), 3600); m, s = divmod(r, 60)

        self._set_status("儲存中...", self.colors["yellow"])
        self._log(f"■ 停止錄音，時長 {h:02d}:{m:02d}:{s:02d}")
        self._log("  儲存中...")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = OUTPUT_DIR / f"{ts}.m4a"
        self.current_audio = save_path

        def _run():
            # 停止並儲存到 output/
            script = f'''
tell application "QuickTime Player"
    stop (document 1)
    delay 1
    save document 1 in POSIX file "{save_path}"
    delay 0.5
    close (document 1) saving no
end tell
'''
            result = subprocess.run(["osascript", "-e", script],
                                    capture_output=True, text=True)
            def _update():
                if save_path.exists() and save_path.stat().st_size > 0:
                    size_mb = save_path.stat().st_size / (1024 * 1024)
                    self._log(f"  ✓ {save_path.name} ({size_mb:.1f} MB)")
                    self._set_status("錄音完成", self.colors["green"])
                    self.transcribe_btn.config(state=tk.NORMAL)
                else:
                    err = result.stderr.strip()
                    self._log(f"  ✗ 儲存失敗{': ' + err if err else ''}")
                    self._set_status("儲存失敗", self.colors["accent"])
                self.rec_btn.config(text="● 開始錄音")
            self.root.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _reset_recording_ui(self):
        self.is_recording = False
        self.rec_btn.config(text="● 開始錄音")
        self._set_status("待機中", "#585b70")

    def _update_timer(self):
        if not self.is_recording:
            return
        elapsed = time.time() - self.start_time
        h, r = divmod(int(elapsed), 3600); m, s = divmod(r, 60)
        self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        cur = self.status_dot.itemcget(self.dot, "fill")
        nxt = self.colors["bg"] if cur == self.colors["accent"] else self.colors["accent"]
        self.status_dot.itemconfig(self.dot, fill=nxt)
        self.root.after(500, self._update_timer)

    # ─── 轉錄 ───
    def _start_transcribe(self):
        if not self.current_audio or not self.current_audio.exists():
            self._log("✗ 找不到錄音檔")
            return

        self.is_transcribing = True
        self.transcribe_btn.config(state=tk.DISABLED, text="轉錄中...")
        self._set_status("轉錄中", self.colors["yellow"])
        self.progress.start(10)
        self._log(f"📝 轉錄 {self.current_audio.name}（首次需下載模型）...")

        audio_path = self.current_audio

        def _run():
            try:
                from faster_whisper import WhisperModel
                self.root.after(0, lambda: self._log("  載入 Whisper medium 模型..."))
                model = WhisperModel("medium", device="auto", compute_type="int8")
                self.root.after(0, lambda: self._log("  轉錄進行中..."))
                segments, info = model.transcribe(str(audio_path), language="zh", beam_size=5)

                lines = []
                for seg in segments:
                    lines.append(f"[{_fmt(seg.start)} → {_fmt(seg.end)}] {seg.text.strip()}")
                transcript = "\n".join(lines)

                md = _build_markdown(transcript, audio_path.name)
                md_path = audio_path.with_suffix(".md")
                md_path.write_text(md, encoding="utf-8")

                self.root.after(0, lambda: self._on_transcribe_done(md_path))

            except ImportError:
                self.root.after(0, lambda: self._log("✗ 請先安裝: pip3 install faster-whisper"))
                self.root.after(0, self._on_transcribe_fail)
            except Exception as e:
                self.root.after(0, lambda: self._log(f"✗ 轉錄失敗: {e}"))
                self.root.after(0, self._on_transcribe_fail)

        threading.Thread(target=_run, daemon=True).start()

    def _on_transcribe_done(self, md_path: Path):
        self.progress.stop()
        self.is_transcribing = False
        self.transcribe_btn.config(state=tk.NORMAL, text="📝 轉逐字稿")
        self._set_status("完成", self.colors["green"])
        self._log(f"✓ 會議記錄: {md_path.name}")
        subprocess.Popen(["open", str(OUTPUT_DIR)])

    def _on_transcribe_fail(self):
        self.progress.stop()
        self.is_transcribing = False
        self.transcribe_btn.config(state=tk.NORMAL, text="📝 轉逐字稿")
        self._set_status("轉錄失敗", self.colors["accent"])

    # ─── 快捷鍵 ───
    def _bind_keys(self):
        self.root.bind("<space>", lambda e: self._toggle_recording())
        self.root.bind("<t>", lambda e: (
            self._start_transcribe()
            if self.transcribe_btn["state"] == tk.NORMAL else None
        ))
        self.root.bind("<T>", lambda e: (
            self._start_transcribe()
            if self.transcribe_btn["state"] == tk.NORMAL else None
        ))

    def run(self):
        self._bind_keys()
        self.root.mainloop()


# ─── 工具函式 ───
def _fmt(s: float) -> str:
    m, sec = divmod(int(s), 60); h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _build_markdown(transcript: str, filename: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# 會議記錄

- **日期**：{now}
- **錄音檔**：{filename}
- **與會者**：（請填入）
- **會議主題**：（請填入）

---

## 逐字稿

{transcript}

---

## 會議摘要

（貼給 AI 整理，或自行填寫）

## 決議事項

1.

## 待辦事項

| 項目 | 負責人 | 截止日期 |
|------|--------|----------|
|      |        |          |
"""


if __name__ == "__main__":
    app = MeetingRecorderApp()
    app.run()

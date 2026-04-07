#!/usr/bin/env python3
"""
Meeting Recorder UI
放桌面雙擊就能啟動的會議錄音工具
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import os
import time
import signal
from datetime import datetime
from pathlib import Path

# ─── 設定 ───
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
SWIFT_SOURCE = BASE_DIR / "record.swift"
RECORDER_BIN = BASE_DIR / "recorder"


class MeetingRecorderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Meeting Recorder")
        self.root.geometry("340x480")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)  # 永遠置頂

        # 狀態
        self.is_recording = False
        self.is_transcribing = False
        self.record_process = None
        self.start_time = None
        self.current_wav = None
        self.current_mic_wav = None

        OUTPUT_DIR.mkdir(exist_ok=True)

        self._build_ui()
        self._ensure_compiler()

    # ─── UI 建構 ───
    def _build_ui(self):
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#f38ba8"
        green = "#a6e3a1"
        yellow = "#f9e2af"
        surface = "#313244"

        self.root.configure(bg=bg)

        # 狀態燈號區
        status_frame = tk.Frame(self.root, bg=bg)
        status_frame.pack(pady=(20, 10))

        self.status_dot = tk.Canvas(
            status_frame, width=16, height=16, bg=bg, highlightthickness=0
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self.dot = self.status_dot.create_oval(2, 2, 14, 14, fill="#585b70")

        self.status_label = tk.Label(
            status_frame, text="待機中", font=("SF Pro", 14), fg=fg, bg=bg
        )
        self.status_label.pack(side=tk.LEFT)

        # 計時器
        self.timer_label = tk.Label(
            self.root, text="00:00:00", font=("SF Mono", 36, "bold"), fg=fg, bg=bg
        )
        self.timer_label.pack(pady=(5, 15))

        # 錄音按鈕
        self.rec_btn = tk.Button(
            self.root,
            text="● 開始錄音",
            font=("SF Pro", 15, "bold"),
            fg="#1e1e2e",
            bg=accent,
            activebackground="#eba0ac",
            activeforeground="#1e1e2e",
            relief=tk.FLAT,
            width=18,
            height=2,
            command=self._toggle_recording,
        )
        self.rec_btn.pack(pady=(0, 10))

        # 轉錄按鈕
        self.transcribe_btn = tk.Button(
            self.root,
            text="📝 轉逐字稿",
            font=("SF Pro", 13),
            fg="#1e1e2e",
            bg=yellow,
            activebackground="#f9e2af",
            relief=tk.FLAT,
            width=18,
            height=2,
            command=self._start_transcribe,
            state=tk.DISABLED,
        )
        self.transcribe_btn.pack(pady=(0, 10))

        # 進度條
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=280)
        self.progress.pack(pady=(0, 10))

        # 日誌區
        log_frame = tk.Frame(self.root, bg=surface, padx=8, pady=8)
        log_frame.pack(fill=tk.X, padx=20, pady=(5, 15))

        self.log_text = tk.Text(
            log_frame,
            height=7,
            width=36,
            font=("SF Mono", 10),
            fg="#a6adc8",
            bg=surface,
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_text.pack()

        # 顏色常數存起來
        self.colors = {
            "bg": bg,
            "green": green,
            "accent": accent,
            "yellow": yellow,
            "gray": "#585b70",
        }

    # ─── 日誌 ───
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ─── 狀態更新 ───
    def _set_status(self, text: str, color: str):
        self.status_label.config(text=text)
        self.status_dot.itemconfig(self.dot, fill=color)

    # ─── 編譯 Swift ───
    def _ensure_compiler(self):
        if not SWIFT_SOURCE.exists():
            self._log("⚠ 找不到 record.swift")
            self._log("  請將 record.swift 放在同目錄")
            return

        # 檢查是否需要重編
        if RECORDER_BIN.exists():
            if RECORDER_BIN.stat().st_mtime > SWIFT_SOURCE.stat().st_mtime:
                self._log("✓ 錄音模組已就緒")
                return

        self._log("編譯錄音模組中...")

        def _compile():
            result = subprocess.run(
                ["swiftc", str(SWIFT_SOURCE), "-o", str(RECORDER_BIN),
                 "-framework", "ScreenCaptureKit",
                 "-framework", "AVFoundation",
                 "-framework", "CoreMedia"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.root.after(0, lambda: self._log("✓ 編譯完成"))
            else:
                err = result.stderr[:300]
                self.root.after(0, lambda: self._log(f"✗ 編譯失敗:\n{err}"))

        threading.Thread(target=_compile, daemon=True).start()

    # ─── 錄音控制 ───
    def _toggle_recording(self):
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        if not RECORDER_BIN.exists():
            self._log("✗ 錄音模組不存在，無法錄音")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_wav = OUTPUT_DIR / f"{timestamp}.wav"
        self.current_mic_wav = OUTPUT_DIR / f"{timestamp}_mic.wav"

        self.is_recording = True
        self.start_time = time.time()

        # 更新 UI
        self.rec_btn.config(text="■ 停止錄音", bg="#f38ba8")
        self._set_status("錄音中", self.colors["accent"])
        self.transcribe_btn.config(state=tk.DISABLED)
        self._log(f"▶ 開始錄音: {self.current_wav.name}")

        # 背景執行錄音
        def _record():
            try:
                self.record_process = subprocess.Popen(
                    [
                        str(RECORDER_BIN),
                        str(self.current_wav),
                        "0",       # 0 = record until SIGINT
                        "both",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.record_process.wait()
            except Exception as e:
                self.root.after(0, lambda: self._log(f"✗ 錄音錯誤: {e}"))

        threading.Thread(target=_record, daemon=True).start()

        # 啟動計時器
        self._update_timer()

    def _stop_recording(self):
        if self.record_process:
            # 送 SIGINT 讓 Swift graceful shutdown
            try:
                self.record_process.send_signal(signal.SIGINT)
                self.record_process.wait(timeout=8)
            except Exception:
                self.record_process.kill()

        self.is_recording = False

        elapsed = time.time() - self.start_time if self.start_time else 0
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)

        self.rec_btn.config(text="● 開始錄音", bg=self.colors["accent"])
        self._set_status("錄音完成", self.colors["green"])
        self.transcribe_btn.config(state=tk.NORMAL)

        self._log(f"■ 錄音結束，時長 {h:02d}:{m:02d}:{s:02d}")

        # 檢查檔案
        if self.current_wav and self.current_wav.exists():
            size_mb = self.current_wav.stat().st_size / (1024 * 1024)
            self._log(f"  系統音訊: {size_mb:.1f} MB")
        if self.current_mic_wav and self.current_mic_wav.exists():
            size_mb = self.current_mic_wav.stat().st_size / (1024 * 1024)
            self._log(f"  麥克風:   {size_mb:.1f} MB")

    def _update_timer(self):
        if not self.is_recording:
            return
        elapsed = time.time() - self.start_time
        h, remainder = divmod(int(elapsed), 3600)
        m, s = divmod(remainder, 60)
        self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")

        # 閃爍紅點
        current = self.status_dot.itemcget(self.dot, "fill")
        next_color = self.colors["bg"] if current == self.colors["accent"] else self.colors["accent"]
        self.status_dot.itemconfig(self.dot, fill=next_color)

        self.root.after(500, self._update_timer)

    # ─── 轉錄 ───
    def _start_transcribe(self):
        if not self.current_wav or not self.current_wav.exists():
            self._log("✗ 找不到錄音檔")
            return

        self.is_transcribing = True
        self.transcribe_btn.config(state=tk.DISABLED, text="轉錄中...")
        self._set_status("轉錄中", self.colors["yellow"])
        self.progress.start(10)
        self._log("📝 開始轉錄（首次需下載模型）...")

        def _transcribe():
            try:
                wav_to_use = self.current_wav

                # 如果有雙軌，先合併
                if self.current_mic_wav and self.current_mic_wav.exists():
                    merged = self.current_wav.parent / (
                        self.current_wav.stem + "_merged.wav"
                    )
                    self.root.after(0, lambda: self._log("  合併雙軌音訊..."))
                    subprocess.run(
                        [
                            "ffmpeg", "-y",
                            "-i", str(self.current_wav),
                            "-i", str(self.current_mic_wav),
                            "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
                            str(merged),
                        ],
                        capture_output=True,
                    )
                    if merged.exists():
                        wav_to_use = merged
                        self.root.after(0, lambda: self._log("  ✓ 合併完成"))

                # 轉錄
                from faster_whisper import WhisperModel

                self.root.after(0, lambda: self._log("  載入 Whisper medium 模型..."))
                model = WhisperModel("medium", device="auto", compute_type="int8")

                self.root.after(0, lambda: self._log("  轉錄進行中..."))
                segments, info = model.transcribe(
                    str(wav_to_use), language="zh", beam_size=5
                )

                lines = []
                for seg in segments:
                    ts = f"[{_fmt(seg.start)} → {_fmt(seg.end)}]"
                    lines.append(f"{ts} {seg.text.strip()}")

                transcript = "\n".join(lines)

                # 產生 Markdown
                md = _build_markdown(transcript, self.current_wav.name)
                md_path = self.current_wav.with_suffix(".md")
                md_path.write_text(md, encoding="utf-8")

                self.root.after(0, lambda: self._on_transcribe_done(md_path))

            except ImportError:
                self.root.after(
                    0,
                    lambda: self._log(
                        "✗ 請先安裝: pip3 install faster-whisper"
                    ),
                )
                self.root.after(0, self._on_transcribe_fail)
            except Exception as e:
                self.root.after(0, lambda: self._log(f"✗ 轉錄失敗: {e}"))
                self.root.after(0, self._on_transcribe_fail)

        threading.Thread(target=_transcribe, daemon=True).start()

    def _on_transcribe_done(self, md_path: Path):
        self.progress.stop()
        self.is_transcribing = False
        self.transcribe_btn.config(state=tk.NORMAL, text="📝 轉逐字稿")
        self._set_status("轉錄完成", self.colors["green"])
        self._log(f"✓ 會議記錄: {md_path.name}")
        self._log("  可用 Finder 打開 output/ 查看")
        # 自動用 Finder 打開資料夾
        subprocess.Popen(["open", str(md_path.parent)])

    def _on_transcribe_fail(self):
        self.progress.stop()
        self.is_transcribing = False
        self.transcribe_btn.config(state=tk.NORMAL, text="📝 轉逐字稿")
        self._set_status("轉錄失敗", self.colors["accent"])

    # ─── 快捷鍵 ───
    def _bind_keys(self):
        # Space: 開始/停止錄音
        self.root.bind("<space>", lambda e: self._toggle_recording())
        # t / T: 觸發轉錄（只在錄音結束後有效）
        self.root.bind("<t>", lambda e: self._start_transcribe() if self.transcribe_btn["state"] == tk.NORMAL else None)
        self.root.bind("<T>", lambda e: self._start_transcribe() if self.transcribe_btn["state"] == tk.NORMAL else None)

    # ─── 啟動 ───
    def run(self):
        self._bind_keys()
        self.root.mainloop()


# ─── 工具函式 ───
def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


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

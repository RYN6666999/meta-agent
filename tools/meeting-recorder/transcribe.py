#!/usr/bin/env python3
"""
M2 — Transcription module
Input:  one or two WAV files (system audio, optionally mic)
Output: timestamped transcript string + Markdown meeting note file
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def merge_tracks(sys_wav: Path, mic_wav: Path) -> Path:
    """Merge system audio + mic into one file using ffmpeg amix."""
    merged = sys_wav.parent / (sys_wav.stem + "_merged.wav")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(sys_wav),
            "-i", str(mic_wav),
            "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
            str(merged),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg merge failed:\n{result.stderr}")
    return merged


def transcribe(wav_path: Path, mic_wav_path: Path | None = None,
               model_size: str = "medium", language: str = "zh") -> str:
    """
    Returns a timestamped transcript string.
    Format per line: [MM:SS → MM:SS] text
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("Error: faster-whisper not installed.\n  pip3 install faster-whisper")

    # Merge tracks if both exist
    audio_file = wav_path
    if mic_wav_path and mic_wav_path.exists():
        print("Merging system audio + microphone tracks...")
        audio_file = merge_tracks(wav_path, mic_wav_path)
        print(f"  → {audio_file.name}")

    print(f"Loading Whisper {model_size} model (first run downloads ~1.5 GB)...")
    model = WhisperModel(model_size, device="auto", compute_type="int8")

    print("Transcribing...")
    segments, info = model.transcribe(str(audio_file), language=language, beam_size=5)

    lines = []
    for seg in segments:
        ts = f"[{fmt_ts(seg.start)} → {fmt_ts(seg.end)}]"
        lines.append(f"{ts} {seg.text.strip()}")

    detected = info.language if info.language else language
    print(f"Done. Detected language: {detected}, duration: {fmt_ts(info.duration)}")
    return "\n".join(lines)


def build_markdown(transcript: str, wav_filename: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# 會議記錄

- **日期**：{now}
- **錄音檔**：{wav_filename}
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


def transcribe_and_save(wav_path: Path, mic_wav_path: Path | None = None) -> Path:
    """Full pipeline: transcribe → save Markdown. Returns the .md path."""
    transcript = transcribe(wav_path, mic_wav_path)
    md_content = build_markdown(transcript, wav_path.name)
    md_path = wav_path.with_suffix(".md")
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Meeting note saved → {md_path}")
    return md_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("wav", help="System audio WAV path")
    p.add_argument("--mic", help="Microphone WAV path (optional, for merging)")
    p.add_argument("--model", default="medium")
    p.add_argument("--lang", default="zh")
    args = p.parse_args()

    wav = Path(args.wav)
    mic = Path(args.mic) if args.mic else None
    transcribe_and_save(wav, mic)

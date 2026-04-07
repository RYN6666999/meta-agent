#!/usr/bin/env python3
"""
M4 — CLI entry point
Commands:
  rec        Start recording (Ctrl+C to stop)
  transcribe Transcribe latest (or specified) WAV
  run        Record then auto-transcribe (one-shot)
"""
import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
SWIFT_SOURCE = BASE_DIR / "record.swift"
RECORDER_BIN = BASE_DIR / "recorder"


# MARK: - Compile Swift

def ensure_recorder():
    """Compile record.swift if binary is missing or source is newer."""
    if not SWIFT_SOURCE.exists():
        sys.exit(f"Error: {SWIFT_SOURCE} not found.")

    need_compile = (
        not RECORDER_BIN.exists()
        or SWIFT_SOURCE.stat().st_mtime > RECORDER_BIN.stat().st_mtime
    )
    if not need_compile:
        return

    print("Compiling record.swift...")
    result = subprocess.run(
        ["swiftc", str(SWIFT_SOURCE), "-o", str(RECORDER_BIN),
         "-framework", "ScreenCaptureKit",
         "-framework", "AVFoundation",
         "-framework", "CoreMedia"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Compile error:")
        print(result.stderr)
        sys.exit(1)
    print("✓ Compiled successfully\n")


def make_output_paths() -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sys_wav = OUTPUT_DIR / f"{ts}.wav"
    mic_wav = OUTPUT_DIR / f"{ts}_mic.wav"
    return sys_wav, mic_wav


# MARK: - Commands

def cmd_rec(args):
    ensure_recorder()
    sys_wav, mic_wav = make_output_paths()
    mode = getattr(args, "mode", "both")
    duration = str(getattr(args, "duration", 0))

    print(f"Recording [{mode}] → {sys_wav.name}")
    print("Press Ctrl+C to stop.\n")

    proc = subprocess.Popen(
        [str(RECORDER_BIN), str(sys_wav), duration, mode]
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        proc.wait()

    print(f"\nFiles in {OUTPUT_DIR}:")
    for f in sorted(OUTPUT_DIR.glob("*.wav")):
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")


def cmd_transcribe(args):
    from transcribe import transcribe_and_save

    if getattr(args, "wav", None):
        wav = Path(args.wav)
    else:
        # Find latest non-mic, non-merged WAV
        wavs = [f for f in sorted(OUTPUT_DIR.glob("*.wav"))
                if "_mic" not in f.stem and "_merged" not in f.stem]
        if not wavs:
            sys.exit("No WAV files found in output/")
        wav = wavs[-1]
        print(f"Using latest: {wav.name}")

    mic_wav = wav.parent / (wav.stem + "_mic.wav")
    mic = mic_wav if mic_wav.exists() else None

    md_path = transcribe_and_save(wav, mic)
    # Open output folder
    subprocess.Popen(["open", str(OUTPUT_DIR)])


def cmd_run(args):
    ensure_recorder()
    sys_wav, mic_wav = make_output_paths()
    mode = getattr(args, "mode", "both")
    duration = str(getattr(args, "duration", 0))

    print(f"Recording [{mode}] → {sys_wav.name}")
    print("Press Ctrl+C to stop.\n")

    proc = subprocess.Popen(
        [str(RECORDER_BIN), str(sys_wav), duration, mode]
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        proc.wait()

    print("\nRecording stopped. Starting transcription...")

    from transcribe import transcribe_and_save
    mic = mic_wav if mic_wav.exists() else None
    if sys_wav.exists():
        md_path = transcribe_and_save(sys_wav, mic)
        subprocess.Popen(["open", str(OUTPUT_DIR)])
    else:
        sys.exit(f"Error: {sys_wav} not found after recording.")


# MARK: - Entry

def main():
    p = argparse.ArgumentParser(prog="meeting-recorder", description="Meeting Recorder CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # rec
    r = sub.add_parser("rec", help="Start recording (Ctrl+C to stop)")
    r.add_argument("--mode", choices=["internal", "microphone", "both"], default="both")
    r.add_argument("--duration", type=float, default=0, help="Auto-stop after N seconds (0=manual)")

    # transcribe
    t = sub.add_parser("transcribe", help="Transcribe latest (or specified) WAV")
    t.add_argument("wav", nargs="?", help="WAV file path (optional, defaults to latest)")

    # run
    ru = sub.add_parser("run", help="Record then auto-transcribe")
    ru.add_argument("--mode", choices=["internal", "microphone", "both"], default="both")
    ru.add_argument("--duration", type=float, default=0)

    args = p.parse_args()

    dispatch = {"rec": cmd_rec, "transcribe": cmd_transcribe, "run": cmd_run}
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()

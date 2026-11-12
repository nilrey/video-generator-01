#!/usr/bin/env python3
"""Обрезка тишины в начале/конце mp3-озвучки.

Читает SCENES (импортом из video_creator) и обрабатывает
assets/voice/<key>.mp3 → assets/voice_trimmed/<key>.wav
"""
import os, subprocess, sys
import numpy as np
import wave
from shorts_creator import SCENES 

IN_DIR   = r"D:\Projects\video-generator-01\assets\voice"
OUT_DIR   = r"D:\Projects\video-generator-01\assets\voice_trimmed"
VOICE_EXT = ".mp3"
SR        = 44100
THRESHOLD = 0.02          # порог «тишины» по амплитуде (−34 dBFS)
PAD_MS    = 50            # запас вокруг речи, мс


def decode_mp3(path, sr=SR):
    cmd = ["ffmpeg", "-v", "error", "-i", path,
           "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1",
           "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def find_bounds(x, thr=THRESHOLD):
    """Возвращает (start_sample, end_sample) по громкости."""
    mask = np.abs(x) > thr
    if not mask.any():
        return 0, len(x)
    idx = np.where(mask)[0]
    return int(idx[0]), int(idx[-1]) + 1


def write_wav(path, x, sr=SR):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pad = int(PAD_MS * SR / 1000)
    report = []
    for sc in SCENES:
        key = sc["key"]
        src = os.path.join(IN_DIR, key + VOICE_EXT)
        if not os.path.exists(src):
            print(f"[skip] {key}: нет файла {src}")
            continue
        x = decode_mp3(src)
        a, b = find_bounds(x)
        a = max(0, a - pad)
        b = min(len(x), b + pad)
        trimmed = x[a:b]
        dst = os.path.join(OUT_DIR, key + ".wav")
        write_wav(dst, trimmed)
        cut_head = a / SR
        cut_tail = (len(x) - b) / SR
        report.append((key, len(x) / SR, cut_head, cut_tail, len(trimmed) / SR))
        print(f"{key:8s} было {len(x)/SR:6.2f} c  →  стало {len(trimmed)/SR:6.2f} c  "
              f"(срезано: {cut_head:.2f} c / {cut_tail:.2f} c)")
    print(f"\nГотово: {len(report)} файлов в {OUT_DIR}")


if __name__ == "__main__":
    main()
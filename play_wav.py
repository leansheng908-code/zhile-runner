#!/usr/bin/env python3
"""WAV播放器 - 独立进程运行MCI，避免daemon线程无消息泵问题"""
import sys
import ctypes

def play(path):
    w = ctypes.windll.winmm
    alias = "zhile_tts"
    # 用mpegvideo类型（兼容性最好，wav/mp3都能播）
    open_cmd = f'open "{path}" type mpegvideo alias {alias}'
    ret = w.mciSendStringW(open_cmd, None, 0, None)
    if ret != 0:
        # 尝试不指定类型
        ret = w.mciSendStringW(f'open "{path}" alias {alias}', None, 0, None)
        if ret != 0:
            print(f"[play_wav] open failed: {ret}", flush=True)
            return
    w.mciSendStringW(f'play {alias} wait', None, 0, None)
    w.mciSendStringW(f'close {alias}', None, 0, None)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python play_wav.py <wav_path>")
        sys.exit(1)
    play(sys.argv[1])

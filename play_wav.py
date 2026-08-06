#!/usr/bin/env python3
"""WAV播放器 - 带完整诊断"""
import sys
import os
import ctypes
import struct

def play(path):
    # 1. 检查文件
    if not os.path.exists(path):
        print(f"[play_wav] 文件不存在: {path}")
        return False
    sz = os.path.getsize(path)
    print(f"[play_wav] 文件: {path}")
    print(f"[play_wav] 大小: {sz} bytes")

    # 2. 检查WAV格式
    with open(path, 'rb') as f:
        h = f.read(44)
    if h[:4] != b'RIFF' or h[8:12] != b'WAVE':
        print(f"[play_wav] 不是WAV文件! RIFF={h[:4]} WAVE={h[8:12]}")
    else:
        af = struct.unpack('<H', h[20:22])[0]
        ch = struct.unpack('<H', h[22:24])[0]
        sr = struct.unpack('<I', h[24:28])[0]
        bits = struct.unpack('<H', h[34:36])[0]
        print(f"[play_wav] 格式: audio_fmt={af} ch={ch} rate={sr} bits={bits}")

    w = ctypes.windll.winmm
    alias = "zhile_tts"

    # 3. 尝试MCI mpegvideo
    for mci_type in ['mpegvideo', 'waveaudio', '']:
        try:
            if mci_type:
                open_cmd = f'open "{path}" type {mci_type} alias {alias}'
            else:
                open_cmd = f'open "{path}" alias {alias}'
            ret = w.mciSendStringW(open_cmd, None, 0, None)
            print(f"[play_wav] MCI open (type={mci_type or 'auto'}): ret={ret}")
            if ret == 0:
                # 查询时长
                buf = ctypes.create_unicode_buffer(256)
                w.mciSendStringW(f'status {alias} length', buf, 256, None)
                print(f"[play_wav] 时长: {buf.value}")
                
                # 播放
                ret2 = w.mciSendStringW(f'play {alias} wait', None, 0, None)
                print(f"[play_wav] MCI play wait: ret={ret2}")
                w.mciSendStringW(f'close {alias}', None, 0, None)
                print(f"[play_wav] MCI close: done")
                if ret2 == 0:
                    print(f"[play_wav] ✅ 播放成功!")
                    return True
            else:
                print(f"[play_wav] MCI open失败，换类型")
        except Exception as e:
            print(f"[play_wav] MCI异常 (type={mci_type}): {e}")
        finally:
            w.mciSendStringW(f'close {alias}', None, 0, None)

    # 4. 尝试winsound
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
        print(f"[play_wav] winsound: 无异常（但不一定有声）")
        return True
    except Exception as e:
        print(f"[play_wav] winsound异常: {e}")

    print(f"[play_wav] ❌ 所有方式都失败了")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python play_wav.py <wav_path>")
        sys.exit(1)
    ok = play(sys.argv[1])
    sys.exit(0 if ok else 1)

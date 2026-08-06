#!/usr/bin/env python3
"""WAV播放器 - 修正流式WAV头部 + 音量调节 + MCI播放"""
import sys
import os
import ctypes
import struct
import array

def fix_wav_header(data):
    """检查并修正WAV头部data chunk size（流式输出可能写0）"""
    if len(data) < 44:
        return data
    fixed = bytearray(data)
    riff_size = struct.unpack('<I', data[4:8])[0]
    data_size = struct.unpack('<I', data[40:44])[0]
    actual_data = len(data) - 44
    if data_size == 0 or data_size != actual_data:
        fixed[40:44] = struct.pack('<I', actual_data)
    expected_riff = len(data) - 8
    if riff_size != expected_riff:
        fixed[4:8] = struct.pack('<I', expected_riff)
    return bytes(fixed)

def apply_volume(data, volume):
    """调节16位PCM WAV音量 (-100~+100)"""
    if volume == 0 or len(data) < 44:
        return data
    factor = 1.0 + volume / 100.0  # -100→0.0, 0→1.0, +100→2.0
    if factor <= 0:
        # 静音：保留头部，清零数据
        return data[:44] + b'\x00' * (len(data) - 44)
    # 解析音频参数
    bits = struct.unpack('<H', data[34:36])[0]
    if bits != 16:
        return data  # 非16位PCM不支持
    # 提取音频数据（跳过44字节头部）
    audio_data = array.array('h')
    audio_data.frombytes(data[44:])
    # 缩放
    for i in range(len(audio_data)):
        val = int(audio_data[i] * factor)
        if val > 32767:
            val = 32767
        elif val < -32768:
            val = -32768
        audio_data[i] = val
    return data[:44] + audio_data.tobytes()

def play(path, volume=0):
    if not os.path.exists(path):
        print(f"[play_wav] 文件不存在: {path}")
        return False
    
    with open(path, 'rb') as f:
        raw = f.read()
    
    # 修正WAV头部
    raw = fix_wav_header(raw)
    
    # 音量调节
    if volume != 0:
        raw = apply_volume(raw, volume)
    
    # 写到临时文件
    tmp = path + '.play.wav'
    with open(tmp, 'wb') as f:
        f.write(raw)
    
    w = ctypes.windll.winmm
    alias = "zhile_tts"
    
    try:
        # waveaudio对WAV更准确
        ret = w.mciSendStringW(f'open "{tmp}" type waveaudio alias {alias}', None, 0, None)
        if ret != 0:
            ret = w.mciSendStringW(f'open "{tmp}" type mpegvideo alias {alias}', None, 0, None)
        if ret != 0:
            ret = w.mciSendStringW(f'open "{tmp}" alias {alias}', None, 0, None)
        if ret != 0:
            print(f"[play_wav] open failed: {ret}")
            return False
        
        ret2 = w.mciSendStringW(f'play {alias} wait', None, 0, None)
        w.mciSendStringW(f'close {alias}', None, 0, None)
        return ret2 == 0
    except Exception as e:
        print(f"[play_wav] error: {e}")
        return False
    finally:
        w.mciSendStringW(f'close {alias}', None, 0, None)
        if os.path.exists(tmp):
            os.remove(tmp)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python play_wav.py <wav_path> [volume]")
        sys.exit(1)
    vol = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ok = play(sys.argv[1], vol)
    sys.exit(0 if ok else 1)

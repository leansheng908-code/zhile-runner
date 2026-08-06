#!/usr/bin/env python3
"""WAV播放器 - 修正流式WAV头部 + MCI播放"""
import sys
import os
import ctypes
import struct
import tempfile

def fix_wav_header(path):
    """检查并修正WAV头部data chunk size（流式输出可能写0）"""
    with open(path, 'rb') as f:
        data = f.read()
    
    if len(data) < 44:
        return path  # 太小，不处理
    
    riff_size = struct.unpack('<I', data[4:8])[0]
    data_size = struct.unpack('<I', data[40:44])[0]
    actual_data = len(data) - 44
    
    need_fix = False
    fixed = bytearray(data)
    
    # 修正data chunk size
    if data_size == 0 or data_size != actual_data:
        fixed[40:44] = struct.pack('<I', actual_data)
        need_fix = True
    
    # 修正RIFF size
    expected_riff = len(data) - 8
    if riff_size != expected_riff:
        fixed[4:8] = struct.pack('<I', expected_riff)
        need_fix = True
    
    if need_fix:
        # 写到临时文件
        tmp = path + '.fixed.wav'
        with open(tmp, 'wb') as f:
            f.write(fixed)
        print(f"[play_wav] 修正WAV头部: data_size {data_size}→{actual_data}, riff_size {riff_size}→{expected_riff}")
        return tmp
    
    return path

def play(path):
    if not os.path.exists(path):
        print(f"[play_wav] 文件不存在: {path}")
        return False
    
    sz = os.path.getsize(path)
    print(f"[play_wav] 文件: {path} ({sz} bytes)")
    
    # 修正WAV头部
    play_path = fix_wav_header(path)
    
    # MCI播放（waveaudio类型对WAV更准确）
    w = ctypes.windll.winmm
    alias = "zhile_tts"
    
    for mci_type in ['waveaudio', 'mpegvideo', '']:
        try:
            if mci_type:
                open_cmd = f'open "{play_path}" type {mci_type} alias {alias}'
            else:
                open_cmd = f'open "{play_path}" alias {alias}'
            ret = w.mciSendStringW(open_cmd, None, 0, None)
            if ret != 0:
                continue
            
            buf = ctypes.create_unicode_buffer(256)
            w.mciSendStringW(f'status {alias} length', buf, 256, None)
            length = buf.value
            print(f"[play_wav] MCI(type={mci_type or 'auto'}) 时长={length}")
            
            if length == '0':
                w.mciSendStringW(f'close {alias}', None, 0, None)
                continue
            
            ret2 = w.mciSendStringW(f'play {alias} wait', None, 0, None)
            w.mciSendStringW(f'close {alias}', None, 0, None)
            
            if ret2 == 0:
                print(f"[play_wav] ✅ 播放成功!")
                # 清理临时文件
                if play_path != path and os.path.exists(play_path):
                    os.remove(play_path)
                return True
        except Exception as e:
            print(f"[play_wav] MCI异常: {e}")
        finally:
            w.mciSendStringW(f'close {alias}', None, 0, None)
    
    # 清理临时文件
    if play_path != path and os.path.exists(play_path):
        os.remove(play_path)
    print(f"[play_wav] ❌ 所有MCI类型失败")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python play_wav.py <wav_path>")
        sys.exit(1)
    ok = play(sys.argv[1])
    sys.exit(0 if ok else 1)

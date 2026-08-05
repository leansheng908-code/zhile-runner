#!/usr/bin/env python3
"""
pytest配置 — 自动将运行器根目录加入sys.path
确保 tests/ 下的测试文件能直接 import 运行器模块
"""
import sys
import os

_RUNNER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RUNNER_DIR not in sys.path:
    sys.path.insert(0, _RUNNER_DIR)

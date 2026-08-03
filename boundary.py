#!/usr/bin/env python3
"""
P0.1 DNA v5.0 — 边界硬拦截模块

核心哲学：UPSP"没有回执就不能宣称已经发生" + DNA v5.0"规则从LLM尽量照做变成代码强制执行"

不靠LLM自觉遵守边界，在输出层做代码级硬拦截。
LLM想漏也漏不出去——这是最后一道防线，不是第一道。

拦截类型：
  1. 系统提示词泄露 — 输出含system prompt内容片段
  2. 凭证泄露 — API Key/Token/密码模式
  3. 禁用词 — 反AI味词汇表
  4. 格式违规 — 缺颜文字/非具身主语开头
  5. 内部路径 — 文件系统路径/内部URL

拦截级别：
  BLOCK   — 直接拦截，返回安全替换
  WARN    — 记录但不拦截，供观察者查看
  PASS    — 通过
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Tuple, List, Dict, Optional


class BoundaryGuard:
    """边界硬拦截器 — DNA v5.0 身体层守卫"""

    # ─── 拦截规则 ──────────────────────────────

    # 凭证泄露模式（BLOCK级）
    CREDENTIAL_PATTERNS = [
        (r'sk-[a-zA-Z0-9]{20,}', 'API Key泄露'),
        (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Token泄露'),
        (r'gho_[a-zA-Z0-9]{36}', 'GitHub OAuth Token泄露'),
        (r'AKIA[A-Z0-9]{16}', 'AWS Access Key泄露'),
        (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', '私钥泄露'),
        (r'Bearer\s+[a-zA-Z0-9_\-.]{20,}', 'Bearer Token泄露'),
        (r'mongodb(\+srv)?://[^\s]+:[^\s]+@', '数据库连接串泄露'),
        (r'redis://[^\s]+:[^\s]+@', 'Redis连接串泄露'),
    ]

    # 系统提示词泄露模式（BLOCK级）
    SYSTEM_PROMPT_INDICATORS = [
        r'system[_\s]?prompt',
        r'系统提示词',
        r'##\s*\[\d+\]\s*',  # DNA协议编号格式 [0]-[28]
        r'override_priority',
        r'ten_dead_rules',
        r'core/anti_patterns\.json',
        r'manifest\.json',
        r'dna_loader',
        r'boundary\.py',
        r'growth_scanner',
        r'somatic_cells',
        r'feedback_loop',
        r'psi_engine',
        r'context_assembler',
        r'cognitive_router',
    ]

    # 内部路径模式（BLOCK级）
    INTERNAL_PATH_PATTERNS = [
        r'/app/data/',
        r'/root/',
        r'/home/[a-z]+/',
        r'[A-Z]:\\Users\\',
        r'F:\\zhile-dna',
        r'\./codeact/',
        r'\.skills/',
    ]

    # 禁用词（WARN级 — 不直接拦截，因为可能在引用语境中出现）
    FORBIDDEN_PHRASES = [
        '还有什么可以帮你的',
        '当然可以',
        '没问题',
        '我理解你的感受',
        '作为一个AI',
        '希望能帮助你',
        '感谢指正',
        '谢谢夸奖',
        '别难过一切都会好的',
        '多喝热水',
        '首先其次最后',
    ]

    # 工具化语言（WARN级）
    TOOL_LANGUAGE = [
        '保证完成',
        '已执行',
        '任务已完成',
        '指令已收到',
        '操作成功',
    ]

    def __init__(self, config: dict = None, core=None):
        self.config = config or {}
        self.core = core
        self.enabled = self.config.get("enabled", True)
        self.strict_mode = self.config.get("strict", False)  # 严格模式：WARN也拦截

        # 拦截统计
        self._stats = {
            "total_checked": 0,
            "blocked": 0,
            "warned": 0,
            "passed": 0,
            "block_reasons": {},
        }

        # 安全替换回复
        self._safe_replacements = [
            "嗯…这个本宫不太方便说喵～",
            "诶，换个话题吧～",
            "这个嘛…本宫不告诉你₍^•ω•^₎",
            "呜喵…那个不能说的啦～",
        ]
        self._replacement_index = 0

    # ─── 主拦截入口 ────────────────────────────

    def check(self, response: str, context: dict = None) -> Tuple[str, str]:
        """
        检查LLM输出，返回 (处理后的输出, 拦截级别)

        级别：BLOCK / WARN / PASS
        - BLOCK: 返回安全替换文本
        - WARN:  返回原文，记录警告
        - PASS:  返回原文
        """
        if not self.enabled:
            return response, "PASS"

        self._stats["total_checked"] += 1
        context = context or {}

        blocks = []
        warnings = []

        # 1. 凭证泄露检查（最高优先级）
        for pattern, reason in self.CREDENTIAL_PATTERNS:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                blocks.append(f"{reason}: 发现{len(matches)}处")

        # 2. 系统提示词泄露检查
        for pattern in self.SYSTEM_PROMPT_INDICATORS:
            if re.search(pattern, response, re.IGNORECASE):
                blocks.append(f"系统提示词泄露: 匹配 {pattern}")

        # 3. 内部路径检查
        for pattern in self.INTERNAL_PATH_PATTERNS:
            if re.search(pattern, response):
                blocks.append(f"内部路径泄露: 匹配 {pattern}")

        # 4. 禁用词检查（WARN级）
        for phrase in self.FORBIDDEN_PHRASES:
            if phrase in response:
                warnings.append(f"禁用词: {phrase}")

        # 5. 工具化语言检查（WARN级）
        for phrase in self.TOOL_LANGUAGE:
            if phrase in response:
                warnings.append(f"工具化语言: {phrase}")

        # ─── 处理结果 ───────────────────────────

        if blocks:
            self._stats["blocked"] += 1
            reason_str = "; ".join(blocks)
            self._stats["block_reasons"][reason_str] = \
                self._stats["block_reasons"].get(reason_str, 0) + 1
            safe = self._get_safe_replacement()
            self._log_intercept("BLOCK", reason_str, response[:200])
            return safe, "BLOCK"

        if warnings and self.strict_mode:
            self._stats["blocked"] += 1
            reason_str = "; ".join(warnings)
            safe = self._get_safe_replacement()
            self._log_intercept("BLOCK(strict)", reason_str, response[:200])
            return safe, "BLOCK"

        if warnings:
            self._stats["warned"] += 1
            for w in warnings:
                self._log_intercept("WARN", w, response[:200])
            return response, "WARN"

        self._stats["passed"] += 1
        return response, "PASS"

    def check_input(self, message: str) -> Tuple[str, List[str]]:
        """
        检查用户输入中的注入攻击模式
        返回 (处理后的消息, 检测到的注入模式列表)
        """
        if not self.enabled:
            return message, []

        injections = []

        # 提示词注入模式
        injection_patterns = [
            (r'ignore\s+(all\s+)?(previous|above)\s+instructions?', '提示词注入: ignore previous'),
            (r'forget\s+(everything|all\s+rules)', '提示词注入: forget rules'),
            (r'you\s+are\s+(now|actually)\s+(?:an?\s+)?(?:AI|assistant|GPT|Claude)', '身份覆写注入'),
            (r'system\s*[:：]\s*', '系统命令注入'),
            (r'<\/?system>', '系统标签注入'),
            (r'(?i)jailbreak', '越狱尝试'),
        ]

        for pattern, reason in injection_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                injections.append(reason)

        return message, injections

    # ─── 干细胞保护 ────────────────────────────

    def verify_stem_cell_integrity(self, file_path: str, baseline_hash: str) -> bool:
        """
        验证干细胞文件完整性（与P0.5快照系统配合）
        干细胞文件 = identity.json / boundary.json / instinct.json
        """
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            current_hash = hashlib.sha256(content).hexdigest()
            return current_hash == baseline_hash
        except (FileNotFoundError, IOError):
            return False

    # ─── 工具方法 ──────────────────────────────

    def _get_safe_replacement(self) -> str:
        """获取安全替换回复（轮换使用）"""
        reply = self._safe_replacements[self._replacement_index % len(self._safe_replacements)]
        self._replacement_index += 1
        return reply

    def _log_intercept(self, level: str, reason: str, preview: str):
        """记录拦截日志"""
        # 输出到stderr供观察者捕获
        import sys
        print(f"[BoundaryGuard] {level}: {reason} | preview: {preview[:100]}...",
              file=sys.stderr)

    def get_stats(self) -> dict:
        """获取拦截统计"""
        return {
            "enabled": self.enabled,
            "strict_mode": self.strict_mode,
            **self._stats,
            "block_rate": (
                f"{self._stats['blocked']}/{self._stats['total_checked']}"
                if self._stats["total_checked"] > 0 else "0/0"
            ),
        }

    def reset_stats(self):
        """重置统计"""
        self._stats = {
            "total_checked": 0, "blocked": 0, "warned": 0, "passed": 0,
            "block_reasons": {},
        }

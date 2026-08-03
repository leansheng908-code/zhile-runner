"""
DNA加载器 v5.0 — 支持三层结构(soul/mind/body)，向后兼容v4.0

v5.0新增：
  - detect_version() 自动检测DNA版本
  - load_soul() 加载灵魂层（soul/*.md拼接为prompt）
  - load_body() 加载身体层（body/*.json配置）
  - get_mind_modules() 返回心智层模块声明（供运行器import）
  - load_system_prompt() 向后兼容：v5.0走soul，v4.0走system_prompt.md

职责：
  1. 检测DNA版本，选择对应加载方式
  2. v5.0: soul/*.md → system prompt, body/*.json → 配置, mind/ → 模块声明
  3. v4.0: system_prompt.md → system prompt (原逻辑不变)
  4. 可选注入 data/USER.md + data/MEMORY.md
  5. verify() 验证DNA完整性
"""

import json
import re
from pathlib import Path


class DNALoader:
    def __init__(self, dna_path: str):
        self.dna_path = Path(dna_path).resolve()
        if not self.dna_path.exists():
            raise FileNotFoundError(f"DNA路径不存在: {self.dna_path}")
        self._version = self._detect_version()

    # ─── 版本检测 ──────────────────────────────

    def _detect_version(self) -> str:
        """自动检测DNA版本：有soul/目录→v5.0，否则→v4.0"""
        # v5.0: 有 manifest.json + soul/ 目录
        manifest = self.dna_path / "manifest.json"
        soul_dir = self.dna_path / "soul"
        if manifest.exists() and soul_dir.exists():
            return "v5.0"

        # v4.0: 有 system_prompt.md
        prompt_file = self.dna_path / "system_prompt.md"
        if prompt_file.exists():
            return "v4.0"

        return "unknown"

    def get_version(self) -> str:
        return self._version

    # ─── 系统提示词加载 ────────────────────────

    def load_system_prompt(self, inject_memory: bool = True,
                           memory_files: list = None) -> str:
        """
        加载系统提示词（自动选择v5.0或v4.0路径）
        """
        if self._version == "v5.0":
            return self._load_v5_prompt(inject_memory, memory_files)
        else:
            return self._load_v4_prompt(inject_memory, memory_files)

    def _load_v5_prompt(self, inject_memory: bool, memory_files: list) -> str:
        """v5.0: 拼接soul/*.md为system prompt"""
        soul_dir = self.dna_path / "soul"

        # 加载manifest获取文件顺序
        manifest = self.load_manifest()
        soul_files = manifest.get("soul", {}).get("files", [
            "soul/identity.md",
            "soul/personality.md",
            "soul/expression.md",
            "soul/anti_patterns.md",
        ])

        parts = []
        for filepath in soul_files:
            full_path = self.dna_path / filepath
            if full_path.exists():
                with open(full_path, "r", encoding="utf-8") as f:
                    parts.append(f.read().strip())

        prompt = "\n\n---\n\n".join(parts)

        # 注入记忆
        if inject_memory and memory_files:
            memory_content = self._load_memory(memory_files)
            if memory_content:
                prompt += (
                    "\n\n---\n"
                    "## 即时记忆层（运行器自动注入）\n\n"
                    + memory_content
                )

        return prompt

    def _load_v4_prompt(self, inject_memory: bool, memory_files: list) -> str:
        """v4.0: 原始system_prompt.md加载（向后兼容）"""
        prompt_file = self.dna_path / "system_prompt.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"系统提示词文件不存在: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        if inject_memory and memory_files:
            memory_content = self._load_memory(memory_files)
            if memory_content:
                system_prompt += (
                    "\n\n---\n"
                    "## 即时记忆层（运行器自动注入）\n\n"
                    + memory_content
                )

        return system_prompt

    # ─── v5.0 专用接口 ────────────────────────

    def load_manifest(self) -> dict:
        """加载manifest.json"""
        manifest_file = self.dna_path / "manifest.json"
        if not manifest_file.exists():
            return {}
        with open(manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_body(self) -> dict:
        """
        v5.0: 加载身体层配置
        返回 {config_name: config_dict} 映射
        """
        if self._version != "v5.0":
            return {}

        manifest = self.load_manifest()
        body_configs = manifest.get("body", {}).get("configs", {})

        result = {}
        for name, rel_path in body_configs.items():
            full_path = self.dna_path / rel_path
            if full_path.exists():
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        result[name] = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

        return result

    def get_mind_modules(self) -> dict:
        """
        v5.0: 返回心智层模块声明
        供运行器知道需要import哪些模块
        """
        if self._version != "v5.0":
            return {}

        manifest = self.load_manifest()
        return manifest.get("mind", {}).get("modules", {})

    def get_soul_stats(self) -> dict:
        """v5.0: 获取灵魂层统计"""
        if self._version != "v5.0":
            return {"version": self._version}

        manifest = self.load_manifest()
        soul_files = manifest.get("soul", {}).get("files", [])

        total_chars = 0
        file_stats = []
        for filepath in soul_files:
            full_path = self.dna_path / filepath
            if full_path.exists():
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                total_chars += len(content)
                file_stats.append({
                    "file": filepath,
                    "chars": len(content),
                })

        target = manifest.get("soul", {}).get("target_words", 2000)
        return {
            "version": "v5.0",
            "files": file_stats,
            "total_chars": total_chars,
            "target_chars": target,
            "compression_ratio": f"{total_chars}/38092" if total_chars > 0 else "N/A",
        }

    # ─── 模型配置 ──────────────────────────────

    def load_model_config(self) -> dict:
        """加载模型配置（v5.0和v4.0通用）"""
        # v5.0: config/model_config.json
        config_file = self.dna_path / "config" / "model_config.json"
        if not config_file.exists():
            # v5.0: 也可能在body/中定义
            body = self.load_body()
            if "model" in body:
                return body["model"]
            return {}

        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_core_config(self, name: str) -> dict:
        """加载单个核心配置文件（兼容v4.0 core/xxx.json）"""
        config_file = self.dna_path / "core" / f"{name}.json"
        if not config_file.exists():
            return {}
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # ─── 记忆加载 ──────────────────────────────

    def _load_memory(self, files: list) -> str:
        """加载记忆文件（v5.0和v4.0通用）"""
        data_dir = self.dna_path / "data"
        parts = []
        for filename in files:
            filepath = data_dir / filename
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    parts.append(f"### {filename}\n\n{content}")
        return "\n\n".join(parts)

    # ─── 验证 ──────────────────────────────────

    def verify(self) -> list:
        """验证DNA文件完整性，返回缺失文件列表"""
        missing = []

        if self._version == "v5.0":
            # v5.0: 检查soul层文件
            manifest = self.load_manifest()
            soul_files = manifest.get("soul", {}).get("files", [
                "soul/identity.md",
                "soul/personality.md",
                "soul/expression.md",
                "soul/anti_patterns.md",
            ])
            for f in soul_files:
                if not (self.dna_path / f).exists():
                    missing.append(f)

            # 检查manifest.json
            if not (self.dna_path / "manifest.json").exists():
                missing.append("manifest.json")

        else:
            # v4.0: 检查原始文件
            required = [
                "system_prompt.md",
                "config/model_config.json",
                "core/identity.json",
            ]
            for f in required:
                if not (self.dna_path / f).exists():
                    missing.append(f)

        return missing

    def get_dna_version(self) -> str:
        """获取DNA版本号"""
        if self._version == "v5.0":
            manifest = self.load_manifest()
            return manifest.get("version", "5.0")
        else:
            prompt_file = self.dna_path / "system_prompt.md"
            if not prompt_file.exists():
                return "unknown"
            with open(prompt_file, "r", encoding="utf-8") as f:
                first_line = f.readline()
            match = re.search(r"v(\d+\.\d+)", first_line)
            return f"v{match.group(1)}" if match else "unknown"

    # ─── 兼容性信息 ────────────────────────────

    def get_platform_mode(self, platform: str = "runner") -> str:
        """
        获取指定平台的DNA使用模式
        runner: soul+mind+body
        coze: soul+body
        astrbot: soul only
        """
        if self._version != "v5.0":
            return "full"  # v4.0全部作为prompt

        manifest = self.load_manifest()
        compat = manifest.get("compatibility", {})
        return compat.get(platform, {}).get("mode", "soul + mind + body")

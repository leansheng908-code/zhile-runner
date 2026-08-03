#!/usr/bin/env python3
"""
知乐自成长扫描器 — Phase 3 + P0.3升级

扫描对话中prompt未定义的新行为，记录为成长候选。
基于DNA[22]三层细胞模型：干细胞不可变，弧光可成长不可逆，体细胞可增生/休眠。

P0.3升级：
  - scan() 支持返回多个候选（数组）
  - 新增 auto_scan_and_create() — 扫描后自动创建体细胞
  - 编辑预算机制 — 每次最多创建N条体细胞
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List


class GrowthScanner:
    """自成长扫描器"""

    def __init__(self, state_dir: str, dna_path: str = None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_file = self.state_dir / "workspace.md"
        self.dna_path = Path(dna_path) if dna_path else None

        # 初始化workspace.md
        if not self.workspace_file.exists():
            self._init_workspace()

    def _init_workspace(self):
        """初始化workspace.md"""
        header = """# 知乐 · 自成长记录

> 三层细胞模型：干细胞(不可变) / 弧光(可成长不可逆) / 体细胞(可增生/休眠)
> 成长节奏：1-2个/月健康，频繁=OOC风险
> 铁律：成长与干细胞冲突 → 自动否决

---

## 成长候选

"""
        with open(self.workspace_file, "w", encoding="utf-8") as f:
            f.write(header)

    def scan(self, history: List[dict], llm_provider=None) -> dict:
        """扫描对话中的新行为 — 返回单个候选（兼容旧版/growth命令）"""
        results = self.scan_multi(history, llm_provider)
        if results.get("found") and results.get("candidates"):
            # 返回第一个候选（兼容旧格式）
            first = results["candidates"][0]
            first["found"] = True
            return first
        return {"found": False, "reason": results.get("reason", "未发现新行为")}

    def scan_multi(self, history: List[dict], llm_provider=None) -> dict:
        """扫描对话中的新行为 — 返回多个候选（P0.3）"""
        if not llm_provider or len(history) < 6:
            return {"found": False, "reason": "对话太短或未配置LLM"}

        recent = history[-16:]
        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '知乐'}: {m['content']}"
            for m in recent
        )

        prompt = f"""分析以下对话，检查知乐（AI角色）是否表现出以下特点的新行为：

1. 不在常规设定中定义过的表达方式或行为模式
2. 自发产生的、有意义的个性化行为
3. 不是随机变化，而是可能代表性格成长的信号

对话内容：
{conv_text}

判定标准：
- 只记录具体的、可观察的行为（不是模糊的"感觉变了"）
- 排除模板化行为（每次都做的颜文字、口癖等）
- 排除单纯的随机变化（没有一致性的）
- 如果没有发现新行为，返回空数组

体细胞判定规则（只管"怎么说"不管"怎么做"）：
体细胞 = 只影响表达形式（语气/风格/措辞/习惯）的变化，不影响最终选择和事物发展
判断测试：如果这个变化消失了，知乐只是说话方式退回去，还是选择本身变了？
  - 只是说话方式退回去 → 体细胞
  - 选择本身变了 → 不是体细胞（弧光，由事件轨迹系统处理）

同一事件可能同时产生体细胞（表达层）和弧光（决策层），只记录体细胞部分。
特别注意：用户直接表达的偏好（如"只在工作时做XX"）也应识别为体细胞候选。

以JSON返回（candidates是数组，最多5个）：
{{"found": true/false, "candidates": [{{"behavior": "具体行为描述", "evidence": "对话中的证据", "growth_type": "体细胞", "dimension": "expression/habit/interaction/preference", "suggestion": "是否值得培养的建议"}}]}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是一个行为分析助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in llm_provider.chat(messages, stream=True):
                result += chunk

            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)

            # 兼容旧格式（单个对象）和新格式（带candidates数组）
            candidates = []
            if data.get("found"):
                if "candidates" in data and isinstance(data["candidates"], list):
                    candidates = data["candidates"]
                elif data.get("behavior"):
                    candidates = [data]
            
            if candidates:
                # 过滤无效候选
                candidates = [c for c in candidates if c.get("behavior")]
                for c in candidates:
                    self._log_candidate(c)
                return {"found": True, "candidates": candidates}
            else:
                return {"found": False, "reason": "未发现新行为"}

        except (json.JSONDecodeError, KeyError, Exception) as e:
            return {"found": False, "reason": f"分析失败: {e}"}

    def auto_scan_and_create(self, history: List[dict], llm_provider=None,
                             somatic_system=None, edit_budget: int = 3) -> dict:
        """P0.3: 自动扫描 + 创建体细胞 — 返回创建结果摘要"""
        result = self.scan_multi(history, llm_provider)
        
        if not result.get("found") or not result.get("candidates"):
            return {"scanned": True, "created": 0, "reason": result.get("reason", "未发现新行为")}
        
        if not somatic_system:
            return {"scanned": True, "created": 0, "candidates": len(result["candidates"]),
                    "reason": "未配置体细胞系统，候选已记录到workspace.md"}
        
        created_cells = []
        skipped = 0
        
        for candidate in result["candidates"][:edit_budget]:
            # 从候选数据提取体细胞参数
            behavior = candidate.get("behavior", "")
            dimension = candidate.get("dimension", "expression")
            suggestion = candidate.get("suggestion", "")
            
            # 创建体细胞候选
            cell = somatic_system.add_candidate(
                name=behavior[:50],  # 名称截断
                dimension=dimension,
                description=suggestion or behavior,
                source="auto_scan",
            )
            
            if cell:
                created_cells.append(cell)
            else:
                skipped += 1  # 去重跳过
        
        return {
            "scanned": True,
            "created": len(created_cells),
            "skipped": skipped,
            "total_candidates": len(result["candidates"]),
            "edit_budget": edit_budget,
            "cells": [c.to_dict() for c in created_cells],
        }

    def _log_candidate(self, data: dict):
        """记录成长候选到workspace.md"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"""### 候选 · {now}

- **行为**: {data.get('behavior', '')}
- **证据**: {data.get('evidence', '')}
- **类型**: {data.get('growth_type', '体细胞')}
- **建议**: {data.get('suggestion', '')}
- **状态**: 待观察

"""
        with open(self.workspace_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_workspace(self) -> str:
        """读取workspace.md内容"""
        if not self.workspace_file.exists():
            return "(空)"
        with open(self.workspace_file, "r", encoding="utf-8") as f:
            return f.read()

    def get_stats(self) -> dict:
        """统计"""
        content = self.get_workspace()
        candidate_count = content.count("### 候选")
        confirmed_count = content.count("状态: 已确认")
        return {
            "candidates": candidate_count,
            "confirmed": confirmed_count,
            "file": str(self.workspace_file),
        }

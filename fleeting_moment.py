#!/usr/bin/env python3
"""
瞬时感知层 — 一期一会机制

记忆共振时产生一次性的感受描述，注入当前回复上下文，用完即弃。
不修改 PSI 值、不修改标签权重、不持久化任何系统状态。
唯一持久痕迹是可选的知觉日记条目（score >= diary_threshold 时）。

核心原则：
  - 绝不修改 PSI 值
  - 绝不修改标签权重
  - 绝不持久化任何系统状态（除可选日记条目）
  - descriptor 只作为局部变量存在于一次回复生成期间
  - 日记条目只记现象（"好像有种X的感觉"），不分析不判断
  - 任何异常都静默跳过，绝不中断对话
"""

import os
import random
from datetime import datetime
from typing import Optional, Dict, Any, Union, List


# ─── 感受模板（按共振分三档）─────────────────────

_FEELING_TEMPLATES = {
    # 隐约 (1.0 - 1.5)：记忆微微浮起，说不清道不明
    "faint": [
        "翻到一段旧记忆，隐约有些熟悉，说不上来。",
        "好像之前聊过类似的事，一闪而过。",
        "旧事微微浮上来，又好像要沉下去。",
        "记忆深处好像有什么在轻轻回应，但抓不住。",
        "有什么旧的事在远处闪了一下，像水面上的光。",
    ],
    # 明显 (1.5 - 2.0)：记忆清晰浮起，与天时呼应
    "clear": [
        "旧记忆浮上来，和此刻的天时有些呼应，有种时间重叠的感觉。",
        "翻到旧事，共振分明——那时和现在，好像隔着时间对望。",
        "记忆涌上来，带着那时的气息，和此刻的天空莫名相合。",
        "旧事翻起，和当下的时空有种微妙的共振，像两段旋律意外合拍。",
        "记忆清晰浮起，此刻的气韵好像在回应那时，说不清但分明。",
    ],
    # 强烈 (2.0+)：记忆扑面而来，今昔交叠
    "intense": [
        "这段记忆扑面而来，共振强烈。此刻与那时的时空仿佛在重叠。",
        "旧事翻涌，天时共振——好像又回到了那个当下，一瞬间分不清今昔。",
        "记忆与天时强烈交叠，一种深邃的似曾相识感涌上来。",
        "记忆汹涌而至，时空在此刻折叠——那时的事就在眼前，呼吸可闻。",
        "强烈共振，记忆与当下猛烈交叠，一瞬间恍惚回到了那个时刻。",
    ],
}

# ─── 卦象氛围词映射 ─────────────────────────────

_HEXAGRAM_MOOD = {
    "乾为天": "刚健清明",
    "坤为地": "厚载包容",
    "水雷屯": "初生艰难",
    "山水蒙": "蒙昧待启",
    "水天需": "静待时机",
    "天水讼": "争锋对峙",
    "地水师": "整肃有序",
    "水地比": "亲近和合",
    "风天小畜": "蓄势待发",
    "天泽履": "谨慎前行",
    "地天泰": "通泰安和",
    "天地否": "闭塞不通",
    "天火同人": "和谐共鸣",
    "火天大有": "丰盛光明",
    "地山谦": "谦逊虚心",
    "雷地豫": "愉悦振奋",
    "泽雷随": "随顺应变",
    "山风蛊": "整治积弊",
    "地泽临": "居高临下",
    "风地观": "观望审视",
    "火雷噬嗑": "明断果决",
    "山火贲": "文饰华美",
    "山地剥": "剥落衰败",
    "地雷复": "回复重生",
    "天雷无妄": "无妄正直",
    "山天大畜": "大积深蓄",
    "山雷颐": "养正蓄德",
    "泽风大过": "过载非常",
    "坎为水": "险陷重险",
    "离为火": "光明附丽",
    "泽山咸": "感应交感",
    "雷风恒": "恒久不变",
    "天山遁": "退避隐遁",
    "雷天大壮": "强盛壮健",
    "火地晋": "晋升光明",
    "地火明夷": "光明受伤",
    "风火家人": "家人和睦",
    "火泽睽": "乖违背离",
    "水山蹇": "蹇滞难行",
    "雷水解": "解除困厄",
    "山泽损": "减损克制",
    "风雷益": "增益进取",
    "泽天夬": "决断果行",
    "天风姤": "邂逅相遇",
    "泽地萃": "聚集汇合",
    "地风升": "上升进长",
    "泽水困": "困穷受困",
    "水风井": "井养不竭",
    "泽火革": "变革更新",
    "火风鼎": "鼎新稳固",
    "震为雷": "震动惊起",
    "艮为山": "静止安定",
    "风山渐": "渐进有序",
    "雷泽归妹": "归终有终",
    "雷火丰": "丰盛盛大",
    "火山旅": "旅行行进",
    "巽为风": "顺风随入",
    "兑为泽": "喜悦和悦",
    "风水涣": "涣散消解",
    "水泽节": "节制适度",
    "风泽中孚": "诚信中实",
    "雷山小过": "小有过越",
    "水火既济": "既成圆满",
    "火水未济": "未成待续",
}


class FleetingMoment:
    """瞬时感知层 — 一期一会，不持久化任何系统状态"""

    def __init__(self, diary_path: str = "data/perception_diary.md",
                 resonance_threshold: float = 1.0,
                 diary_threshold: float = 1.5):
        self.diary_path = diary_path
        self.resonance_threshold = resonance_threshold
        self.diary_threshold = diary_threshold
        self._current_descriptor: Optional[str] = None

    def generate(self, resonance_results: Union[str, List[Any]],
                 hexagram_info: Optional[Dict] = None) -> Optional[Dict]:
        """
        输入：共振检索结果（格式化字符串或结果列表）+ 当前卦象信息（可选）
        输出：dict 或 None
          {
            'descriptor': str,     # 注入上下文的瞬时感受文本
            'score': float,        # 触发它的共振分
            'is_notable': bool,    # 是否记入知觉日记
          }
        如果共振分 < threshold 或无结果，返回 None
        """
        try:
            # 解析共振结果，提取分数和顶部记忆内容
            score, top_memory_content = self._parse_results(resonance_results)

            if score is None or score < self.resonance_threshold:
                return None

            # 组合感受文本
            feeling_text = self._compose_feeling(score, top_memory_content, hexagram_info)

            is_notable = score >= self.diary_threshold
            if is_notable:
                self._maybe_diary(feeling_text, score)

            descriptor = self._format_descriptor(feeling_text)
            self._current_descriptor = descriptor

            return {
                "descriptor": descriptor,
                "score": round(score, 4),
                "is_notable": is_notable,
            }
        except Exception:
            # 任何异常都静默跳过，绝不中断对话
            return None

    def _parse_results(self, resonance_results: Union[str, List[Any]]) -> tuple:
        """
        从共振结果中提取分数和顶部记忆内容。

        支持两种输入：
        - 字符串（格式化记忆列表）：非空视为 score=1.0，取首条记忆内容
        - 列表（MemoryResult 或 Memory 对象）：取最高分，取顶部记忆内容
        """
        if not resonance_results:
            return None, None

        if isinstance(resonance_results, str):
            # 格式化字符串 — 检查是否非空
            text = resonance_results.strip()
            if not text:
                return None, None
            # 从格式化文本中提取第一条记忆内容
            top_content = self._extract_first_memory_from_text(text)
            # 字符串模式没有精确分数，用基准分 1.0
            return 1.0, top_content

        if isinstance(resonance_results, (list, tuple)):
            if len(resonance_results) == 0:
                return None, None

            max_score = 0.0
            top_content = None
            for item in resonance_results:
                # 尝试多种分数字段
                item_score = 0.0
                if hasattr(item, "score"):
                    item_score = float(item.score)
                elif hasattr(item, "_resonance_boost"):
                    item_score = float(item._resonance_boost)
                elif isinstance(item, dict):
                    item_score = float(item.get("score", item.get("_resonance_boost", 0.0)))

                if item_score > max_score:
                    max_score = item_score
                    # 提取记忆内容
                    if hasattr(item, "memory"):
                        top_content = getattr(item.memory, "content", str(item.memory))
                    elif hasattr(item, "content"):
                        top_content = item.content
                    elif isinstance(item, dict):
                        mem = item.get("memory", {})
                        top_content = mem.get("content", "") if isinstance(mem, dict) else str(item)

            if max_score <= 0:
                # 列表非空但分数全为0，用基准分
                return 1.0, top_content
            return max_score, top_content

        return None, None

    def _extract_first_memory_from_text(self, text: str) -> Optional[str]:
        """从格式化记忆文本中提取第一条记忆的内容（模糊引用）"""
        try:
            lines = text.strip().split("\n")
            for line in lines:
                line = line.strip()
                # 格式化记忆行形如 "  - [fact] 某某内容"
                if line.startswith("- ") or line.startswith("  - "):
                    # 去掉前缀 "- [category] "
                    content = line.lstrip("- ").strip()
                    # 去掉 [category] 前缀
                    if content.startswith("["):
                        close = content.find("]")
                        if close > 0:
                            content = content[close + 1:].strip()
                    if content:
                        return content[:30]
            # 没找到标准格式行，取第一个非空行
            for line in lines:
                line = line.strip()
                if line and not line.startswith("【"):
                    return line[:30]
            return None
        except Exception:
            return None

    def _compose_feeling(self, score: float, top_memory: Optional[str],
                        hexagram_info: Optional[Dict]) -> str:
        """
        根据共振强度 + 记忆内容 + 卦象氛围组合感受文本。
        按共振分三档：隐约(1.0-1.5) / 明显(1.5-2.0) / 强烈(2.0+)
        卦象名可融入氛围词，记忆内容取前30字做模糊引用。
        """
        # 选择档位
        if score >= 2.0:
            tier = "intense"
        elif score >= 1.5:
            tier = "clear"
        else:
            tier = "faint"

        templates = _FEELING_TEMPLATES[tier]
        feeling = random.choice(templates)

        # 融入卦象氛围词
        if hexagram_info:
            hex_name = hexagram_info.get("name", "") if isinstance(hexagram_info, dict) else ""
            if hex_name and hex_name in _HEXAGRAM_MOOD:
                mood = _HEXAGRAM_MOOD[hex_name]
                feeling += f"（{hex_name}·{mood}）"

        # 模糊引用记忆内容（不直接复述，取前30字做模糊化）
        if top_memory:
            # 截断到30字，加省略号
            ref = top_memory[:30]
            if len(top_memory) > 30:
                ref += "…"
            # 模糊化：不说"我记得"，而是"旧事里好像有…"
            feeling += f' 好像旧事里有什么和"{ref}"相关的，隐隐约约。'

        return feeling

    def _format_descriptor(self, feeling_text: str) -> str:
        """格式化为注入 LLM 上下文的 descriptor 文本"""
        return (
            "## 瞬时感知·一期一会\n\n"
            f"{feeling_text}\n\n"
            "注意：这是此刻翻涌的一阵感觉，只存在于这一句话里。"
            "让它自然影响你的语气和用词，不必说出，下一刻它就消散了。"
        )

    def _maybe_diary(self, feeling_text: str, score: float):
        """
        如果 score >= diary_threshold，追加一行到知觉日记。
        格式：2026-08-05 07:00 — {feeling_text}
        文件不存在则创建，写入失败静默跳过。
        """
        if score < self.diary_threshold:
            return

        try:
            now = datetime.now()
            entry = f"{now.strftime('%Y-%m-%d %H:%M')} — {feeling_text}\n"

            # 确保目录存在
            diary_dir = os.path.dirname(self.diary_path)
            if diary_dir and not os.path.exists(diary_dir):
                os.makedirs(diary_dir, exist_ok=True)

            # 追加写入（文件不存在则创建）
            with open(self.diary_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            # 写入失败静默跳过，绝不中断对话
            pass

    def clear(self):
        """清空当前瞬时感知（回复生成后调用）"""
        self._current_descriptor = None

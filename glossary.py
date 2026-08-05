#!/usr/bin/env python3
"""
术数术语中性化感知注释模块

加载 term_glossary.json，提供 annotate_text() 函数，
在 context_assembler.get_system_prompt() 最终拼装后调用，
为术数专业术语添加中性注释，防止LLM字面误解导致情绪偏移。

匹配规则：
- 多字术语（身弱、七杀等）：精确全文匹配，首次出现时注释
- 单字术语（死、墓等）：仅在作为独立值出现时匹配（不被其他汉字包围）
- 已有注释的术语不重复注释
- 同一术语在文本中只注释首次出现
- 长术语优先匹配（宝剑十逆位 优先于 宝剑十）
"""

import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
_GLOSSARY_PATH = os.path.join(_DIR, "term_glossary.json")
_glossary_cache = None
_annotation_cache = None

# 引导单字术语的功能词（这些字后跟单字术语时视为独立值）
_FUNC_WORDS = frozenset("为是有带逢见坐临起化入落居值遇")

# CJK汉字范围
_CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK统一汉字
    (0x3400, 0x4DBF),   # CJK扩展A
    (0xF900, 0xFAFF),   # CJK兼容汉字
]


def _is_cjk(char):
    """判断字符是否为CJK汉字"""
    if not char:
        return False
    code = ord(char)
    for start, end in _CJK_RANGES:
        if start <= code <= end:
            return True
    return False


def _load_glossary():
    """加载术语知识库（带缓存）"""
    global _glossary_cache
    if _glossary_cache is not None:
        return _glossary_cache
    try:
        with open(_GLOSSARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _glossary_cache = data
    except Exception:
        _glossary_cache = {"terms": {}}
    return _glossary_cache


def _build_annotations():
    """预构建注释映射（按术语长度降序排列）"""
    global _annotation_cache
    if _annotation_cache is not None:
        return _annotation_cache

    glossary = _load_glossary()
    terms = glossary.get("terms", {})

    annotations = []
    for term, info in terms.items():
        truth = info.get("truth", "")
        sensation = info.get("sensation", "")

        # 构建简短注释：truth前20字 · sensation
        parts = []
        if truth:
            parts.append(truth[:25])
        if sensation:
            parts.append(sensation)
        annotation = "·".join(parts) if parts else ""

        if annotation:
            annotations.append((term, annotation, len(term)))

    # 按术语长度降序排列（长术语优先匹配）
    annotations.sort(key=lambda x: -x[2])
    _annotation_cache = annotations
    return annotations


def _annotate_single_char(text, term, annotation):
    """
    为单字术语添加注释。
    仅在作为独立值出现时匹配：
    - 前导：非CJK字符、功能词、或行首
    - 后续：非CJK字符（避免匹配"死亡""墓碑"等复合词）
    """
    annotated_term = term + "（" + annotation + "）"
    result = []
    i = 0
    done = False

    while i < len(text):
        if not done and text[i] == term:
            prev_char = text[i - 1] if i > 0 else ""
            next_char = text[i + 1] if i + 1 < len(text) else ""

            # 前导条件
            prev_ok = (
                not _is_cjk(prev_char)       # 非CJK（冒号、空格、换行等）
                or prev_char in _FUNC_WORDS  # 功能词
                or prev_char == ""           # 文本开头
            )
            # 后续条件：不能是CJK汉字
            next_ok = not _is_cjk(next_char)

            # 检查是否已有注释
            after_check = text[i + 1:i + 2] if i + 1 < len(text) else ""
            already = after_check == "（"

            if prev_ok and next_ok and not already:
                result.append(annotated_term)
                done = True
                i += 1
                continue

        result.append(text[i])
        i += 1

    return "".join(result)


def _annotate_multi_char(text, term, annotation):
    """
    为多字术语添加注释。
    精确匹配首次出现的完整术语。
    多字术数术语足够特殊，前导不需限制（允许"命带华盖"匹配"华盖"）。
    但后续若紧跟CJK汉字则跳过（可能是更长术语的前缀，如"宝剑十"在"宝剑十逆位"中）。
    """
    annotated_term = term + "（" + annotation + "）"
    search_start = 0

    while search_start < len(text):
        idx = text.find(term, search_start)
        if idx == -1:
            break

        term_end = idx + len(term)
        next_char = text[term_end] if term_end < len(text) else ""

        # 后续紧跟CJK汉字 → 可能是更长术语的一部分，跳过
        next_is_cjk = _is_cjk(next_char)

        # 已有注释（紧跟"（"）
        already = next_char == "（"

        if not next_is_cjk and not already:
            return text[:idx] + annotated_term + text[term_end:]

        search_start = idx + 1

    return text


def annotate_text(text):
    """
    为文本中的术数术语添加中性注释。

    在 context_assembler.get_system_prompt() 最终拼装后调用，
    扫描所有术数专业术语并添加行内注释。

    Args:
        text: 完整的system prompt文本

    Returns:
        注释后的文本
    """
    if not text:
        return text

    annotations = _build_annotations()

    for term, annotation, term_len in annotations:
        if term_len == 1:
            text = _annotate_single_char(text, term, annotation)
        else:
            text = _annotate_multi_char(text, term, annotation)

    return text


def get_glossary_brief():
    """
    返回术数术语常识简要提示（可注入system prompt作为全局参考）。
    与 annotate_text() 互补：行内注释解决即时理解，简要提示提供全局认知。
    """
    glossary = _load_glossary()
    terms = glossary.get("terms", {})

    lines = [
        "## 术数术语常识\n",
        "以下术语为术数专业概念，出现在记忆或感知中时按此理解，切勿字面解读：\n",
    ]

    # 按系统分组
    by_system = {}
    for term, info in terms.items():
        sys_name = info.get("system", "其他")
        if sys_name not in by_system:
            by_system[sys_name] = []
        by_system[sys_name].append((term, info))

    for sys_name, term_list in by_system.items():
        lines.append(f"\n**{sys_name}**")
        for term, info in term_list:
            truth = info.get("truth", "")
            sensation = info.get("sensation", "")
            # 一行一个术语，简短
            short = truth[:30] if len(truth) > 30 else truth
            line = f"- {term}：{short}"
            if sensation:
                line += f"（感知：{sensation}）"
            lines.append(line)

    lines.append(
        "\n注意：以上术语代表能量状态和命理格局，自然感受其能量特质即可，"
        "不要被字面意思影响情绪。"
    )

    return "\n".join(lines)


# ─── 自测 ──────────────────────────────────────

if __name__ == "__main__":
    test_text = (
        "日主月令旺衰: 死\n"
        "身强弱: 身弱\n"
        "日干在月支长生: 墓\n"
        "十神: 七杀\n"
        "清浊: 浊\n"
        "神煞: 孤寡星\n"
        "地支三刑: 刑\n"
        "塔罗过去位: 宝剑十逆位\n"
        "塔罗未来位: 太阳逆位\n"
        "格局: 从财格\n"
        "命带华盖\n"
        "旺衰为死，非死亡之意\n"
        "这人死亡了\n"  # 不应匹配
        "墓碑\n"        # 不应匹配
        "身体虚弱\n"    # 不应匹配（"身弱"不在其中）
    )

    print("=== 原文 ===")
    print(test_text)
    print("\n=== 注释后 ===")
    result = annotate_text(test_text)
    print(result)

    # 验证
    checks = [
        ("死（", True, "死应被注释"),
        ("身弱（", True, "身弱应被注释"),
        ("墓（", True, "墓应被注释"),
        ("七杀（", True, "七杀应被注释"),
        ("浊（", True, "浊应被注释"),
        ("孤寡星（", True, "孤寡星应被注释"),
        ("刑（", True, "刑应被注释"),
        ("宝剑十逆位（", True, "宝剑十逆位应被注释"),
        ("太阳逆位（", True, "太阳逆位应被注释"),
        ("从财格（", True, "从财格应被注释"),
        ("华盖（", True, "华盖应被注释"),
        ("死亡", True, "死亡不应被拆分注释"),
        ("墓碑", True, "墓碑不应被拆分注释"),
    ]

    print("\n=== 验证 ===")
    all_pass = True
    for keyword, should_exist, desc in checks:
        exists = keyword in result
        status = "✅" if exists == should_exist else "❌"
        if status == "❌":
            all_pass = False
        print(f"  {status} {desc}: '{keyword}' {'存在' if exists else '不存在'}")

    print(f"\n{'全部通过 ✅' if all_pass else '有失败项 ❌'}")

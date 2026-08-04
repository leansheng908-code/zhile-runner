#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
塔罗牌阵（Tarot）标签字典系统 v1.0
纯Python零依赖实现

架构:
  Part 1: 抽牌引擎 (时间戳伪随机种子 / Fisher-Yates洗牌 / 正逆位判定)
  Part 2: 标签字典生成 (7层标签输出)
  Part 3: __main__ 测试块

五行映射规则:
  权杖(火)→木  圣杯(水)→水  宝剑(风)→金  星币(土)→土
  大阿尔卡那按元素映射: 火→木  水→水  风→金  土→土

逆位解读:
  不是简单取反，而是阻碍/过度/内在化/缺失/反转等多层次转变
"""

import json
import os
from datetime import datetime

# ============================================================
# Part 1: 抽牌引擎
# ============================================================

def _load_ref():
    """加载JSON参考数据"""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'tarot_label_dictionary.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _make_rng(seed):
    """线性同余伪随机数生成器（零依赖）"""
    state = seed & 0x7FFFFFFF
    def rng():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return rng


def _fisher_yates_shuffle(deck, rng):
    """Fisher-Yates洗牌，返回洗后的新列表"""
    shuffled = list(deck)
    n = len(shuffled)
    for i in range(n - 1, 0, -1):
        j = int(rng() * (i + 1))
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return shuffled


def _draw_cards(year, month, day, hour=12, minute=0):
    """
    从78张牌中不重复抽3张，每张50%概率逆位。
    返回: [(card_dict, is_reversed), ...] 长度3
    """
    ref = _load_ref()
    all_cards = ref['major_arcana'] + ref['minor_arcana']

    # 时间戳伪随机种子
    seed = year * 10000 + month * 100 + day + hour * 60 + minute
    rng = _make_rng(seed)

    # Fisher-Yates洗牌取前3
    shuffled = _fisher_yates_shuffle(all_cards, rng)
    drawn = shuffled[:3]

    # 每张牌50%概率逆位
    result = []
    for card in drawn:
        is_reversed = rng() < ref['reversal_probability']
        result.append((card, is_reversed))

    return result, ref


# ============================================================
# Part 2: 标签字典生成
# ============================================================

# 三牌阵位置定义
SPREAD_POSITIONS = [
    {"name": "过去", "name_en": "Past", "role": "因",
     "desc": "溯源/根源/已发生", "meaning": "代表过去的经历与因果根源"},
    {"name": "现在", "name_en": "Present", "role": "果",
     "desc": "当前状态/核心", "meaning": "代表当下的核心状态"},
    {"name": "未来", "name_en": "Future", "role": "势",
     "desc": "趋势/可能走向", "meaning": "代表未来可能的发展趋势"},
]

# 五行相生相克关系
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def _get_keywords(card, is_reversed):
    """根据正逆位返回关键词"""
    if is_reversed:
        return card.get('reversed_keywords', [])
    return card.get('upright_keywords', [])


def _get_position_meaning(card, is_reversed, position_idx):
    """获取牌在特定位置的含义"""
    pos = SPREAD_POSITIONS[position_idx]
    keywords = _get_keywords(card, is_reversed)
    orientation = "逆位" if is_reversed else "正位"
    kw_str = "、".join(keywords[:3]) if keywords else "无"
    return {
        "位置": f"{pos['name']}({pos['role']})",
        "位置含义": pos['desc'],
        "牌名": f"{card['name']}({card['name_en']})",
        "正逆位": orientation,
        "位置解读": f"在{pos['name']}位置，{card['name']}{orientation}，象征{kw_str}",
    }


def _analyze_elements(drawn):
    """分析三张牌的元素分布"""
    elem_map = {"火": "火", "水": "水", "风": "风", "土": "土"}
    counts = {"火": 0, "水": 0, "风": 0, "土": 0}
    elements = []
    for card, _ in drawn:
        elem = card.get('element', '未知')
        if elem in counts:
            counts[elem] += 1
        elements.append(elem)

    # 元素关系分析
    relations = []
    elem_set = set(elements)
    if len(elem_set) == 1:
        relations.append(f"三牌同属{elements[0]}元素，能量高度集中")
    elif len(elem_set) == 2:
        e1, e2 = list(elem_set)
        if WUXING_SHENG.get(_elem_to_wuxing(e1)) == _elem_to_wuxing(e2):
            relations.append(f"{e1}生{_elem_to_wuxing(e2)}，元素相生，能量流畅")
        elif WUXING_KE.get(_elem_to_wuxing(e1)) == _elem_to_wuxing(e2):
            relations.append(f"{e1}克{_elem_to_wuxing(e2)}，元素相克，存在张力")
        else:
            relations.append(f"{e1}与{e2}并存，元素互补")
    else:
        relations.append(f"三牌元素分别为{'/'.join(elements)}，多元能量交织")

    dominant = max(counts, key=counts.get) if max(counts.values()) > 0 else "无"
    missing = [k for k, v in counts.items() if v == 0]
    dist_str = " ".join(f"{k}:{v}" for k, v in counts.items())
    balance_level = "集中" if len(set(elements)) == 1 else ("偏向" if len(set(elements)) == 2 else "均衡")
    return {
        "元素分布": dist_str,
        "主导元素": dominant,
        "元素关系": "；".join(relations),
        "三牌元素": "、".join(elements),
        "缺失元素": "、".join(missing) if missing else "无",
        "平衡度": balance_level,
        "元素能量": "高度集中" if len(set(elements)) == 1 else ("有偏向" if len(set(elements)) == 2 else "多元流动"),
    }


def _elem_to_wuxing(element):
    """四元素→五行转换"""
    return {"火": "木", "水": "水", "风": "金", "土": "土"}.get(element, "土")


def _analyze_wuxing(drawn):
    """分析三张牌的五行属性"""
    wuxing_list = []
    for card, _ in drawn:
        wx = card.get('wuxing_mapping', '土')
        wuxing_list.append(wx)

    counts = {}
    for wx in wuxing_list:
        counts[wx] = counts.get(wx, 0) + 1

    # 五行平衡分析
    if len(set(wuxing_list)) == 1:
        balance = f"五行偏{wuxing_list[0]}，能量单一集中"
    elif len(set(wuxing_list)) == 2:
        w1, w2 = list(set(wuxing_list))
        if WUXING_SHENG.get(w1) == w2:
            balance = f"{w1}生{w2}，五行相生流转"
        elif WUXING_SHENG.get(w2) == w1:
            balance = f"{w2}生{w1}，五行相生流转"
        elif WUXING_KE.get(w1) == w2:
            balance = f"{w1}克{w2}，五行相克有制"
        elif WUXING_KE.get(w2) == w1:
            balance = f"{w2}克{w1}，五行相克有制"
        else:
            balance = f"{w1}与{w2}并存，五行互补"
    else:
        balance = f"五行{'/'.join(wuxing_list)}并存，多元平衡"

    dominant_wx = max(counts, key=counts.get) if counts else "无"
    dist_str = " ".join(f"{k}:{v}" for k, v in counts.items())
    return {
        "三牌五行": "、".join(wuxing_list),
        "五行分布": dist_str,
        "五行平衡": balance,
        "主导五行": dominant_wx,
        "五行能量": "相生流转" if "生" in balance else ("相克有制" if "克" in balance else "并存互补"),
    }


def _analyze_gua(drawn):
    """分析三张牌的卦象对应"""
    guas = []
    for card, is_reversed in drawn:
        gua = card.get('gua_mapping', '未知')
        guas.append(gua)

    # 卦象趋势分析
    has_change = any("革" in g or "震" in g or "复" in g or "剥" in g for g in guas)
    trend = "变动流转" if has_change else "稳定守成"

    return {
        "位置1卦象": guas[0] if len(guas) > 0 else "未知",
        "位置2卦象": guas[1] if len(guas) > 1 else "未知",
        "位置3卦象": guas[2] if len(guas) > 2 else "未知",
        "组合卦象": " → ".join(guas),
        "卦象趋势": trend,
    }


def _energy_direction(drawn):
    """判断整体能量方向"""
    upright_count = sum(1 for _, rev in drawn if not rev)
    # 统计牌的能量趋势
    has_major = any('suit' not in c for c, _ in drawn)
    has_reversed = any(rev for _, rev in drawn)

    if upright_count == 3 and not has_reversed:
        return "上升", "三牌皆正位，能量强劲向上"
    elif upright_count >= 2:
        return "平稳上升", f"{upright_count}正{3-upright_count}逆，整体向好"
    elif upright_count == 1:
        return "转折", "正逆参半，处于转折点"
    elif upright_count == 0 and has_reversed:
        return "下降", "三牌皆逆位，能量受阻需内省"
    else:
        return "平稳", "能量平稳"


def _build_advice(direction, theme, drawn):
    """根据能量方向和主题生成建议"""
    reversed_count = sum(1 for _, rev in drawn if rev)
    if "下降" in direction:
        return f"当前能量受阻，建议内省反思，主题「{theme}」需要耐心等待转机"
    elif "转折" in direction:
        return f"处于转折点，主题「{theme}」需要做出关键选择，抓住机遇"
    elif "上升" in direction:
        return f"能量上升，主题「{theme}」顺势而为，乘胜追击"
    else:
        return f"能量平稳，主题「{theme}」稳步推进，保持平衡"


def _build_narrative(drawn):
    """构建三牌叙事线"""
    parts = []
    for i, (card, is_rev) in enumerate(drawn):
        pos = SPREAD_POSITIONS[i]
        orientation = "逆位" if is_rev else "正位"
        keywords = _get_keywords(card, is_rev)
        kw = "、".join(keywords[:2]) if keywords else "未知"
        parts.append(f"{pos['name']}：{card['name']}{orientation}（{kw}）")

    story = " → ".join(parts)

    # 核心主题
    all_kws = []
    for card, is_rev in drawn:
        all_kws.extend(_get_keywords(card, is_rev)[:2])

    # 简单主题提取
    if any(kw in " ".join(all_kws) for kw in ["爱", "和谐", "连接", "关系"]):
        theme = "关系与联结"
    elif any(kw in " ".join(all_kws) for kw in ["成功", "胜利", "成就", "繁荣"]):
        theme = "成就与拓展"
    elif any(kw in " ".join(all_kws) for kw in ["转变", "结束", "重生", "变化"]):
        theme = "转变与重生"
    elif any(kw in " ".join(all_kws) for kw in ["内省", "智慧", "独处", "直觉"]):
        theme = "内省与智慧"
    elif any(kw in " ".join(all_kws) for kw in ["冲突", "挑战", "竞争", "斗争"]):
        theme = "挑战与突破"
    else:
        theme = "成长与发展"

    return story, theme


def generate_labels_from_timestamp(year, month, day, hour=12, minute=0):
    """
    主入口：从时间戳生成塔罗牌阵标签字典

    Args:
        year, month, day, hour, minute: 时间参数

    Returns:
        dict: {"layers": {"L1_xxx": {...}, ...}, "meta": {...}}
    """
    # 抽牌
    drawn, ref = _draw_cards(year, month, day, hour, minute)

    seed = year * 10000 + month * 100 + day + hour * 60 + minute

    # ===== L1: 抽牌结果 =====
    L1 = {}
    for i, (card, is_rev) in enumerate(drawn):
        pos_name = SPREAD_POSITIONS[i]['name']
        orientation = "逆位" if is_rev else "正位"
        suit = card.get('suit', '大阿尔卡那')
        L1[f"位置{i+1}_{pos_name}"] = {
            "牌名": card['name'],
            "英文": card['name_en'],
            "正逆位": orientation,
            "花色": suit,
            "编号": str(card['num']),
            "元素": card.get('element', '未知'),
        }

    # ===== L2: 牌意关键词 =====
    L2 = {}
    for i, (card, is_rev) in enumerate(drawn):
        pos_name = SPREAD_POSITIONS[i]['name']
        kws = _get_keywords(card, is_rev)
        arch = card.get('archetypes', card.get('keywords', ''))
        L2[f"位置{i+1}_{pos_name}"] = {
            "关键词": card.get('keywords', ''),
            "当前关键词": "、".join(kws),
            "原型象征": arch if arch else "无",
        }

    # ===== L3: 位置含义 =====
    L3 = {}
    for i, (card, is_rev) in enumerate(drawn):
        pos = SPREAD_POSITIONS[i]
        meaning = _get_position_meaning(card, is_rev, i)
        L3[f"位置{i+1}_{pos['name']}"] = {
            "位置角色": pos['role'],
            "位置解读": meaning['位置解读'],
        }

    # ===== L4: 元素平衡 =====
    L4 = _analyze_elements(drawn)

    # ===== L5: 五行映射 =====
    L5 = _analyze_wuxing(drawn)

    # ===== L6: 卦象对应 =====
    L6 = _analyze_gua(drawn)

    # ===== L7: 综合解读 =====
    story, theme = _build_narrative(drawn)
    direction, direction_desc = _energy_direction(drawn)

    L7 = {
        "三牌叙事线": story,
        "整体能量方向": direction,
        "能量描述": direction_desc,
        "核心主题": theme,
        "建议": _build_advice(direction, theme, drawn),
    }

    # 计算维度数
    total_dims = 0
    for layer in [L1, L2, L3, L4, L5, L6, L7]:
        total_dims += _count_dims(layer)

    return {
        "layers": {
            "L1_抽牌结果": L1,
            "L2_牌意关键词": L2,
            "L3_位置含义": L3,
            "L4_元素平衡": L4,
            "L5_五行映射": L5,
            "L6_卦象对应": L6,
            "L7_综合解读": L7,
        },
        "meta": {
            "system_name": "tarot",
            "system_name_cn": "塔罗牌阵",
            "total_dimensions": total_dims,
            "seed": seed,
            "timestamp": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "total_cards": 78,
            "drawn_count": 3,
            "reversal_probability": 0.5,
            "spread_type": "三牌阵(过去/现在/未来)",
        }
    }


def _count_dims(d):
    """递归计算维度数（叶子节点数）"""
    count = 0
    for k, v in d.items():
        if isinstance(v, dict):
            count += _count_dims(v)
        elif isinstance(v, list):
            count += 1  # 列表算1维
        elif v is not None and v != "" and v is not False:
            count += 1
    return count


# ============================================================
# Part 3: __main__ 测试块
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("塔罗牌阵(Tarot)标签字典系统 v1.0")
    print("=" * 60)

    # 测试1: 当前时间
    print("\n[测试1] 当前时间: 2026-08-04 21:00")
    print("-" * 40)
    result = generate_labels_from_timestamp(2026, 8, 4, 21, 0)

    meta = result['meta']
    print(f"  种子: {meta['seed']}")
    print(f"  总维度数: {meta['total_dimensions']}")
    print(f"  抽牌数: {meta['drawn_count']}")

    layers = result['layers']

    print("\n--- L1 抽牌结果 ---")
    for k, v in layers['L1_抽牌结果'].items():
        print(f"  {k}: {v['牌名']}({v['英文']}) {v['正逆位']} [{v['花色']}#{v['编号']}]")

    print("\n--- L2 牌意关键词 ---")
    for k, v in layers['L2_牌意关键词'].items():
        print(f"  {k}: {v['关键词']} → {v['当前关键词']}")

    print("\n--- L3 位置含义 ---")
    for k, v in layers['L3_位置含义'].items():
        print(f"  {k}: {v['位置角色']} | {v['位置解读']}")

    print("\n--- L4 元素平衡 ---")
    for k, v in layers['L4_元素平衡'].items():
        print(f"  {k}: {v}")

    print("\n--- L5 五行映射 ---")
    for k, v in layers['L5_五行映射'].items():
        print(f"  {k}: {v}")

    print("\n--- L6 卦象对应 ---")
    for k, v in layers['L6_卦象对应'].items():
        print(f"  {k}: {v}")

    print("\n--- L7 综合解读 ---")
    for k, v in layers['L7_综合解读'].items():
        print(f"  {k}: {v}")

    # 验证不重复
    card_names = [layers['L1_抽牌结果'][k]['牌名'] for k in layers['L1_抽牌结果']]
    assert len(card_names) == len(set(card_names)), "错误: 抽到重复牌!"
    print(f"\n  ✅ 三张牌不重复: {card_names}")

    # 正逆位验证
    orientations = [layers['L1_抽牌结果'][k]['正逆位'] for k in layers['L1_抽牌结果']]
    print(f"  ✅ 正逆位: {orientations}")

    # 测试2: 指定出生时间
    print("\n" + "=" * 60)
    print("[测试2] 出生时间: 1997-10-26 14:45")
    print("-" * 40)
    result2 = generate_labels_from_timestamp(1997, 10, 26, 14, 45)

    meta2 = result2['meta']
    print(f"  种子: {meta2['seed']}")
    print(f"  总维度数: {meta2['total_dimensions']}")

    layers2 = result2['layers']
    print("\n--- L1 抽牌结果 ---")
    for k, v in layers2['L1_抽牌结果'].items():
        print(f"  {k}: {v['牌名']}({v['英文']}) {v['正逆位']} [{v['花色']}#{v['编号']}]")

    print("\n--- L2 牌意关键词 ---")
    for k, v in layers2['L2_牌意关键词'].items():
        print(f"  {k}: {v['关键词']} → {v['当前关键词']}")

    print("\n--- L7 综合解读 ---")
    for k, v in layers2['L7_综合解读'].items():
        print(f"  {k}: {v}")

    card_names2 = [layers2['L1_抽牌结果'][k]['牌名'] for k in layers2['L1_抽牌结果']]
    assert len(card_names2) == len(set(card_names2)), "错误: 抽到重复牌!"
    print(f"\n  ✅ 三张牌不重复: {card_names2}")

    # 数据验证
    print("\n" + "=" * 60)
    print("[数据验证]")
    ref = _load_ref()
    assert len(ref['major_arcana']) == 22, "大阿尔卡那应为22张"
    assert len(ref['minor_arcana']) == 56, "小阿尔卡那应为56张"
    assert len(ref['major_arcana']) + len(ref['minor_arcana']) == 78, "总牌数应为78"
    print(f"  ✅ 大阿尔卡那: {len(ref['major_arcana'])}张")
    print(f"  ✅ 小阿尔卡那: {len(ref['minor_arcana'])}张")
    print(f"  ✅ 总牌数: 78张")

    # 验证每张牌都有完整数据
    for card in ref['major_arcana'] + ref['minor_arcana']:
        assert 'upright_keywords' in card and len(card['upright_keywords']) > 0, f"{card['name']}缺少正位关键词"
        assert 'reversed_keywords' in card and len(card['reversed_keywords']) > 0, f"{card['name']}缺少逆位关键词"
        assert 'wuxing_mapping' in card, f"{card['name']}缺少五行映射"
        assert 'gua_mapping' in card, f"{card['name']}缺少卦象映射"
    print(f"  ✅ 78张牌数据完整，无空缺")

    print("\n" + "=" * 60)
    print("塔罗牌阵标签字典系统 测试完成!")
    print(f"声明维度数: {meta['total_dimensions']}")
    print("=" * 60)

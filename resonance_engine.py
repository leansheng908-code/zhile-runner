#!/usr/bin/env python3
"""
多策略共振权重引擎 (Multi-Strategy Resonance Engine)
=====================================================
替代旧版「五行共振一刀切」方案，为13个术数系统各设计专属共振函数。

核心接口：
  engine = ResonanceEngine()
  score = engine.calculate(labels_a, labels_b)  # 1.0=中性 >1.0=共振 <1.0=冲突

共振规则总表：
  - 五行: 相同1.5 / 相生1.3 / 相克0.7 / 无关1.0
  - 卦象: 同卦1.5 / 互卦1.3 / 变卦1.3 / 错卦1.1 / 综卦1.1
  - 十神: 同类1.3 / 相生1.2 / 相克0.8
  - 刑冲合害: 三合1.5 / 六合1.4 / 六冲0.6 / 三刑0.6 / 相害0.7
  - 格局: 同格局1.5 / 关联1.3 / 对立0.7
  - 宫位: 三合1.4 / 对宫1.2 / 相邻1.1
  - 八门: 同门1.5 / 相生1.3 / 相克0.7
  - 九星: 同星1.3 / 旺相1.2 / 休囚0.8
  - 天将: 同将1.3 / 相生1.2 / 相克0.8
  - 课体: 同课1.4 / 关联1.2
  - 十六神: 同神1.3 / 相邻1.1 / 对立0.7
  - 建除: 同神1.3 / 相生1.2 / 相克0.8
  - 二十八宿: 同宿1.3 / 相邻1.1 / 对立0.7
  - 脏腑: 同1.5 / 表里1.4 / 相生1.3 / 相克0.7
  - 子午流注: 同时辰1.4 / 相邻1.1 / 对立0.7
  - 行星(印度): 同1.5 / 友好1.3 / 敌对0.7
  - 星座: 同1.4 / 三合1.3 / 对宫1.2
  - 大运: 同主星1.5
  - 塔罗: 同牌1.5 / 相邻编号1.2 / 对立0.7 / 同花色1.3
  - 经济周期: 同段1.5 / 相邻段1.3 / 对立段0.7 / 同阶段1.3

设计原则：
  - 命是倾向不是笼子：共振分数只是权重，不阻止任何记忆被检索
  - 每个系统独立计分，最后加权平均
  - 缺少数据的系统跳过（不计入加权）
  - 单系统分数封顶2.0，防止某个系统过度主导
"""

import json
from typing import Dict, Any, Optional


# ═══════════════════════════════════════════════
#  五行关系表
# ═══════════════════════════════════════════════

_WUXING = ["金", "木", "水", "火", "土"]

# 相生: 金生水, 水生木, 木生火, 火生土, 土生金
_SHENG = {("金", "水"), ("水", "木"), ("木", "火"), ("火", "土"), ("土", "金")}

# 相克: 金克木, 木克土, 土克水, 水克火, 火克金
_KE = {("金", "木"), ("木", "土"), ("土", "水"), ("水", "火"), ("火", "金")}

# 天干→五行
_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 地支→五行
_ZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 地支六合
_LIUHE = {("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未")}

# 地支三合
_SANHE = [
    {"申", "子", "辰"},  # 水局
    {"亥", "卯", "未"},  # 木局
    {"寅", "午", "戌"},  # 火局
    {"巳", "酉", "丑"},  # 金局
]

# 地支六冲
_LIUCHONG = {("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥")}

# 地支三刑
_SANXING = [
    {"寅", "巳", "申"},
    {"丑", "戌", "未"},
    {"子", "卯"},
]

# 地支相害
_XIANGHAI = {("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"), ("申", "亥"), ("酉", "戌")}


def _wuxing_score(a: str, b: str) -> float:
    """五行共振分数"""
    if not a or not b:
        return 1.0
    if a == b:
        return 1.5
    if (a, b) in _SHENG or (b, a) in _SHENG:
        return 1.3
    if (a, b) in _KE or (b, a) in _KE:
        return 0.7
    return 1.0


def _branch_relation(a: str, b: str) -> float:
    """地支关系分数"""
    if not a or not b:
        return 1.0
    if a == b:
        return 1.3
    pair = (a, b) if (a, b) in _LIUHE else (b, a)
    if (a, b) in _LIUHE or (b, a) in _LIUHE:
        return 1.4
    for sanhe in _SANHE:
        if a in sanhe and b in sanhe:
            return 1.5
    if (a, b) in _LIUCHONG or (b, a) in _LIUCHONG:
        return 0.6
    for sanxing in _SANXING:
        if a in sanxing and b in sanxing:
            return 0.6
    if (a, b) in _XIANGHAI or (b, a) in _XIANGHAI:
        return 0.7
    return 1.0


# ═══════════════════════════════════════════════
#  印度占星行星敌友关系
# ═══════════════════════════════════════════════

_PLANET_FRIENDS = {
    "Sun": {"Sun", "Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Moon", "Mars", "Jupiter"},
    "Mars": {"Sun", "Moon", "Mars", "Jupiter"},
    "Mercury": {"Mercury", "Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars", "Jupiter"},
    "Venus": {"Mercury", "Venus", "Saturn"},
    "Saturn": {"Mercury", "Venus", "Saturn"},
}

_PLANET_ENEMIES = {
    "Sun": {"Mercury", "Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury", "Venus"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon", "Mars"},
    "Saturn": {"Sun", "Moon", "Mars", "Jupiter"},
}


def _planet_score(a: str, b: str) -> float:
    """行星共振分数"""
    if not a or not b:
        return 1.0
    if a == b:
        return 1.5
    if b in _PLANET_FRIENDS.get(a, set()):
        return 1.3
    if b in _PLANET_ENEMIES.get(a, set()):
        return 0.7
    return 1.0


# ═══════════════════════════════════════════════
#  13个系统的专属共振函数
# ═══════════════════════════════════════════════

def _resonance_yi_jing(a: dict, b: dict) -> float:
    """易经：卦象关联 + 六亲（通过五行）"""
    score = 1.0
    hex_a = a.get("结构_本卦", "")
    hex_b = b.get("结构_本卦", "")
    if hex_a and hex_b:
        if hex_a == hex_b:
            score *= 1.5
        elif (a.get("结构_互卦", "") == hex_b or b.get("结构_互卦", "") == hex_a):
            score *= 1.3
        elif (a.get("结构_变卦", "") == hex_b or b.get("结构_变卦", "") == hex_a):
            score *= 1.3
        elif (a.get("结构_错卦", "") == hex_b or b.get("结构_错卦", "") == hex_a):
            score *= 1.1
        elif (a.get("结构_综卦", "") == hex_b or b.get("结构_综卦", "") == hex_a):
            score *= 1.1
    return min(score, 2.0)


def _resonance_bazi(a: dict, b: dict) -> float:
    """八字：日主五行 + 地支刑冲合害"""
    score = 1.0
    # 日主五行
    dm_a = a.get("day_master", "")
    dm_b = b.get("day_master", "")
    wx_a = _GAN_WUXING.get(dm_a, "")
    wx_b = _GAN_WUXING.get(dm_b, "")
    score *= _wuxing_score(wx_a, wx_b)
    # 日支关系
    labels_a = a.get("labels", {})
    labels_b = b.get("labels", {})
    dz_a = labels_a.get("L1_日柱地支", "")
    dz_b = labels_b.get("L1_日柱地支", "")
    if dz_a and dz_b:
        score *= _branch_relation(dz_a, dz_b)
    return min(score, 2.0)


def _resonance_ziwei(a: dict, b: dict) -> float:
    """紫微：主星格局关联 + 宫位三合 + 四化"""
    score = 1.0
    # 主星坐宫对比
    stars_a = a.get("L2_主星坐宫", {})
    stars_b = b.get("L2_主星坐宫", {})
    if stars_a and stars_b:
        common = set(stars_a.keys()) & set(stars_b.keys())
        same_pos = sum(1 for k in common if stars_a.get(k) == stars_b.get(k))
        if same_pos > 0:
            score *= 1.0 + min(same_pos * 0.1, 0.5)
        elif common:
            score *= 1.1
    # 四化对比
    sihua_a = a.get("L6_四化系统", {})
    sihua_b = b.get("L6_四化系统", {})
    hua_lu_a = sihua_a.get("化禄_星曜", "")
    hua_lu_b = sihua_b.get("化禄_星曜", "")
    if hua_lu_a and hua_lu_b:
        if hua_lu_a == hua_lu_b:
            score *= 1.3
        else:
            score *= 1.1
    return min(score, 2.0)


def _resonance_qimen(a: dict, b: dict) -> float:
    """奇门：八门生克 + 九星旺衰 + 八神"""
    score = 1.0
    # 八门五行
    for door_name in ["休门_五行", "生门_五行", "伤门_五行", "杜门_五行"]:
        wa = a.get("L7_八门完整属性", {}).get(door_name, "")
        wb = b.get("L7_八门完整属性", {}).get(door_name, "")
        if wa and wb:
            score *= _wuxing_score(wa, wb)
            break
    # 九星五行
    for star_name in ["天蓬_五行", "天芮_五行", "天冲_五行", "天辅_五行"]:
        wa = a.get("L5_九星完整属性", {}).get(star_name, "")
        wb = b.get("L5_九星完整属性", {}).get(star_name, "")
        if wa and wb:
            score *= _wuxing_score(wa, wb)
            break
    return min(score, 2.0)


def _resonance_liuren(a: dict, b: dict) -> float:
    """六壬：天将关系 + 课体格局 + 三传五行"""
    score = 1.0
    # 课体对比
    keti_a = a.get("L8_课体格局判断", {})
    keti_b = b.get("L8_课体格局判断", {})
    if keti_a and keti_b:
        active_a = {k for k, v in keti_a.items() if v and v != "否"}
        active_b = {k for k, v in keti_b.items() if v and v != "否"}
        if active_a & active_b:
            score *= 1.4
        elif active_a and active_b:
            score *= 1.1
    # 三传五行
    chuan_a = a.get("L4_三传", {})
    chuan_b = b.get("L4_三传", {})
    wx_a = chuan_a.get("初传_五行", "")
    wx_b = chuan_b.get("初传_五行", "")
    if wx_a and wx_b:
        score *= _wuxing_score(wx_a, wx_b)
    return min(score, 2.0)


def _resonance_taiyi(a: dict, b: dict) -> float:
    """太乙：太乙宫 + 主客算 + 十六神五行"""
    score = 1.0
    la = a.get("layers", {}).get("L1_基础排盘", {})
    lb = b.get("layers", {}).get("L1_基础排盘", {})
    # 太乙宫对比
    pa = la.get("太乙宫", "")
    pb = lb.get("太乙宫", "")
    if pa and pb:
        if pa == pb:
            score *= 1.3
        else:
            score *= 1.0
    # 主算/客算对比
    sa = la.get("主算", "")
    sb = lb.get("主算", "")
    if sa and sb:
        try:
            diff = abs(int(sa) - int(sb))
            if diff == 0:
                score *= 1.3
            elif diff <= 5:
                score *= 1.2
            elif diff >= 20:
                score *= 0.8
        except (ValueError, TypeError):
            pass
    # 阴阳遁对比
    ya = la.get("阴阳遁", "")
    yb = lb.get("阴阳遁", "")
    if ya and yb:
        if ya == yb:
            score *= 1.2
        else:
            score *= 0.8
    return min(score, 2.0)


def _resonance_tongsheng(a: dict, b: dict) -> float:
    """通胜：建除值日 + 二十八宿值日 + 黄黑道"""
    score = 1.0
    la = a.get("layers", {}).get("L1_基础排盘", {})
    lb = b.get("layers", {}).get("L1_基础排盘", {})
    # 建除值日
    sa = la.get("建除值日", "")
    sb = lb.get("建除值日", "")
    if sa and sb:
        if sa == sb:
            score *= 1.3
        else:
            score *= 1.0
    # 二十八宿值日
    xa = la.get("二十八宿值日", "")
    xb = lb.get("二十八宿值日", "")
    if xa and xb:
        if xa == xb:
            score *= 1.3
        else:
            score *= 1.0
    # 黄黑道
    ha = la.get("黄黑道", "")
    hb = lb.get("黄黑道", "")
    if ha and hb:
        if ha == hb:
            score *= 1.2
        else:
            score *= 1.0
    return min(score, 2.0)


def _resonance_zhongyi(a: dict, b: dict) -> float:
    """中医：当令经脉 + 五运 + 司天在泉"""
    score = 1.0
    la = a.get("layers", {}).get("L1_基础排盘", {})
    lb = b.get("layers", {}).get("L1_基础排盘", {})
    # 当令经脉
    ma = la.get("当令经脉", "")
    mb = lb.get("当令经脉", "")
    if ma and mb:
        if ma == mb:
            score *= 1.4
        elif _is_paired_meridian(ma, mb):
            score *= 1.3
        else:
            score *= 1.0
    # 五运
    ya = la.get("五运", "")
    yb = lb.get("五运", "")
    if ya and yb:
        # 提取五行（水运/木运/火运/金运/土运）
        for wx in _WUXING:
            if wx in ya and wx in yb:
                score *= 1.3
                break
            elif wx in ya or wx in yb:
                score *= 1.0
                break
    # 司天对比
    sa = la.get("司天", "")
    sb = lb.get("司天", "")
    if sa and sb:
        if sa == sb:
            score *= 1.2
    return min(score, 2.0)


# 脏腑表里对应
_PAIRED_ORGANS = {
    ("肺", "大肠"), ("心", "小肠"), ("脾", "胃"),
    ("肝", "胆"), ("肾", "膀胱"),
    ("心包", "三焦"),
}


def _is_paired_meridian(a: str, b: str) -> bool:
    """判断两条经络是否为表里关系"""
    for x, y in _PAIRED_ORGANS:
        if (a in x and b in y) or (a in y and b in x):
            return True
    return False


def _resonance_qita(a: dict, b: dict) -> float:
    """其他术数：小六壬时宫 + 年飞星"""
    score = 1.0
    la = a.get("layers", {}).get("L1_基础排盘", {})
    lb = b.get("layers", {}).get("L1_基础排盘", {})
    # 小六壬时宫
    sa = la.get("小六壬时宫", "")
    sb = lb.get("小六壬时宫", "")
    if sa and sb:
        if sa == sb:
            score *= 1.3
        else:
            score *= 1.0
    # 年飞星入中
    fa = la.get("年飞星入中", "")
    fb = lb.get("年飞星入中", "")
    if fa and fb:
        if fa == fb:
            score *= 1.3
    return min(score, 2.0)


def _resonance_canmou(a: dict, b: dict) -> float:
    """参考系统：塔罗三牌 + 跨文化对应"""
    score = 1.0
    # 塔罗三牌
    tl_a = a.get("L4_塔罗三牌", {})
    tl_b = b.get("L4_塔罗三牌", {})
    pa = tl_a.get("过去牌名", "")
    pb = tl_b.get("过去牌名", "")
    if pa and pb:
        if pa == pb:
            score *= 1.4
        else:
            score *= 1.0
    # 跨文化对应（五行映射）
    cc_a = a.get("L9_跨文化对应", {})
    cc_b = b.get("L9_跨文化对应", {})
    ea = cc_a.get("中国五行_西方塔罗", "")
    eb = cc_b.get("中国五行_西方塔罗", "")
    if ea and eb:
        score *= _wuxing_score(ea, eb)
    return min(score, 2.0)


def _resonance_jyotish(a: dict, b: dict) -> float:
    """印度占星：行星敌友 + 星座三合 + 大运"""
    score = 1.0
    # 行星位置对比（取月亮星座的行星关系）
    l1_a = a.get("L1_行星位置", {})
    l1_b = b.get("L1_行星位置", {})
    moon_a = l1_a.get("Moon_月亮", {})
    moon_b = l1_b.get("Moon_月亮", {})
    if isinstance(moon_a, dict) and isinstance(moon_b, dict):
        sa = moon_a.get("星座", "")
        sb = moon_b.get("星座", "")
        if sa and sb:
            if sa == sb:
                score *= 1.4
            elif _is_trine_sign(sa, sb):
                score *= 1.3
            elif _is_opposite_sign(sa, sb):
                score *= 1.2
    # 大运主星
    l4_a = a.get("L4_大运系统", {})
    l4_b = b.get("L4_大运系统", {})
    da = l4_a.get("当前大运(Mahadasha)", "")
    db = l4_b.get("当前大运(Mahadasha)", "")
    if da and db:
        # 提取行星名（去掉中文括号部分）
        pa = da.split("(")[0].strip() if "(" in da else da
        pb = db.split("(")[0].strip() if "(" in db else db
        if pa and pb:
            score *= _planet_score(pa, pb)
    return min(score, 2.0)


def _is_trine_sign(a: str, b: str) -> bool:
    """判断两个星座是否三合（火/土/风/水三方）"""
    # 火象: 白羊/狮子/射手, 土象: 金牛/处女/摩羯, 风象: 双子/天秤/水瓶, 水象: 巨蟹/天蝎/双鱼
    groups = [
        {"白羊", "狮子", "射手"},
        {"金牛", "处女", "摩羯"},
        {"双子", "天秤", "水瓶"},
        {"巨蟹", "天蝎", "双鱼"},
    ]
    for g in groups:
        if any(x in a for x in g) and any(x in b for x in g):
            return True
    return False


def _is_opposite_sign(a: str, b: str) -> bool:
    """判断两个星座是否对宫"""
    pairs = [
        ({"白羊"}, {"天秤"}),
        ({"金牛"}, {"天蝎"}),
        ({"双子"}, {"射手"}),
        ({"巨蟹"}, {"摩羯"}),
        ({"狮子"}, {"水瓶"}),
        ({"处女"}, {"双鱼"}),
    ]
    for g1, g2 in pairs:
        if (any(x in a for x in g1) and any(x in b for x in g2)) or \
           (any(x in a for x in g2) and any(x in b for x in g1)):
            return True
    return False


def _resonance_tarot(a: dict, b: dict) -> float:
    """塔罗：花色五行 + 大牌编号 + 正逆位"""
    score = 1.0
    # 花色→五行
    suit_wx = {"权杖": "木", "圣杯": "水", "宝剑": "金", "星币": "土"}
    cards_a = a.get("layers", {}).get("L1_抽牌结果", {})
    cards_b = b.get("layers", {}).get("L1_抽牌结果", {})
    # 取位置1（过去牌）做对比
    pos1_a = cards_a.get("位置1_过去", {})
    pos1_b = cards_b.get("位置1_过去", {})
    if isinstance(pos1_a, dict) and isinstance(pos1_b, dict):
        sa = pos1_a.get("花色", "")
        sb = pos1_b.get("花色", "")
        wa = suit_wx.get(sa, "")
        wb = suit_wx.get(sb, "")
        if wa and wb:
            score *= _wuxing_score(wa, wb)
        # 正逆位
        ra = pos1_a.get("正逆位", "")
        rb = pos1_b.get("正逆位", "")
        if ra and rb:
            if ra == rb:
                score *= 1.2
            else:
                score *= 0.9
        # 编号接近度
        na = pos1_a.get("编号", "")
        nb = pos1_b.get("编号", "")
        try:
            diff = abs(int(na) - int(nb))
            if diff == 0:
                score *= 1.5
            elif diff <= 2:
                score *= 1.2
            elif diff >= 20:
                score *= 0.7
        except (ValueError, TypeError):
            pass
    return min(score, 2.0)


def _resonance_economic_cycle(a: dict, b: dict) -> float:
    """经济周期：段类型共振 + 阶段接近度"""
    score = 1.0
    la = a.get("layers", {}).get("L1_周期定位", {})
    lb = b.get("layers", {}).get("L1_周期定位", {})
    seg_a = la.get("当前段类型", "")
    seg_b = lb.get("当前段类型", "")
    if seg_a and seg_b:
        if seg_a == seg_b:
            score *= 1.5
        elif _is_adjacent_segment(seg_a, seg_b):
            score *= 1.3
        elif _is_opposite_segment(seg_a, seg_b):
            score *= 0.7
    # 阶段接近度
    l5a = a.get("layers", {}).get("L5_投资窗口", {})
    l5b = b.get("layers", {}).get("L5_投资窗口", {})
    pa = l5a.get("窗口阶段", "")
    pb = l5b.get("窗口阶段", "")
    if pa and pb:
        if pa == pb:
            score *= 1.3
        else:
            score *= 1.0
    return min(score, 2.0)


_SEGMENTS = ["C→B", "B→A", "A→C", "B→C"]


def _is_adjacent_segment(a: str, b: str) -> bool:
    """判断两个段类型是否相邻（共享一个阶段）"""
    adjacent = {
        ("C→B", "B→A"), ("C→B", "B→C"),
        ("B→A", "A→C"), ("B→A", "B→C"),
        ("A→C", "C→B"),
        ("B→C", "C→B"), ("B→C", "B→A"),
    }
    return (a, b) in adjacent or (b, a) in adjacent


def _is_opposite_segment(a: str, b: str) -> bool:
    """判断两个段类型是否对立"""
    opposite = {
        ("C→B", "A→C"),  # 买入 vs 持币
        ("B→A", "B→C"),  # 卖出 vs 观望
    }
    return (a, b) in opposite or (b, a) in opposite


# ═══════════════════════════════════════════════
#  共振引擎主类
# ═══════════════════════════════════════════════

class ResonanceEngine:
    """多策略共振权重引擎

    用法：
        engine = ResonanceEngine()
        score = engine.calculate(labels_a, labels_b)
        # score: 1.0=中性, >1.0=共振, <1.0=冲突
    """

    # 系统共振函数注册表
    _STRATEGIES = {
        "yi_jing": _resonance_yi_jing,
        "bazi": _resonance_bazi,
        "ziwei": _resonance_ziwei,
        "qimen": _resonance_qimen,
        "liuren": _resonance_liuren,
        "taiyi": _resonance_taiyi,
        "tongsheng": _resonance_tongsheng,
        "zhongyi": _resonance_zhongyi,
        "qita": _resonance_qita,
        "canmou": _resonance_canmou,
        "jyotish": _resonance_jyotish,
        "tarot": _resonance_tarot,
        "economic_cycle": _resonance_economic_cycle,
    }

    # 系统权重（可调整，默认全1.0）
    _SYSTEM_WEIGHTS = {
        "yi_jing": 1.2,       # 卦象是核心，权重略高
        "bazi": 1.0,
        "ziwei": 1.0,
        "qimen": 0.8,
        "liuren": 0.8,
        "taiyi": 0.8,
        "tongsheng": 0.6,     # 通胜偏日常，权重略低
        "zhongyi": 0.6,
        "qita": 0.5,          # 其他术数权重最低
        "canmou": 0.5,        # 参考系统权重最低
        "jyotish": 1.0,
        "tarot": 0.8,
        "economic_cycle": 1.0, # 经济周期直接影响投资决策
    }

    def calculate(self, labels_a: Dict[str, Any], labels_b: Dict[str, Any]) -> float:
        """计算两个标签向量集的多策略共振分数

        参数：
            labels_a/b: dict, {system_name: raw_labels_dict}
                        来自 label_unifier.generate_unified_labels() 的 systems 展开结果

        返回：
            float: 共振分数, 1.0=中性, >1.0=共振, <1.0=冲突
        """
        total_score = 0.0
        total_weight = 0.0

        for sys_name, strategy in self._STRATEGIES.items():
            a = labels_a.get(sys_name, {})
            b = labels_b.get(sys_name, {})
            if not a or not b:
                continue  # 缺少数据的系统跳过

            try:
                score = strategy(a, b)
            except Exception:
                score = 1.0  # 出错时回退中性

            weight = self._SYSTEM_WEIGHTS.get(sys_name, 1.0)
            total_score += score * weight
            total_weight += weight

        return total_score / total_weight if total_weight > 0 else 1.0

    @staticmethod
    def extract_snapshot(raw_labels: Dict[str, Any]) -> Dict[str, Any]:
        """从 label_unifier 的原始输出中提取共振快照

        参数：
            raw_labels: label_unifier.generate_unified_labels() 的返回值

        返回：
            dict: {system_name: raw_labels_dict} 适合存储和共振计算
        """
        systems = raw_labels.get("systems", [])
        snapshot = {}
        for sys_data in systems:
            sid = sys_data.get("system_id", "")
            labels = sys_data.get("labels", {})
            # labels 可能是 list（normalized）或 dict（raw）
            # 共振函数需要 raw dict，所以从原始模块获取
            if isinstance(labels, list):
                # normalized 格式，跳过（共振函数需要 raw dict）
                continue
            if isinstance(labels, dict) and labels:
                snapshot[sid] = labels
        return snapshot

    @staticmethod
    def extract_compact_snapshot(raw_labels: Dict[str, Any]) -> Dict[str, Any]:
        """从各系统原始输出中提取共振快照（精简版，减少存储）

        参数：
            raw_labels: dict, {system_name: raw_labels_dict}
                        每个系统 generate_labels_from_timestamp() 的直接返回值

        返回：
            dict: 精简的 {system_name: {key: value}} 适合存储在记忆条目中
        """
        # 每个系统共振函数需要的关键字段路径
        # 对于flat结构：直接取key
        # 对于layers结构：取 layers.{sub_key}
        COMPACT_PATHS = {
            "yi_jing": [("", "结构_本卦"), ("", "结构_变卦"), ("", "结构_互卦"), ("", "结构_错卦"), ("", "结构_综卦")],
            "bazi": [("", "day_master"), ("", "labels")],
            "ziwei": [("", "L2_主星坐宫"), ("", "L6_四化系统")],
            "qimen": [("", "L5_九星完整属性"), ("", "L7_八门完整属性")],
            "liuren": [("", "L4_三传"), ("", "L8_课体格局判断")],
            "taiyi": [("layers", "L1_基础排盘")],
            "tongsheng": [("layers", "L1_基础排盘")],
            "zhongyi": [("layers", "L1_基础排盘")],
            "qita": [("layers", "L1_基础排盘")],
            "canmou": [("", "L4_塔罗三牌"), ("", "L9_跨文化对应")],
            "jyotish": [("", "L1_行星位置"), ("", "L4_大运系统")],
            "tarot": [("layers", "L1_抽牌结果")],
            "economic_cycle": [("layers", "L1_周期定位"), ("layers", "L5_投资窗口")],
        }

        snapshot = {}
        for sys_name, paths in COMPACT_PATHS.items():
            raw = raw_labels.get(sys_name)
            if not raw or not isinstance(raw, dict):
                continue
            compact = {}
            for parent_key, child_key in paths:
                if parent_key:
                    # nested under parent (e.g. "layers")
                    parent = raw.get(parent_key, {})
                    if isinstance(parent, dict) and child_key in parent:
                        compact[child_key] = parent[child_key]
                else:
                    # flat structure
                    if child_key in raw:
                        compact[child_key] = raw[child_key]
            if compact:
                snapshot[sys_name] = compact
        return snapshot

    @staticmethod
    def generate_snapshot(year: int, month: int, day: int, hour: int = 12,
                          minute: int = 0, gender: str = "male") -> Dict[str, Any]:
        """生成当前时间点的共振快照（直接调用各系统模块）

        参数：
            year/month/day/hour/minute: 时间戳
            gender: 性别（部分系统需要）

        返回：
            dict: {system_name: raw_labels_dict} 适合共振计算和存储
        """
        import sys as _sys
        import os as _os
        from datetime import datetime as _dt

        _BASE = _os.path.dirname(_os.path.abspath(__file__))
        dt = _dt(year, month, day, hour, minute)

        # 系统调用配置: (dir, module, func, call_type)
        _SYS_CFG = {
            "yi_jing": ("yi_jing", "yi_jing_label_dictionary", "generate_labels_from_timestamp", "dt"),
            "bazi": ("bazi", "bazi_label_dictionary", "generate_labels_from_timestamp", "dt"),
            "ziwei": ("ziwei", "ziwei_label_dictionary", "generate_labels_from_timestamp", "str"),
            "qimen": ("qimen", "qimen_label_dictionary", "generate_labels_from_timestamp", "args5"),
            "liuren": ("liuren", "liuren_label_dictionary", "generate_labels_from_timestamp", "args5"),
            "taiyi": ("taiyi", "taiyi_label_dictionary", "generate_labels_from_timestamp", "args4"),
            "tongsheng": ("tongsheng", "tongsheng_label_dictionary", "generate_labels_from_timestamp", "args4"),
            "zhongyi": ("zhongyi", "zhongyi_label_dictionary", "generate_labels_from_timestamp", "args4"),
            "qita": ("qita", "qita_label_dictionary", "generate_labels_from_timestamp", "args4"),
            "canmou": ("canmou", "canmou_label_dictionary", "generate_canmou_labels", "args4"),
            "jyotish": ("jyotish", "jyotish_label_dictionary", "generate_labels_from_timestamp", "args5"),
            "tarot": ("tarot", "tarot_label_dictionary", "generate_labels_from_timestamp", "args5"),
            "economic_cycle": ("economic_cycle", "economic_cycle_label_dictionary", "generate_labels_from_timestamp", "args5"),
        }

        raw_labels = {}
        for sys_name, (dir_name, module_name, func_name, call_type) in _SYS_CFG.items():
            sys_dir = _os.path.join(_BASE, dir_name)
            if sys_dir not in _sys.path:
                _sys.path.insert(0, sys_dir)
            try:
                mod = __import__(module_name)
                func = getattr(mod, func_name)
                if call_type == "dt":
                    raw_labels[sys_name] = func(dt)
                elif call_type == "str":
                    raw_labels[sys_name] = func(dt.strftime("%Y-%m-%d %H:%M"), gender=gender)
                elif call_type == "args5":
                    raw_labels[sys_name] = func(year, month, day, hour, minute)
                elif call_type == "args4":
                    raw_labels[sys_name] = func(year, month, day, hour)
            except Exception:
                pass  # 跳过失败的系统

        return raw_labels


# ═══════════════════════════════════════════════
#  测试
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    import time
    from datetime import datetime

    print("=" * 60)
    print("多策略共振引擎测试")
    print("=" * 60)

    engine = ResonanceEngine()

    # 用 generate_snapshot 生成两个时间点的标签
    print("\n--- 生成快照 ---")
    t0 = time.time()
    labels_a = engine.generate_snapshot(2026, 8, 4, 22, 0)
    t1 = time.time()
    print("  dt1 (2026-08-04 22:00) 系统数: " + str(len(labels_a)) + " 耗时: " + str(round((t1-t0)*1000, 1)) + "ms")

    t0 = time.time()
    labels_b = engine.generate_snapshot(2026, 8, 5, 8, 0)
    t1 = time.time()
    print("  dt2 (2026-08-05 08:00) 系统数: " + str(len(labels_b)) + " 耗时: " + str(round((t1-t0)*1000, 1)) + "ms")

    t0 = time.time()
    labels_c = engine.generate_snapshot(2027, 3, 15, 14, 0)
    t1 = time.time()
    print("  dt3 (2027-03-15 14:00) 系统数: " + str(len(labels_c)) + " 耗时: " + str(round((t1-t0)*1000, 1)) + "ms")

    print("\n--- 测试1: 同一天不同时间 (dt1 vs dt2) ---")
    score = engine.calculate(labels_a, labels_b)
    print("  共振分数: " + str(round(score, 3)))
    print("  (同日不同时辰，预期接近1.0~1.3)")

    print("\n--- 测试2: 不同月份 (dt1 vs dt3) ---")
    score2 = engine.calculate(labels_a, labels_c)
    print("  共振分数: " + str(round(score2, 3)))
    print("  (不同月份，预期偏离1.0)")

    print("\n--- 测试3: 自共振 (dt1 vs dt1) ---")
    score3 = engine.calculate(labels_a, labels_a)
    print("  共振分数: " + str(round(score3, 3)))
    print("  (完全相同，预期>1.0)")

    print("\n--- 测试4: 各系统独立分数 ---")
    for sys_name, strategy in ResonanceEngine._STRATEGIES.items():
        a = labels_a.get(sys_name, {})
        b = labels_b.get(sys_name, {})
        c = labels_c.get(sys_name, {})
        if a and b:
            try:
                s_same = strategy(a, b)
                s_diff = strategy(a, c) if c else 0
                if s_diff:
                    print("  " + sys_name + ": 同日=" + str(round(s_same, 2)) + " 跨月=" + str(round(s_diff, 2)))
                else:
                    print("  " + sys_name + ": 同日=" + str(round(s_same, 2)))
            except Exception as e:
                print("  " + sys_name + ": ERROR " + str(e)[:50])
        else:
            print("  " + sys_name + ": 无数据")

    print("\n--- 测试5: compact snapshot 大小 ---")
    compact = ResonanceEngine.extract_compact_snapshot(labels_a)
    compact_json = json.dumps(compact, ensure_ascii=False)
    print("  compact snapshot 大小: " + str(len(compact_json)) + " bytes")
    print("  系统数: " + str(len(compact)))
    # 验证compact snapshot也能用于共振计算
    score_compact = engine.calculate(compact, ResonanceEngine.extract_compact_snapshot(labels_b))
    print("  compact vs compact 共振分数: " + str(round(score_compact, 3)))

    print("\n--- 测试6: 性能 ---")
    t0 = time.time()
    for _ in range(100):
        engine.calculate(labels_a, labels_b)
    t1 = time.time()
    print("  100次共振计算耗时: " + str(round((t1 - t0) * 1000, 1)) + "ms")
    print("  单次平均: " + str(round((t1 - t0) * 10, 2)) + "ms")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

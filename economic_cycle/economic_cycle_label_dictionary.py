#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经济周期（Economic Cycle）标签字典系统 v1.0
纯Python零依赖实现

架构:
  Part 1: 周期计算引擎 — 三条固定循环数组（A恐慌/B繁荣/C艰难）
  Part 2: 段判断引擎 — 按时间排序所有节点，找到当前段类型/起止/进度
  Part 3: 三层标签生成（L1周期定位 + L5投资窗口 + L6历史对照）

周期定义:
  A恐慌：间隔[18,20,16]循环，54年大周期，起点1927
  B繁荣：间隔[9,10,8]循环，27年大周期，起点1926
  C艰难：间隔[7,11,9]循环，27年大周期，起点1924

段类型（4种）:
  C→B：艰难到繁荣，买入窗口
  B→A：繁荣到恐慌，卖出窗口
  A→C：恐慌到艰难，持币窗口
  B→C：繁荣中回调，观望窗口

L6成长机制:
  历史事件存储在 economic_cycle_history.json 中
  初始为人工种子数据，运行器可在新段完成时自动追加事件
  这是唯一一个会自己长大的标签层
"""

import json
import os

# ============================================================
# Part 1: 周期计算引擎
# ============================================================

_CYCLES = {
    'A': {'start': 1927, 'intervals': [18, 20, 16]},
    'B': {'start': 1926, 'intervals': [9, 10, 8]},
    'C': {'start': 1924, 'intervals': [7, 11, 9]},
}

# 同年多相位排序优先级：C < B < A
_PHASE_PRIORITY = {'C': 0, 'B': 1, 'A': 2}

_PHASE_CN = {'A': 'A恐慌', 'B': 'B繁荣', 'C': 'C艰难'}

_SEGMENT_TYPES = {
    ('C', 'B'): 'C→B',
    ('B', 'A'): 'B→A',
    ('A', 'C'): 'A→C',
    ('B', 'C'): 'B→C',
}

_WINDOW_TYPES = {
    'C→B': '买入',
    'B→A': '卖出',
    'A→C': '持币',
    'B→C': '观望',
}

_ACTION_MAP = {
    ('C→B', '早期'): '建仓',
    ('C→B', '中期'): '加仓',
    ('C→B', '晚期'): '持有',
    ('B→A', '早期'): '持有',
    ('B→A', '中期'): '减仓',
    ('B→A', '晚期'): '清仓',
    ('A→C', '早期'): '空仓',
    ('A→C', '中期'): '观望',
    ('A→C', '晚期'): '准备',
    ('B→C', '早期'): '持有',
    ('B→C', '中期'): '观望',
    ('B→C', '晚期'): '准备建仓',
}

_TYPE_TO_JSON_KEY = {
    'C→B': 'C_to_B',
    'B→A': 'B_to_A',
    'A→C': 'A_to_C',
    'B→C': 'B_to_C',
}


def _generate_cycle_years(phase, min_year=1800, max_year=2200):
    """生成某条循环的所有年份"""
    cfg = _CYCLES[phase]
    start = cfg['start']
    intervals = cfg['intervals']
    n = len(intervals)

    years = []

    # 向前生成
    year = start
    idx = 0
    while year <= max_year:
        years.append(year)
        year += intervals[idx % n]
        idx += 1

    # 向后生成
    rev_intervals = intervals[::-1]
    year = start
    idx = 0
    while year > min_year:
        year -= rev_intervals[idx % n]
        if year >= min_year:
            years.append(year)
        idx += 1

    return sorted(set(years))


def _generate_all_turning_points(min_year=1800, max_year=2200):
    """生成所有A/B/C转折点，按时间排序。同年按C<B<A排序。"""
    points = []
    for phase in ['A', 'B', 'C']:
        for y in _generate_cycle_years(phase, min_year, max_year):
            points.append((y, phase))
    points.sort(key=lambda x: (x[0], _PHASE_PRIORITY[x[1]]))
    return points


# ============================================================
# Part 2: 段判断引擎
# ============================================================

def _find_current_segment(year, points=None):
    """找到给定年份所在的段"""
    if points is None:
        points = _generate_all_turning_points()

    # 找到 <= year 的最后一个转折点
    past_idx = None
    for i, (y, _) in enumerate(points):
        if y <= year:
            past_idx = i
        else:
            break

    if past_idx is None or past_idx + 1 >= len(points):
        return None

    start_year, start_phase = points[past_idx]
    end_year, end_phase = points[past_idx + 1]

    seg_type = _SEGMENT_TYPES.get((start_phase, end_phase))
    if seg_type is None:
        return None

    # 下一段信息（用于 next_window）
    next_seg_type = None
    if past_idx + 2 < len(points):
        _, next_end_phase = points[past_idx + 2]
        next_seg_type = _SEGMENT_TYPES.get((end_phase, next_end_phase))

    return {
        'segment_type': seg_type,
        'start_year': start_year,
        'start_phase': start_phase,
        'end_year': end_year,
        'end_phase': end_phase,
        'total_years': end_year - start_year,
        'next_segment_type': next_seg_type,
    }


def _find_nearest_phase(year, phase):
    """找到给定年份最近的某相位年份和距离"""
    years = _generate_cycle_years(phase)
    best_year = min(years, key=lambda y: abs(y - year))
    return best_year, abs(best_year - year)


def _find_past_same_segments(seg_type, current_start, points=None):
    """从cycle引擎找到当前段类型的历史段"""
    if points is None:
        points = _generate_all_turning_points()

    segments = []
    for i in range(len(points) - 1):
        sy, sp = points[i]
        ey, ep = points[i + 1]
        st = _SEGMENT_TYPES.get((sp, ep))
        if st == seg_type and ey < current_start:
            segments.append({
                'start': sy,
                'end': ey,
                'length': ey - sy,
            })

    segments.sort(key=lambda s: s['end'], reverse=True)
    return segments


# ============================================================
# Part 3: 三层标签生成
# ============================================================

def _load_history():
    """加载历史事件JSON"""
    json_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'economic_cycle_history.json'
    )
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _find_event_in_json(json_key, start_year, end_year, history):
    """在历史JSON中查找匹配的事件描述"""
    entries = history.get(json_key, [])
    for e in entries:
        if e.get('start') == start_year and e.get('end') == end_year:
            return e.get('event', '待记录')
    return '待记录'


def _count_dims(d):
    """递归计算展平后的维度数"""
    count = 0
    if isinstance(d, dict):
        for v in d.values():
            count += _count_dims(v)
    elif isinstance(d, (str, int, float)):
        if d != '' and d is not None:
            count += 1
    elif isinstance(d, list):
        for item in d:
            count += _count_dims(item)
    return count


def generate_labels_from_timestamp(year, month, day, hour=12, minute=0):
    """
    主入口：从时间戳生成经济周期标签字典

    Args:
        year, month, day, hour, minute: 时间参数（仅year参与计算）

    Returns:
        dict: {"layers": {"L1_xxx": {...}, ...}, "meta": {...}}
    """
    points = _generate_all_turning_points()
    seg = _find_current_segment(year, points)

    if seg is None:
        return {
            "layers": {"L1_周期定位": {"错误": "无法定位当前段"}},
            "meta": {"system_name": "economic_cycle", "error": True}
        }

    seg_type = seg['segment_type']
    start_year = seg['start_year']
    end_year = seg['end_year']
    total_years = seg['total_years']
    elapsed = year - start_year
    remaining = end_year - year
    progress = round(elapsed / total_years * 100, 1) if total_years > 0 else 100.0

    # ===== L1: 周期定位（纯数学，高信任度） =====
    nearest_a_year, nearest_a_dist = _find_nearest_phase(year, 'A')
    nearest_b_year, nearest_b_dist = _find_nearest_phase(year, 'B')
    nearest_c_year, nearest_c_dist = _find_nearest_phase(year, 'C')

    L1 = {
        "当前段类型": seg_type,
        "段起始年份": str(start_year),
        "段起始阶段": _PHASE_CN[seg['start_phase']],
        "段结束年份": str(end_year),
        "段结束阶段": _PHASE_CN[seg['end_phase']],
        "段总长度": str(total_years),
        "段已走年数": str(elapsed),
        "段剩余年数": str(remaining),
        "段进度": f"{progress}%",
        "最近A恐慌": f"{nearest_a_year}年(距{nearest_a_dist}年)",
        "最近B繁荣": f"{nearest_b_year}年(距{nearest_b_dist}年)",
        "最近C艰难": f"{nearest_c_year}年(距{nearest_c_dist}年)",
    }

    # ===== L5: 投资窗口（推演，中信任度） =====
    if progress <= 33.3:
        stage = '早期'
    elif progress <= 66.6:
        stage = '中期'
    else:
        stage = '晚期'

    window_type = _WINDOW_TYPES[seg_type]
    action = _ACTION_MAP.get((seg_type, stage), '观望')

    if progress <= 33.3:
        risk = '低'
    elif progress <= 66.6:
        risk = '中'
    else:
        risk = '高'

    next_window_str = '未知'
    if seg['next_segment_type']:
        nw = _WINDOW_TYPES.get(seg['next_segment_type'], '未知')
        next_window_str = str(nw) + '(' + str(end_year) + ')' + '年起'
    L5 = {
        "窗口类型": window_type,
        "窗口阶段": stage,
        "操作建议": action,
        "风险等级": risk,
        "距窗口关闭": f"{remaining}年",
        "下一窗口": next_window_str,
    }

    # ===== L6: 历史对照（种子数据+成长，中低信任度） =====
    history = _load_history()
    json_key = _TYPE_TO_JSON_KEY[seg_type]
    past_segs = _find_past_same_segments(seg_type, start_year, points)

    # 上一个同类型段
    last_seg_str = '待记录'
    if len(past_segs) >= 1:
        ps = past_segs[0]
        event = _find_event_in_json(json_key, ps['start'], ps['end'], history)
        last_seg_str = f"{ps['start']}-{ps['end']}年: {event}"

    # 上上一个同类型段
    last_last_seg_str = '待记录'
    if len(past_segs) >= 2:
        ps = past_segs[1]
        event = _find_event_in_json(json_key, ps['start'], ps['end'], history)
        last_last_seg_str = f"{ps['start']}-{ps['end']}年: {event}"

    # 历史平均长度（从cycle引擎精确计算）
    if past_segs:
        avg_length = sum(s['length'] for s in past_segs) / len(past_segs)
        avg_str = f"{avg_length:.1f}年"
        diff = total_years - avg_length
        if abs(diff) <= 1:
            vs_avg = '正常'
        elif diff > 1:
            vs_avg = f'偏长(+{diff:.1f}年)'
        else:
            vs_avg = f'偏短({diff:.1f}年)'
    else:
        avg_str = '待记录'
        vs_avg = '待记录'

    L6 = {
        "上一轮同段": last_seg_str,
        "上上轮同段": last_last_seg_str,
        "历史平均长度": avg_str,
        "当前vs均值": vs_avg,
    }

    # 计算维度数
    total_dims = _count_dims(L1) + _count_dims(L5) + _count_dims(L6)

    return {
        "layers": {
            "L1_周期定位": L1,
            "L5_投资窗口": L5,
            "L6_历史对照": L6,
        },
        "meta": {
            "system_name": "economic_cycle",
            "system_name_cn": "经济周期",
            "total_dimensions": total_dims,
            "trust_levels": {
                "L1_周期定位": "high",
                "L5_投资窗口": "medium",
                "L6_历史对照": "medium_low",
            },
            "growth_enabled": True,
            "growth_note": "L6历史对照层支持自动成长，运行器可在新段完成时通过联网搜索追加事件记录",
        }
    }


# ============================================================
# 测试块
# ============================================================
if __name__ == "__main__":
    from datetime import datetime

    print("=" * 60)
    print("经济周期标签系统 测试")
    print("=" * 60)

    # 测试1: 三条循环验证
    print("\n--- 测试1: 循环验证 ---")
    for phase in ['A', 'B', 'C']:
        years = _generate_cycle_years(phase, 1900, 2100)
        print(f"{phase}: {years[:8]}...共{len(years)}个年份")

    # 验证间隔
    for phase in ['A', 'B', 'C']:
        years = _generate_cycle_years(phase, 1920, 2060)
        intervals = [years[i+1] - years[i] for i in range(len(years)-1)]
        cfg_intervals = _CYCLES[phase]['intervals']
        n = len(cfg_intervals)
        for i, gap in enumerate(intervals):
            expected = cfg_intervals[i % n]
            assert gap == expected, f"{phase}间隔错误: 位置{i} 期望{expected} 实际{gap}"
        print(f"{phase}间隔验证通过: {cfg_intervals}")

    # 测试2: 当前时间段定位
    print("\n--- 测试2: 当前时间定位 ---")
    now = datetime.now()
    result = generate_labels_from_timestamp(now.year, now.month, now.day, now.hour, now.minute)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试3: 4种段类型各测一个
    print("\n--- 测试3: 4种段类型验证 ---")
    test_years = {
        2024: "C→B段预期",   # 2023C→2026B
        2026: "B→C段预期",   # 2026B→2032C
        2033: "C→B段预期",   # 2032C→2034B
        2034: "B→A段预期",   # 2034B→2035A
    }
    for y, desc in test_years.items():
        r = generate_labels_from_timestamp(y, 1, 1)
        seg_type = r["layers"]["L1_周期定位"]["当前段类型"]
        progress = r["layers"]["L1_周期定位"]["段进度"]
        print(f"  {y}年: {seg_type} 进度{progress} ({desc})")

    # 测试4: 维度数
    print(f"\n--- 测试4: 维度数 ---")
    total_dims = result["meta"]["total_dimensions"]
    print(f"总维度: {total_dims}")
    assert total_dims == 22, f"维度数应为22，实际{total_dims}"
    print("维度验证通过 ✓")

    # 测试5: 12种操作组合
    print("\n--- 测试5: 操作建议组合 ---")
    for seg_t in ['C→B', 'B→A', 'A→C', 'B→C']:
        for stage in ['早期', '中期', '晚期']:
            action = _ACTION_MAP.get((seg_t, stage), '未定义')
            print(f"  {seg_t} {stage}: {action}")

    print("\n" + "=" * 60)
    print("全部测试通过 ✓")
    print("=" * 60)

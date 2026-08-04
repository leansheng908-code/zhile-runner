#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
其他中国术数记忆标签字典生成器 v1.0
小六壬 · 九宫飞星 · 姓名学 · 测字术 · 紫白九星
"""

import json
import os
from datetime import datetime

DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# ============================================================
# Part 1: 基础数据表
# ============================================================

# --- 小六壬 (诸葛马前课) ---
XIAOLIUREN = [
    {"name": "大安", "dizhi": "寅", "wuxing": "木", "jixiong": "吉", "desc": "事事安稳", "xiang": "青龙", "yi": "求财/谋事/出行"},
    {"name": "留连", "dizhi": "卯", "wuxing": "水", "jixiong": "凶", "desc": "事多拖延", "xiang": "玄武", "yi": "不宜急事"},
    {"name": "速喜", "dizhi": "辰", "wuxing": "火", "jixiong": "吉", "desc": "喜事速至", "xiang": "朱雀", "yi": "求财/谋事/求名"},
    {"name": "赤口", "dizhi": "巳", "wuxing": "金", "jixiong": "凶", "desc": "口舌是非", "xiang": "白虎", "yi": "防口舌/防官非"},
    {"name": "小吉", "dizhi": "午", "wuxing": "水", "jixiong": "吉", "desc": "小有吉利", "xiang": "六合", "yi": "求财/谋事/婚恋"},
    {"name": "空亡", "dizhi": "未", "wuxing": "土", "jixiong": "大凶", "desc": "万事落空", "xiang": "勾陈", "yi": "万事不宜"},
]

# --- 九宫飞星 (紫白九星) ---
JIUGONG_FEIXING = {
    1: {"name": "一白", "gua": "坎", "wuxing": "水", "fangwei": "正北", "desc": "桃花文昌", "jixiong": "吉", "zhuguan": "事业/人缘"},
    2: {"name": "二黑", "gua": "坤", "wuxing": "土", "fangwei": "西南", "desc": "病符星", "jixiong": "凶", "zhuguan": "疾病/健康"},
    3: {"name": "三碧", "gua": "震", "wuxing": "木", "fangwei": "正东", "desc": "禄存星", "jixiong": "凶", "zhuguan": "口舌/是非"},
    4: {"name": "四绿", "gua": "巽", "wuxing": "木", "fangwei": "东南", "desc": "文曲星", "jixiong": "吉", "zhuguan": "学业/文昌"},
    5: {"name": "五黄", "gua": "中", "wuxing": "土", "fangwei": "中宫", "desc": "廉贞大煞", "jixiong": "大凶", "zhuguan": "灾祸/意外"},
    6: {"name": "六白", "gua": "乾", "wuxing": "金", "fangwei": "西北", "desc": "武曲星", "jixiong": "吉", "zhuguan": "权力/贵人"},
    7: {"name": "七赤", "gua": "兑", "wuxing": "金", "fangwei": "正西", "desc": "破军星", "jixiong": "凶", "zhuguan": "破财/口舌"},
    8: {"name": "八白", "gua": "艮", "wuxing": "土", "fangwei": "东北", "desc": "左辅星", "jixiong": "大吉", "zhuguan": "财运/置业"},
    9: {"name": "九紫", "gua": "离", "wuxing": "火", "fangwei": "正南", "desc": "右弼星", "jixiong": "大吉", "zhuguan": "姻缘/喜庆"},
}

# --- 三元九运 (20年一运, 180年一大循环) ---
SANYUAN_JIUYUN = [
    {"yun": "一运", "start": 1864, "end": 1883, "star": 1, "yuan": "上元"},
    {"yun": "二运", "start": 1884, "end": 1903, "star": 2, "yuan": "上元"},
    {"yun": "三运", "start": 1904, "end": 1923, "star": 3, "yuan": "上元"},
    {"yun": "四运", "start": 1924, "end": 1943, "star": 4, "yuan": "中元"},
    {"yun": "五运", "start": 1944, "end": 1963, "star": 5, "yuan": "中元"},
    {"yun": "六运", "start": 1964, "end": 1983, "star": 6, "yuan": "中元"},
    {"yun": "七运", "start": 1984, "end": 2003, "star": 7, "yuan": "下元"},
    {"yun": "八运", "start": 2004, "end": 2023, "star": 8, "yuan": "下元"},
    {"yun": "九运", "start": 2024, "end": 2043, "star": 9, "yuan": "下元"},
]

# --- 姓名学五格剖象法 ---
WUGE = {
    "天格": {"desc": "姓氏笔画+1(单姓)或两姓笔画之和(复姓)", "zhuguan": "祖上/长辈/先天运"},
    "人格": {"desc": "姓氏末字+名字首字笔画", "zhuguan": "主运/性格/核心命运", "importance": "最重要"},
    "地格": {"desc": "名字笔画之和(单名+1)", "zhuguan": "早年运/基础运"},
    "总格": {"desc": "姓名总笔画", "zhuguan": "晚年运/总体命运"},
    "外格": {"desc": "总格-人格+1", "zhuguan": "人际运/社交运"},
}

# --- 81数理吉凶 (姓名学) ---
SHULI_81 = {
    1: "大吉", 2: "凶", 3: "大吉", 4: "凶", 5: "大吉",
    6: "大吉", 7: "吉", 8: "吉", 9: "凶", 10: "凶",
    11: "大吉", 12: "凶", 13: "大吉", 14: "凶", 15: "大吉",
    16: "大吉", 17: "吉", 18: "吉", 19: "凶", 20: "凶",
    21: "大吉", 22: "凶", 23: "大吉", 24: "大吉", 25: "吉",
    26: "凶", 27: "吉", 28: "凶", 29: "吉", 30: "凶",
    31: "大吉", 32: "大吉", 33: "大吉", 34: "大凶", 35: "吉",
    36: "凶", 37: "吉", 38: "吉", 39: "吉", 40: "凶",
}

# --- 测字术基本偏旁含义 ---
CEZI_PIANPANG = {
    "人(亻)": {"wuxing": "金", "desc": "主信义/仁慈"},
    "水(氵)": {"wuxing": "水", "desc": "主智慧/流动"},
    "火(灬)": {"wuxing": "火", "desc": "主礼节/热情"},
    "木": {"wuxing": "木", "desc": "主仁慈/成长"},
    "土": {"wuxing": "土", "desc": "主信实/厚重"},
    "金(钅)": {"wuxing": "金", "desc": "主刚毅/决断"},
    "日": {"wuxing": "火", "desc": "主光明/正气"},
    "月": {"wuxing": "水", "desc": "主阴柔/变化"},
    "山": {"wuxing": "土", "desc": "主稳固/阻碍"},
    "心(忄)": {"wuxing": "火", "desc": "主思考/情感"},
}

# --- 五行笔画对应 (康熙字典) ---
WUXING_BIHUA = {
    "木": [1, 2, 11, 12, 21, 22, 31, 32, 41, 42, 51, 52],
    "火": [3, 4, 13, 14, 23, 24, 33, 34, 43, 44, 53, 54],
    "土": [5, 6, 15, 16, 25, 26, 35, 36, 45, 46, 55, 56],
    "金": [7, 8, 17, 18, 27, 28, 37, 38, 47, 48, 57, 58],
    "水": [9, 10, 19, 20, 29, 30, 39, 40, 49, 50, 59, 60],
}

# --- 太岁 (十二值年神) ---
TAISUI = {
    "子": {"太岁": "甲子金辩", "方位": "正北"},
    "丑": {"太岁": "乙丑陈材", "方位": "东北"},
    "寅": {"太岁": "丙寅耿章", "方位": "东北偏东"},
    "卯": {"太岁": "丁卯沈兴", "方位": "正东"},
    "辰": {"太岁": "戊辰赵达", "方位": "东南偏东"},
    "巳": {"太岁": "己巳郭灿", "方位": "东南偏南"},
    "午": {"太岁": "庚午王清", "方位": "正南"},
    "未": {"太岁": "辛未李素", "方位": "西南偏南"},
    "申": {"太岁": "壬申刘旺", "方位": "西南偏西"},
    "酉": {"太岁": "癸酉康忠", "方位": "正西"},
    "戌": {"太岁": "甲戌誓广", "方位": "西北偏西"},
    "亥": {"太岁": "乙亥吴保", "方位": "西北偏北"},
}

# --- 五行生克 ---
WUXING_SHENG = {"金":"水","水":"木","木":"火","火":"土","土":"金"}
WUXING_KE = {"金":"木","木":"土","土":"水","水":"火","火":"金"}


# ============================================================
# Part 2: 计算函数
# ============================================================

def solar_to_ganzhi(year, month, day):
    try:
        from lunar_python import Solar
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        return lunar.getYearInGanZhi(), lunar.getDayInGanZhi()
    except ImportError:
        base = datetime(2024, 1, 1)
        target = datetime(year, month, day)
        days_diff = (target - base).days
        day_idx = days_diff % 60
        day_gan = TIANGAN[day_idx % 10]
        day_zhi = DIZHI[day_idx % 12]
        year_zhi = DIZHI[(4 + (year - 2024)) % 12]
        year_gan = TIANGAN[(0 + (year - 2024)) % 10]
        return year_gan + year_zhi, day_gan + day_zhi

def get_xiaoliuren(month, day, hour_zhi_idx):
    """小六壬排盘: 月起大安, 日从月上起, 时从日上起"""
    month_pos = (month - 1) % 6
    day_pos = (month_pos + day - 1) % 6
    hour_pos = (day_pos + hour_zhi_idx) % 6
    return XIAOLIUREN[month_pos], XIAOLIUREN[day_pos], XIAOLIUREN[hour_pos]

def get_current_yun(year):
    """获取当前元运"""
    for yun in SANYUAN_JIUYUN:
        if yun["start"] <= year <= yun["end"]:
            return yun
    return SANYUAN_JIUYUN[-1]

def get_annual_star(year):
    """获取年飞星入中宫数 (简化)"""
    # 九运(2024-2043)期间, 每年入中星递减
    yun = get_current_yun(year)
    yun_star = yun["star"]
    years_into_yun = year - yun["start"]
    # 入中星 = 用减法: 2024年九紫入中
    center_star = (yun_star - years_into_yun) % 9
    if center_star == 0:
        center_star = 9
    return center_star

def get_taisui(year_zhi):
    """获取太岁"""
    return TAISUI.get(year_zhi, {})


# ============================================================
# Part 3: 标签生成
# ============================================================

def generate_qita_labels(year=None, month=None, day=None, hour=None):
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = {}
    
    year_gz, day_gz = solar_to_ganzhi(year, month, day)
    year_zhi = year_gz[-1]
    year_gan = year_gz[0]
    
    hour_zhi_idx = (hour % 24 + 1) // 2 % 12
    hour_zhi = DIZHI[hour_zhi_idx]
    
    xlr_month, xlr_day, xlr_hour = get_xiaoliuren(month, day, hour_zhi_idx)
    current_yun = get_current_yun(year)
    annual_star = get_annual_star(year)
    taisui = get_taisui(year_zhi)
    
    # --- L1: 基础排盘 (12维) ---
    labels["L1_基础排盘"] = {
        "年干支": year_gz,
        "日干支": day_gz,
        "年支": year_zhi,
        "年干": year_gan,
        "时支": hour_zhi,
        "小六壬月宫": xlr_month["name"],
        "小六壬日宫": xlr_day["name"],
        "小六壬时宫": xlr_hour["name"],
        "当前元运": f"{current_yun['yun']}({current_yun['yuan']})",
        "年飞星入中": f"{annual_star}({JIUGONG_FEIXING[annual_star]['name']})",
        "太岁": taisui.get("太岁", "?"),
        "太岁方位": taisui.get("方位", "?"),
    }
    
    # --- L2: 小六壬六宫 (6维) ---
    labels["L2_小六壬六宫"] = {}
    for xlr in XIAOLIUREN:
        labels["L2_小六壬六宫"][xlr["name"]] = {
            "地支": xlr["dizhi"],
            "五行": xlr["wuxing"],
            "吉凶": xlr["jixiong"],
            "描述": xlr["desc"],
            "象意": xlr["xiang"],
            "宜": xlr["yi"],
        }
    
    # --- L3: 小六壬三宫排盘 (18维) ---
    labels["L3_小六壬排盘"] = {}
    for label, xlr in [("月宫", xlr_month), ("日宫", xlr_day), ("时宫", xlr_hour)]:
        labels["L3_小六壬排盘"][f"{label}_{xlr['name']}"] = {
            "五行": xlr["wuxing"],
            "吉凶": xlr["jixiong"],
            "描述": xlr["desc"],
            "象意": xlr["xiang"],
            "宜": xlr["yi"],
            "地支": xlr["dizhi"],
        }
    
    # --- L4: 九宫飞星九星 (9维) ---
    labels["L4_九宫飞星"] = {}
    for num, info in JIUGONG_FEIXING.items():
        labels["L4_九宫飞星"][f"{num}_{info['name']}"] = {
            "卦": info["gua"],
            "五行": info["wuxing"],
            "方位": info["fangwei"],
            "吉凶": info["jixiong"],
            "描述": info["desc"],
            "主管": info["zhuguan"],
            "本年入中": "✅" if num == annual_star else "❌",
        }
    
    # --- L5: 三元九运 (9维) ---
    labels["L5_三元九运"] = {}
    for yun in SANYUAN_JIUYUN:
        labels["L5_三元九运"][yun["yun"]] = {
            "年份": f"{yun['start']}-{yun['end']}",
            "元": yun["yuan"],
            "当运星": f"{yun['star']}白",
            "当前是否": "✅" if yun["yun"] == current_yun["yun"] else "❌",
        }
    
    # --- L6: 姓名学五格 (5维) ---
    labels["L6_姓名学五格"] = {}
    for name, info in WUGE.items():
        labels["L6_姓名学五格"][name] = {
            "算法": info["desc"],
            "主管": info["zhuguan"],
            "重要性": info.get("importance", "一般"),
        }
    
    # --- L7: 81数理吉凶 (40维) ---
    labels["L7_数理吉凶"] = {}
    for num, jixiong in SHULI_81.items():
        labels["L7_数理吉凶"][f"{num}数"] = {"吉凶": jixiong}
    
    # --- L8: 五行笔画对应 (5维) ---
    labels["L8_五行笔画"] = {}
    for wx, bihua in WUXING_BIHUA.items():
        labels["L8_五行笔画"][wx] = {"笔画": bihua[:6], "desc": f"尾数{[b%10 for b in bihua[:6]]}属{wx}"}
    
    # --- L9: 测字术偏旁 (10维) ---
    labels["L9_测字术"] = {}
    for pian, info in CEZI_PIANPANG.items():
        labels["L9_测字术"][pian] = {
            "五行": info["wuxing"],
            "含义": info["desc"],
        }
    
    # --- L10: 太岁系统 (12维) ---
    labels["L10_太岁系统"] = {}
    for dz, info in TAISUI.items():
        labels["L10_太岁系统"][f"{dz}年太岁"] = {
            "太岁名": info["太岁"],
            "方位": info["方位"],
            "本年是否": "✅" if dz == year_zhi else "❌",
        }
    
    # --- L11: 年飞星九宫分布 (9维) ---
    labels["L11_年飞星分布"] = {}
    # 飞星顺序: 中→乾→兑→艮→离→坎→坤→震→巽 (洛书顺序)
    feixing_order = [5, 6, 7, 8, 9, 1, 2, 3, 4]  # 洛书宫位
    positions = ["中宫", "乾(西北)", "兑(正西)", "艮(东北)", "离(正南)", "坎(正北)", "坤(西南)", "震(正东)", "巽(东南)"]
    for i, pos in enumerate(positions):
        star = (annual_star - 1 + i) % 9 + 1
        star_info = JIUGONG_FEIXING[star]
        labels["L11_年飞星分布"][pos] = {
            "飞星": f"{star}_{star_info['name']}",
            "五行": star_info["wuxing"],
            "吉凶": star_info["jixiong"],
            "主管": star_info["zhuguan"],
        }
    
    # --- L12: 元运分析 (8维) ---
    yun_star_info = JIUGONG_FEIXING[current_yun["star"]]
    labels["L12_元运分析"] = {
        "当前运": current_yun["yun"],
        "当前元": current_yun["yuan"],
        "运期": f"{current_yun['start']}-{current_yun['end']}",
        "当运星": f"{current_yun['star']}_{yun_star_info['name']}",
        "运星五行": yun_star_info["wuxing"],
        "运星吉凶": yun_star_info["jixiong"],
        "运星主管": yun_star_info["zhuguan"],
        "运星描述": yun_star_info["desc"],
    }
    
    # --- L13: 小六壬综合分析 (10维) ---
    labels["L13_小六壬分析"] = {
        "月宫吉凶": xlr_month["jixiong"],
        "日宫吉凶": xlr_day["jixiong"],
        "时宫吉凶": xlr_hour["jixiong"],
        "三宫五行": f"{xlr_month['wuxing']}-{xlr_day['wuxing']}-{xlr_hour['wuxing']}",
        "月宫象意": xlr_month["xiang"],
        "日宫象意": xlr_day["xiang"],
        "时宫象意": xlr_hour["xiang"],
        "综合吉凶": "吉" if xlr_hour["jixiong"] in ("吉","大吉") else ("凶" if xlr_hour["jixiong"] in ("凶","大凶") else "平"),
        "月宫宜": xlr_month["yi"],
        "时宫宜": xlr_hour["yi"],
    }
    
    # --- L14: 年度飞星风水 (10维) ---
    labels["L14_年度风水"] = {
        "年飞星": f"{annual_star}_{JIUGONG_FEIXING[annual_star]['name']}",
        "入中五行": JIUGONG_FEIXING[annual_star]["wuxing"],
        "入中吉凶": JIUGONG_FEIXING[annual_star]["jixiong"],
        "太岁方位": taisui.get("方位", "?"),
        "三煞方位": "待计算",
        "五黄方位": "待计算",
        "二黑方位": "待计算",
        "财星方位": "待计算",
        "喜星方位": "待计算",
        "文昌方位": "待计算",
    }
    
    # --- L15: 姓名学数理分析 (10维) ---
    labels["L15_姓名学数理"] = {
        "天格含义": "祖上根基与先天禀赋",
        "人格含义": "主运，一生核心命运",
        "地格含义": "早年(36岁前)运势",
        "总格含义": "晚年(36岁后)总体运势",
        "外格含义": "人际关系与社交运",
        "三才配置": "天/人/地三格五行相生相克",
        "阴阳配置": "笔画奇偶阴阳平衡",
        "五行补益": "通过姓名五行补八字所缺",
        "数理吉凶": "81数理判断各格吉凶",
        "喜用神配合": "姓名五行配合八字喜用神",
    }
    
    # --- L16: 综合术数信息 (10维) ---
    labels["L16_综合术数"] = {
        "小六壬月宫": xlr_month["name"],
        "小六壬日宫": xlr_day["name"],
        "小六壬时宫": xlr_hour["name"],
        "年飞星": JIUGONG_FEIXING[annual_star]["name"],
        "元运": current_yun["yun"],
        "太岁": taisui.get("太岁", "?"),
        "太岁方位": taisui.get("方位", "?"),
        "小六壬综合": f"月{xlr_month['name']}→日{xlr_day['name']}→时{xlr_hour['name']}",
        "飞星综合": f"{JIUGONG_FEIXING[annual_star]['name']}入中({JIUGONG_FEIXING[annual_star]['jixiong']})",
        "风水要点": f"{current_yun['yun']}当令{yun_star_info['name']}({yun_star_info['zhuguan']})",
    }
    
    # --- L17: 盘面总评 (10维) ---
    ji_count = sum(1 for x in [xlr_month, xlr_day, xlr_hour] if x["jixiong"] in ("吉","大吉"))
    xiong_count = sum(1 for x in [xlr_month, xlr_day, xlr_hour] if x["jixiong"] in ("凶","大凶"))
    
    labels["L17_盘面总评"] = {
        "小六壬总评": f"月{xlr_month['name']}日{xlr_day['name']}时{xlr_hour['name']}",
        "飞星总评": f"{JIUGONG_FEIXING[annual_star]['name']}入中-{JIUGONG_FEIXING[annual_star]['jixiong']}",
        "元运总评": f"{current_yun['yun']}-{yun_star_info['name']}({yun_star_info['zhuguan']})",
        "太岁总评": f"{taisui.get('太岁','?')}({taisui.get('方位','?')})",
        "吉宫数": ji_count,
        "凶宫数": xiong_count,
        "时宫吉凶": xlr_hour["jixiong"],
        "飞星吉凶": JIUGONG_FEIXING[annual_star]["jixiong"],
        "元运吉凶": yun_star_info["jixiong"],
        "综合建议": "吉" if ji_count >= 2 and JIUGONG_FEIXING[annual_star]["jixiong"] in ("吉","大吉") else ("凶" if xiong_count >= 2 else "平"),
    }
    
    return labels


def count_dimensions(labels):
    total = 0
    for layer_name, layer_data in labels.items():
        if isinstance(layer_data, dict):
            total += len(layer_data)
        else:
            total += 1
    return total


def generate_dictionary(year=None, month=None, day=None, hour=None):
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = generate_qita_labels(year, month, day, hour)
    
    dictionary = {
        "system": "其他中国术数",
        "system_alias": "Other Chinese Divination",
        "title": "小六壬 · 九宫飞星 · 姓名学 · 测字术 · 太岁",
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "timestamp": f"{year}-{month:02d}-{day:02d} {hour:02d}:00",
        "architecture": "解压缩架构: 时间戳 → 综合术数排盘 → 标签向量",
        "description": "汇总小六壬、九宫飞星、三元九运、姓名学五格剖象法、测字术、太岁系统等中国术数体系。",
        "total_dimensions": count_dimensions(labels),
        "total_layers": len(labels),
        "layers": labels,
    }
    return dictionary


def generate_labels_from_timestamp(year, month, day, hour=12):
    return generate_dictionary(year, month, day, hour)


if __name__ == "__main__":
    print("=" * 60)
    print("其他中国术数记忆标签字典生成器 v1.0")
    print("=" * 60)
    
    print("\n[1] 生成标签字典JSON...")
    dictionary = generate_dictionary(2026, 8, 4, 18)
    total_dims = dictionary["total_dimensions"]
    print(f"    总维度数: {total_dims}")
    print(f"    层数: {dictionary['total_layers']}")
    
    print(f"\n[2] 各层维度分布:")
    for layer_name, layer_data in dictionary["layers"].items():
        dim_count = len(layer_data) if isinstance(layer_data, dict) else 1
        print(f"    {layer_name}: {dim_count}维")
    
    print(f"\n[3] 当前时间排盘验证:")
    l1 = dictionary["layers"]["L1_基础排盘"]
    print(f"    时间: 2026-08-04 18:00")
    print(f"    年干支: {l1['年干支']}")
    print(f"    小六壬: 月{l1['小六壬月宫']}日{l1['小六壬日宫']}时{l1['小六壬时宫']}")
    print(f"    元运: {l1['当前元运']}")
    print(f"    年飞星: {l1['年飞星入中']}")
    print(f"    太岁: {l1['太岁']}({l1['太岁方位']})")
    
    l17 = dictionary["layers"]["L17_盘面总评"]
    print(f"\n    盘面总评:")
    print(f"      小六壬: {l17['小六壬总评']}")
    print(f"      飞星: {l17['飞星总评']}")
    print(f"      元运: {l17['元运总评']}")
    print(f"      综合: {l17['综合建议']}")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "qita_label_dictionary.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(output_path) / 1024
    print(f"\n[4] JSON已保存: {output_path}")
    print(f"    文件大小: {file_size:.1f} KB")
    
    print(f"\n[5] 数据验证:")
    assert len(XIAOLIUREN) == 6
    print(f"    小六壬六宫: {len(XIAOLIUREN)} (应为6) ✅")
    assert len(JIUGONG_FEIXING) == 9
    print(f"    九宫飞星: {len(JIUGONG_FEIXING)} (应为9) ✅")
    assert len(SANYUAN_JIUYUN) == 9
    print(f"    三元九运: {len(SANYUAN_JIUYUN)} (应为9) ✅")
    assert len(WUGE) == 5
    print(f"    五格: {len(WUGE)} (应为5) ✅")
    assert len(TAISUI) == 12
    print(f"    太岁: {len(TAISUI)} (应为12) ✅")
    assert XIAOLIUREN[0]["name"] == "大安"
    print(f"    小六壬首宫=大安 ✅")
    current_yun_result = get_current_yun(2026)
    assert current_yun_result["yun"] == "九运"
    print(f"    2026年=九运 ✅")
    assert JIUGONG_FEIXING[9]["name"] == "九紫"
    print(f"    九紫星验证 ✅")
    
    print("\n" + "=" * 60)
    print("其他中国术数标签字典生成完成!")
    print(f"总维度: {total_dims}维 / 17层 / {file_size:.1f}KB")
    print("=" * 60)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中医术数时间记忆标签字典生成器 v1.0
解压缩架构: 时间戳 → 中医时间排盘 → 标签向量
子午流注 · 灵龟八法 · 飞腾八法 · 五运六气
"""

import json
import os
from datetime import datetime

DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# ============================================================
# Part 1: 基础数据表
# ============================================================

# --- 子午流注: 十二经脉对应十二时辰 ---
ZIWULIUZHU = {
    "子": {"经脉": "胆经(足少阳胆经)", "wuxing": "木", "流注": "当令", "desc": "子时胆经旺，一阳初生，宜安睡养胆", "养生": "安睡/勿熬夜"},
    "丑": {"经脉": "肝经(足厥阴肝经)", "wuxing": "木", "流注": "当令", "desc": "丑时肝经旺，藏血解毒，宜深度睡眠", "养生": "深度睡眠"},
    "寅": {"经脉": "肺经(手太阴肺经)", "wuxing": "金", "流注": "当令", "desc": "寅时肺经旺，气血由静转动，宜安睡", "养生": "安睡/勿早起剧烈"},
    "卯": {"经脉": "大肠经(手阳明大肠经)", "wuxing": "金", "流注": "当令", "desc": "卯时大肠经旺，宜排便排毒", "养生": "晨起饮水/排便"},
    "辰": {"经脉": "胃经(足阳明胃经)", "wuxing": "土", "流注": "当令", "desc": "辰时胃经旺，宜进早餐", "养生": "吃好早餐"},
    "巳": {"经脉": "脾经(足太阴脾经)", "wuxing": "土", "流注": "当令", "desc": "巳时脾经旺，运化水谷精微", "养生": "工作学习最佳时段"},
    "午": {"经脉": "心经(手少阴心经)", "wuxing": "火", "流注": "当令", "desc": "午时心经旺，宜午休养心", "养生": "午休15-30分钟"},
    "未": {"经脉": "小肠经(手太阳小肠经)", "wuxing": "火", "流注": "当令", "desc": "未时小肠经旺，吸收营养", "养生": "午餐消化/勿剧烈"},
    "申": {"经脉": "膀胱经(足太阳膀胱经)", "wuxing": "水", "流注": "当令", "desc": "申时膀胱经旺，宜多饮水排毒", "养生": "多喝水/运动"},
    "酉": {"经脉": "肾经(足少阴肾经)", "wuxing": "水", "流注": "当令", "desc": "酉时肾经旺，藏精纳气", "养生": "休息/勿过劳"},
    "戌": {"经脉": "心包经(手厥阴心包经)", "wuxing": "火", "流注": "当令", "desc": "戌时心包经旺，宜散步放松", "养生": "散步/听音乐"},
    "亥": {"经脉": "三焦经(手少阳三焦经)", "wuxing": "火", "流注": "当令", "desc": "亥时三焦经旺，宜安睡养百脉", "养生": "安睡/勿兴奋"},
}

# --- 灵龟八法: 八脉交会穴 ---
LINGGUI_BAFA = {
    "公孙": {"经脉": "脾经", "通脉": "冲脉", "配穴": "内关", "八卦": "乾", "num": 1, "desc": "胃心胸疾患"},
    "内关": {"经脉": "心包经", "通脉": "阴维脉", "配穴": "公孙", "八卦": "艮", "num": 2, "desc": "胃心胸疾患"},
    "后溪": {"经脉": "小肠经", "通脉": "督脉", "配穴": "申脉", "八卦": "巽", "num": 3, "desc": "项强耳疾"},
    "申脉": {"经脉": "膀胱经", "通脉": "阳蹻脉", "配穴": "后溪", "八卦": "震", "num": 4, "desc": "项强耳疾"},
    "足临泣": {"经脉": "胆经", "通脉": "带脉", "配穴": "外关", "八卦": "兑", "num": 5, "desc": "目锐眦耳后疾"},
    "外关": {"经脉": "三焦经", "通脉": "阳维脉", "配穴": "足临泣", "八卦": "坎", "num": 6, "desc": "目锐眦耳后疾"},
    "列缺": {"经脉": "肺经", "通脉": "任脉", "配穴": "照海", "八卦": "离", "num": 7, "desc": "肺系咽喉胸膈疾"},
    "照海": {"经脉": "肾经", "通脉": "阴蹻脉", "配穴": "列缺", "八卦": "坤", "num": 8, "desc": "肺系咽喉胸膈疾"},
}

# --- 飞腾八法 (与灵龟八法穴位相同, 但取穴推算方法不同) ---
FEITENG_BAFA = {
    "甲己": "公孙(乾)", "乙庚": "内关(艮)", "丙辛": "足临泣(兑)",
    "丁壬": "照海(坤)", "戊癸": "列缺(离)", "子午": "后溪(巽)",
    "丑未": "申脉(震)", "寅申": "外关(坎)",
}

# --- 五运六气: 天干化运 (五运) ---
WUYUN = {
    "甲己": {"运": "土运", "太过不及": "甲太过/己不及", "对应": "脾胃", "特征": "湿气偏盛"},
    "乙庚": {"运": "金运", "太过不及": "庚太过/乙不及", "对应": "肺大肠", "特征": "燥气偏盛"},
    "丙辛": {"运": "水运", "太过不及": "丙太过/辛不及", "对应": "肾膀胱", "特征": "寒气偏盛"},
    "丁壬": {"运": "木运", "太过不及": "壬太过/丁不及", "对应": "肝胆", "特征": "风气偏盛"},
    "戊癸": {"运": "火运", "太过不及": "戊太过/癸不及", "对应": "心小肠", "特征": "火气偏盛"},
}

# --- 六气 (司天在泉) ---
LIUQI_SITIAN = {
    "子午": {"司天": "少阴君火", "在泉": "阳明燥金", "desc": "火气司天，金气在泉"},
    "丑未": {"司天": "太阴湿土", "在泉": "太阳寒水", "desc": "湿气司天，寒气在泉"},
    "寅申": {"司天": "少阳相火", "在泉": "厥阴风木", "desc": "火气司天，风气在泉"},
    "卯酉": {"司天": "阳明燥金", "在泉": "少阴君火", "desc": "金气司天，火气在泉"},
    "辰戌": {"司天": "太阳寒水", "在泉": "太阴湿土", "desc": "寒气司天，湿气在泉"},
    "巳亥": {"司天": "厥阴风木", "在泉": "少阳相火", "desc": "风气司天，火气在泉"},
}

# --- 六气主气 (每年固定) ---
LIUQI_ZHUQI = [
    {"name": "初气(厥阴风木)", "time": "大寒~春分", "wuxing": "木", "desc": "风气主令"},
    {"name": "二气(少阴君火)", "time": "春分~小满", "wuxing": "火", "desc": "热气主令"},
    {"name": "三气(少阳相火)", "time": "小满~大暑", "wuxing": "火", "desc": "火气主令"},
    {"name": "四气(太阴湿土)", "time": "大暑~秋分", "wuxing": "土", "desc": "湿气主令"},
    {"name": "五气(阳明燥金)", "time": "秋分~小雪", "wuxing": "金", "desc": "燥气主令"},
    {"name": "终气(太阳寒水)", "time": "小雪~大寒", "wuxing": "水", "desc": "寒气主令"},
]

# --- 六气客气 (随年支变化) ---
LIUQI_KEQI_ORDER = ["厥阴风木", "少阴君火", "太阴湿土", "少阳相火", "阳明燥金", "太阳寒水"]

# --- 十二经纳甲法 (天干对应经脉) ---
NAJIA = {
    "甲": {"经脉": "胆经", "wuxing": "木", "穴位": "足窍阴/侠溪/足临泣"},
    "乙": {"经脉": "肝经", "wuxing": "木", "穴位": "大敦/行间/太冲"},
    "丙": {"经脉": "小肠经", "wuxing": "火", "穴位": "少泽/前谷/后溪"},
    "丁": {"经脉": "心经", "wuxing": "火", "穴位": "少冲/少府/神门"},
    "戊": {"经脉": "胃经", "wuxing": "土", "穴位": "厉兑/内庭/足三里"},
    "己": {"经脉": "脾经", "wuxing": "土", "穴位": "隐白/太白/太白"},
    "庚": {"经脉": "大肠经", "wuxing": "金", "穴位": "商阳/二间/三间"},
    "辛": {"经脉": "肺经", "wuxing": "金", "穴位": "少商/鱼际/太渊"},
    "壬": {"经脉": "膀胱经", "wuxing": "水", "穴位": "至阴/通谷/束骨"},
    "癸": {"经脉": "肾经", "wuxing": "水", "穴位": "涌泉/然谷/太溪"},
}

# --- 十二经纳子法 (地支对应经脉) ---
NAZI = {
    "子": "胆经", "丑": "肝经", "寅": "肺经", "卯": "大肠经",
    "辰": "胃经", "巳": "脾经", "午": "心经", "未": "小肠经",
    "申": "膀胱经", "酉": "肾经", "戌": "心包经", "亥": "三焦经",
}

# --- 五行生克 ---
WUXING_SHENG = {"金":"水","水":"木","木":"火","火":"土","土":"金"}
WUXING_KE = {"金":"木","木":"土","土":"水","水":"火","火":"金"}

# --- 十二消息卦与季节对应 ---
XIAOXI_GUA = {
    "子": {"卦": "复", "desc": "一阳来复", "阴阳": "1阳5阴"},
    "丑": {"卦": "临", "desc": "二阳浸长", "阴阳": "2阳4阴"},
    "寅": {"卦": "泰", "desc": "三阳开泰", "阴阳": "3阳3阴"},
    "卯": {"卦": "大壮", "desc": "四阳壮盛", "阴阳": "4阳2阴"},
    "辰": {"卦": "夬", "desc": "五阳决阴", "阴阳": "5阳1阴"},
    "巳": {"卦": "乾", "desc": "纯阳之体", "阴阳": "6阳0阴"},
    "午": {"卦": "姤", "desc": "一阴始生", "阴阳": "5阳1阴"},
    "未": {"卦": "遁", "desc": "二阴渐长", "阴阳": "4阳2阴"},
    "申": {"卦": "否", "desc": "天地不交", "阴阳": "3阳3阴"},
    "酉": {"卦": "观", "desc": "四阴观省", "阴阳": "2阳4阴"},
    "戌": {"卦": "剥", "desc": "五阴剥阳", "阴阳": "1阳5阴"},
    "亥": {"卦": "坤", "desc": "纯阴之体", "阴阳": "0阳6阴"},
}


# ============================================================
# Part 2: 计算函数
# ============================================================

def solar_to_ganzhi(year, month, day):
    """公历转干支"""
    try:
        from lunar_python import Solar
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        return (lunar.getYearInGanZhi(), lunar.getMonthInGanZhi(), 
                lunar.getDayInGanZhi(), lunar.getDayGan(), lunar.getDayZhi())
    except ImportError:
        base = datetime(2024, 1, 1)
        target = datetime(year, month, day)
        days_diff = (target - base).days
        day_idx = days_diff % 60
        day_gan = TIANGAN[day_idx % 10]
        day_zhi = DIZHI[day_idx % 12]
        year_zhi = DIZHI[(4 + (year - 2024)) % 12]
        year_gan = TIANGAN[(0 + (year - 2024)) % 10]
        return (year_gan + year_zhi, "估算", day_gan + day_zhi, day_gan, day_zhi)

def get_wuyun(year_gan):
    """获取五运"""
    for key, val in WUYUN.items():
        if year_gan in key:
            return val
    return {}

def get_liuqi(year_zhi):
    """获取六气司天在泉"""
    for key, val in LIUQI_SITIAN.items():
        if year_zhi in key:
            return val
    return {}

def get_zhuqi(month):
    """获取主气 (按月份近似)"""
    # 大寒(1月20日)~春分(3月20日)=初气
    if month in [1, 2, 3]:
        return LIUQI_ZHUQI[0] if month <= 2 or (month == 3 and day < 20) else LIUQI_ZHUQI[1]
    elif month in [4, 5]:
        return LIUQI_ZHUQI[2] if month == 5 else LIUQI_ZHUQI[1]
    elif month in [6, 7]:
        return LIUQI_ZHUQI[2] if month <= 7 else LIUQI_ZHUQI[3]
    elif month in [8, 9]:
        return LIUQI_ZHUQI[3] if month <= 9 else LIUQI_ZHUQI[4]
    else:
        return LIUQI_ZHUQI[5] if month >= 11 else LIUQI_ZHUQI[4]

def get_linggui_xue(day_gan, day_zhi, hour_zhi):
    """灵龟八法取穴 (简化)"""
    # 使用飞腾八法简化推算
    gan_key = day_gan + day_gan  # 甲甲=甲己类
    for key, val in FEITENG_BAFA.items():
        if day_gan in key or day_zhi in key:
            return val
    return "未知"

def get_najia_jing(day_gan):
    """纳甲法取经"""
    return NAJIA.get(day_gan, {})

def get_nazi_jing(hour_zhi):
    """纳子法取经"""
    return NAZI.get(hour_zhi, "未知")


# ============================================================
# Part 3: 标签生成
# ============================================================

def generate_zhongyi_labels(year=None, month=None, day=None, hour=None):
    """生成中医术数时间标签 (17层)"""
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = {}
    
    # 排盘
    year_gz, month_gz, day_gz, day_gan, day_zhi = solar_to_ganzhi(year, month, day)
    year_gan = year_gz[0] if len(year_gz) >= 2 else "甲"
    year_zhi = year_gz[-1] if len(year_gz) >= 2 else "子"
    hour_zhi = DIZHI[(hour % 24 + 1) // 2 % 12]
    
    wuyun = get_wuyun(year_gan)
    liuqi = get_liuqi(year_zhi)
    ziwu = ZIWULIUZHU.get(hour_zhi, {})
    najia = get_najia_jing(day_gan)
    nazi = get_nazi_jing(hour_zhi)
    xiaoxi = XIAOXI_GUA.get(hour_zhi, {})
    linggui = get_linggui_xue(day_gan, day_zhi, hour_zhi)
    
    # --- L1: 基础排盘 (14维) ---
    labels["L1_基础排盘"] = {
        "年干支": year_gz,
        "月干支": month_gz,
        "日干支": day_gz,
        "年干": year_gan,
        "年支": year_zhi,
        "日干": day_gan,
        "日支": day_zhi,
        "时支": hour_zhi,
        "五运": f"{wuyun.get('运','?')}({wuyun.get('太过不及','?')})",
        "司天": liuqi.get("司天", "?"),
        "在泉": liuqi.get("在泉", "?"),
        "当令经脉": ziwu.get("经脉", "?"),
        "纳甲经": f"{najia.get('经脉','?')}({najia.get('wuxing','?')})",
        "纳子经": nazi,
    }
    
    # --- L2: 子午流注十二经脉 (12维) ---
    labels["L2_子午流注"] = {}
    for dz in DIZHI:
        info = ZIWULIUZHU[dz]
        labels["L2_子午流注"][f"{dz}时_{info['经脉']}"] = {
            "五行": info["wuxing"],
            "流注": info["流注"],
            "描述": info["desc"],
            "养生建议": info["养生"],
            "是否当令": "✅" if dz == hour_zhi else "❌",
        }
    
    # --- L3: 灵龟八法八脉交会穴 (8维) ---
    labels["L3_灵龟八法"] = {}
    for name, info in LINGGUI_BAFA.items():
        labels["L3_灵龟八法"][name] = {
            "经脉": info["经脉"],
            "通脉": info["通脉"],
            "配穴": info["配穴"],
            "八卦": info["八卦"],
            "主治": info["desc"],
        }
    
    # --- L4: 飞腾八法 (8维) ---
    labels["L4_飞腾八法"] = {}
    for key, val in FEITENG_BAFA.items():
        labels["L4_飞腾八法"][key] = {"取穴": val}
    
    # --- L5: 五运系统 (5维) ---
    labels["L5_五运系统"] = {}
    for key, info in WUYUN.items():
        labels["L5_五运系统"][f"{key}化{info['运']}"] = {
            "太过不及": info["太过不及"],
            "对应脏腑": info["对应"],
            "特征": info["特征"],
            "本年是否": "✅" if year_gan in key else "❌",
        }
    
    # --- L6: 六气司天在泉 (6维) ---
    labels["L6_六气司天在泉"] = {}
    for key, info in LIUQI_SITIAN.items():
        labels["L6_六气司天在泉"][f"{key}年"] = {
            "司天": info["司天"],
            "在泉": info["在泉"],
            "描述": info["desc"],
            "本年是否": "✅" if year_zhi in key else "❌",
        }
    
    # --- L7: 六气主气 (6维) ---
    labels["L7_六气主气"] = {}
    for zq in LIUQI_ZHUQI:
        labels["L7_六气主气"][zq["name"]] = {
            "时间": zq["time"],
            "五行": zq["wuxing"],
            "描述": zq["desc"],
        }
    
    # --- L8: 十二经纳甲法 (10维) ---
    labels["L8_纳甲法"] = {}
    for gan, info in NAJIA.items():
        labels["L8_纳甲法"][f"{gan}日"] = {
            "经脉": info["经脉"],
            "五行": info["wuxing"],
            "穴位": info["穴位"],
            "本日是否": "✅" if gan == day_gan else "❌",
        }
    
    # --- L9: 十二经纳子法 (12维) ---
    labels["L9_纳子法"] = {}
    for dz in DIZHI:
        labels["L9_纳子法"][f"{dz}时"] = {
            "经脉": NAZI[dz],
            "本时是否": "✅" if dz == hour_zhi else "❌",
        }
    
    # --- L10: 十二消息卦 (12维) ---
    labels["L10_十二消息卦"] = {}
    for dz, info in XIAOXI_GUA.items():
        labels["L10_十二消息卦"][f"{dz}月_{info['卦']}卦"] = {
            "描述": info["desc"],
            "阴阳比": info["阴阳"],
            "本时是否": "✅" if dz == hour_zhi else "❌",
        }
    
    # --- L11: 五行生克与脏腑 (10维) ---
    labels["L11_五行脏腑"] = {
        "木": {"脏腑": "肝胆", "生": "火(心)", "克": "土(脾)", "季节": "春"},
        "火": {"脏腑": "心小肠", "生": "土(脾)", "克": "金(肺)", "季节": "夏"},
        "土": {"脏腑": "脾胃", "生": "金(肺)", "克": "水(肾)", "季节": "长夏"},
        "金": {"脏腑": "肺大肠", "生": "水(肾)", "克": "木(肝)", "季节": "秋"},
        "水": {"脏腑": "肾膀胱", "生": "木(肝)", "克": "火(心)", "季节": "冬"},
    }
    
    # --- L12: 时辰养生建议 (12维) ---
    labels["L12_时辰养生"] = {}
    for dz in DIZHI:
        info = ZIWULIUZHU[dz]
        labels["L12_时辰养生"][f"{dz}时({info['经脉']})"] = {
            "养生要点": info["养生"],
            "经脉五行": info["wuxing"],
            "当令描述": info["desc"],
        }
    
    # --- L13: 六气客气推算 (6维) ---
    labels["L13_六气客气"] = {}
    sitian = liuqi.get("司天", "?")
    for i, qi_name in enumerate(LIUQI_KEQI_ORDER):
        labels["L13_六气客气"][f"第{i+1}气"] = {
            "客气": qi_name,
            "是否司天": "✅" if qi_name == sitian else "❌",
        }
    
    # --- L14: 运气相合分析 (10维) ---
    labels["L14_运气相合"] = {
        "年运": wuyun.get("运", "?"),
        "运太过不及": wuyun.get("太过不及", "?"),
        "司天之气": liuqi.get("司天", "?"),
        "在泉之气": liuqi.get("在泉", "?"),
        "运气关系": "运气同化" if wuyun.get("运","") in str(liuqi.get("司天","")) else "运气异化",
        "对应脏腑": wuyun.get("对应", "?"),
        "特征": wuyun.get("特征", "?"),
        "全年气候": liuqi.get("desc", "?"),
        "养生重点": f"调养{wuyun.get('对应','?')}",
        "疾病倾向": f"{wuyun.get('特征','?')}相关疾病",
    }
    
    # --- L15: 经络流注时序 (12维) ---
    labels["L15_经络流注时序"] = {}
    for i, dz in enumerate(DIZHI):
        info = ZIWULIUZHU[dz]
        next_dz = DIZHI[(i+1) % 12]
        next_info = ZIWULIUZHU[next_dz]
        labels["L15_经络流注时序"][f"{dz}→{next_dz}"] = {
            "从经": info["经脉"],
            "至经": next_info["经脉"],
            "五行关系": f"{info['wuxing']}→{next_info['wuxing']}",
        }
    
    # --- L16: 当令详细分析 (10维) ---
    labels["L16_当令分析"] = {
        "当令时辰": hour_zhi,
        "当令经脉": ziwu.get("经脉", "?"),
        "当令五行": ziwu.get("wuxing", "?"),
        "当令描述": ziwu.get("desc", "?"),
        "当令养生": ziwu.get("养生", "?"),
        "纳甲经脉": najia.get("经脉", "?"),
        "纳甲五行": najia.get("wuxing", "?"),
        "纳子经脉": nazi,
        "消息卦": f"{xiaoxi.get('卦','?')}({xiaoxi.get('desc','?')})",
        "阴阳比": xiaoxi.get("阴阳", "?"),
    }
    
    # --- L17: 盘面总评 (10维) ---
    labels["L17_盘面总评"] = {
        "年运": f"{wuyun.get('运','?')}-{wuyun.get('太过不及','?')}",
        "司天在泉": f"{liuqi.get('司天','?')}/{liuqi.get('在泉','?')}",
        "当令经脉": ziwu.get("经脉", "?"),
        "当令五行": ziwu.get("wuxing", "?"),
        "养生建议": ziwu.get("养生", "?"),
        "运气相合": "同化" if wuyun.get("运","") in str(liuqi.get("司天","")) else "异化",
        "脏腑重点": wuyun.get("对应", "?"),
        "气候特征": wuyun.get("特征", "?"),
        "消息卦象": f"{xiaoxi.get('卦','?')}",
        "综合建议": f"调养{wuyun.get('对应','?')}，{ziwu.get('养生','?')}",
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
    
    labels = generate_zhongyi_labels(year, month, day, hour)
    
    dictionary = {
        "system": "中医术数时间",
        "system_alias": "TCM Chronobiology",
        "title": "子午流注 · 灵龟八法 · 五运六气",
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "timestamp": f"{year}-{month:02d}-{day:02d} {hour:02d}:00",
        "architecture": "解压缩架构: 时间戳 → 中医时间排盘 → 标签向量",
        "description": "中医术数时间系统融合子午流注、灵龟八法、飞腾八法、五运六气、纳甲纳子法，将时间映射到经脉、脏腑、气血运行节律。",
        "total_dimensions": count_dimensions(labels),
        "total_layers": len(labels),
        "layers": labels,
    }
    return dictionary


def generate_labels_from_timestamp(year, month, day, hour=12):
    return generate_dictionary(year, month, day, hour)


if __name__ == "__main__":
    print("=" * 60)
    print("中医术数时间记忆标签字典生成器 v1.0")
    print("解压缩架构: 时间戳 → 中医时间排盘 → 标签向量")
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
    print(f"    日干支: {l1['日干支']}")
    print(f"    时支: {l1['时支']}")
    print(f"    五运: {l1['五运']}")
    print(f"    司天: {l1['司天']}")
    print(f"    在泉: {l1['在泉']}")
    print(f"    当令经脉: {l1['当令经脉']}")
    
    l17 = dictionary["layers"]["L17_盘面总评"]
    print(f"\n    盘面总评:")
    print(f"      年运: {l17['年运']}")
    print(f"      司天在泉: {l17['司天在泉']}")
    print(f"      当令经脉: {l17['当令经脉']}")
    print(f"      综合建议: {l17['综合建议']}")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "zhongyi_label_dictionary.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(output_path) / 1024
    print(f"\n[4] JSON已保存: {output_path}")
    print(f"    文件大小: {file_size:.1f} KB")
    
    print(f"\n[5] 数据验证:")
    assert len(ZIWULIUZHU) == 12
    print(f"    子午流注经脉数: {len(ZIWULIUZHU)} (应为12) ✅")
    assert len(LINGGUI_BAFA) == 8
    print(f"    灵龟八法穴位数: {len(LINGGUI_BAFA)} (应为8) ✅")
    assert len(WUYUN) == 5
    print(f"    五运数量: {len(WUYUN)} (应为5) ✅")
    assert len(LIUQI_SITIAN) == 6
    print(f"    六气司天在泉数: {len(LIUQI_SITIAN)} (应为6) ✅")
    assert len(NAJIA) == 10
    print(f"    纳甲法天干数: {len(NAJIA)} (应为10) ✅")
    assert len(NAZI) == 12
    print(f"    纳子法地支数: {len(NAZI)} (应为12) ✅")
    assert len(XIAOXI_GUA) == 12
    print(f"    十二消息卦数: {len(XIAOXI_GUA)} (应为12) ✅")
    # 验证子时=胆经
    assert ZIWULIUZHU["子"]["经脉"] == "胆经(足少阳胆经)"
    print(f"    子时胆经验证 ✅")
    # 验证五运
    assert WUYUN["甲己"]["运"] == "土运"
    print(f"    甲己化土运验证 ✅")
    
    print("\n" + "=" * 60)
    print("中医术数时间标签字典生成完成!")
    print(f"总维度: {total_dims}维 / 17层 / {file_size:.1f}KB")
    print("=" * 60)

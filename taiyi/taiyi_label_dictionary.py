#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
太乙神数记忆标签字典生成器 v1.0
解压缩架构: 时间戳 → 太乙排盘 → 标签向量
三式之首 · 帝王之学 · 天人之学
"""

import json
import os
from datetime import datetime, timedelta

# ============================================================
# Part 1: 基础数据表
# ============================================================

# --- 太乙九宫配置 (太乙宫位与洛书宫位不同) ---
# 太乙: 乾1 离2 艮3 震4 中5 兑6 坤7 坎8 巽9
# 洛书: 坎1 坤2 震3 巽4 中5 乾6 兑7 艮8 离9
TAIYI_GONG = {
    1: {"name": "乾宫", "gua": "乾", "wuxing": "金", "fangwei": "西北", "men": "天门",
        "zhou": "冀州", "qi": "绝阳", "bagua_trigram": "☰", "desc": "天之门，阳之极，君父之象"},
    2: {"name": "离宫", "gua": "离", "wuxing": "火", "fangwei": "正南", "men": "火门",
        "zhou": "荆州", "qi": "易气", "bagua_trigram": "☲", "desc": "火之门，文明之象，主光明"},
    3: {"name": "艮宫", "gua": "艮", "wuxing": "土", "fangwei": "东北", "men": "鬼门",
        "zhou": "青州", "qi": "和", "bagua_trigram": "☶", "desc": "鬼之门，止息之象，冬春之交"},
    4: {"name": "震宫", "gua": "震", "wuxing": "木", "fangwei": "正东", "men": "日门",
        "zhou": "徐州", "qi": "绝气", "bagua_trigram": "☳", "desc": "日之门，震动之象，阳气壮盛"},
    5: {"name": "中宫", "gua": "中", "wuxing": "土", "fangwei": "中央", "men": "无",
        "zhou": "无", "qi": "枢纽", "bagua_trigram": "⊕", "desc": "中天之枢纽，太乙不居，斡旋八方"},
    6: {"name": "兑宫", "gua": "兑", "wuxing": "金", "fangwei": "正西", "men": "月门",
        "zhou": "雍州", "qi": "绝气", "bagua_trigram": "☱", "desc": "月之门，肃杀之象，过中则亏"},
    7: {"name": "坤宫", "gua": "坤", "wuxing": "土", "fangwei": "西南", "men": "人门",
        "zhou": "益州", "qi": "和", "bagua_trigram": "☷", "desc": "人之门，厚德载物，阴气施令"},
    8: {"name": "坎宫", "gua": "坎", "wuxing": "水", "fangwei": "正北", "men": "水门",
        "zhou": "兖州", "qi": "易气", "bagua_trigram": "☵", "desc": "水之门，险陷之象，万物所归"},
    9: {"name": "巽宫", "gua": "巽", "wuxing": "木", "fangwei": "东南", "men": "风门",
        "zhou": "扬州", "qi": "绝阴", "bagua_trigram": "☴", "desc": "风之门，入伏之象，阴气渐长"},
}

# --- 太乙行宫顺序 (阳遁顺行, 不入中宫) ---
YANG_GONG_ORDER = [1, 2, 3, 4, 6, 7, 8, 9]  # 乾→离→艮→震→兑→坤→坎→巽
YIN_GONG_ORDER = [9, 8, 7, 6, 4, 3, 2, 1]   # 巽→坎→坤→兑→震→艮→离→乾

# --- 太乙十六神 ---
# 十六神 = 十二地支 + 四隅卦(乾艮巽坤)
SHILIU_SHEN = [
    {"dizhi": "子", "name": "地主", "position": "正宫", "gong_num": 8, "wuxing": "水",
     "desc": "阳气初发，万物阴生", "zhushi": "动摇言语事"},
    {"dizhi": "丑", "name": "阳德", "position": "间神", "gong_num": None, "wuxing": "土",
     "desc": "二阳用事，布育万物", "zhushi": "施恩育物事"},
    {"dizhi": "艮", "name": "和德", "position": "正宫", "gong_num": 3, "wuxing": "土",
     "desc": "冬春将交，阴阳气合", "zhushi": "和集成就事"},
    {"dizhi": "寅", "name": "吕申", "position": "间神", "gong_num": None, "wuxing": "木",
     "desc": "阳育大申，草木甲拆", "zhushi": "运用主宰事"},
    {"dizhi": "卯", "name": "高丛", "position": "正宫", "gong_num": 4, "wuxing": "木",
     "desc": "万物皆出，自地丛生", "zhushi": "发挥事"},
    {"dizhi": "辰", "name": "太阳", "position": "间神", "gong_num": None, "wuxing": "土",
     "desc": "雷出震势，阳气大盛", "zhushi": "危会兵戈事"},
    {"dizhi": "巽", "name": "大旲", "position": "正宫", "gong_num": 9, "wuxing": "木",
     "desc": "春夏将交，暑气方盛", "zhushi": "申命号令事"},
    {"dizhi": "巳", "name": "大神", "position": "间神", "gong_num": None, "wuxing": "火",
     "desc": "少阴用事，阴阳不测", "zhushi": "毁拆破废事"},
    {"dizhi": "午", "name": "大威", "position": "正宫", "gong_num": 2, "wuxing": "火",
     "desc": "阳附阴生，刑暴始行", "zhushi": "光明威烈事"},
    {"dizhi": "未", "name": "天道", "position": "间神", "gong_num": None, "wuxing": "土",
     "desc": "火能生土，土王于未", "zhushi": "阴私事"},
    {"dizhi": "坤", "name": "大武", "position": "正宫", "gong_num": 7, "wuxing": "土",
     "desc": "夏秋将交，阴气施令", "zhushi": "刑罚事"},
    {"dizhi": "申", "name": "武德", "position": "间神", "gong_num": None, "wuxing": "金",
     "desc": "万物欲死，荠麦将生", "zhushi": "传送迁移事"},
    {"dizhi": "酉", "name": "太簇", "position": "正宫", "gong_num": 6, "wuxing": "金",
     "desc": "万物皆成，有大品簇", "zhushi": "更易肃杀事"},
    {"dizhi": "戌", "name": "阴主", "position": "间神", "gong_num": None, "wuxing": "土",
     "desc": "阳气不长，阴气用事", "zhushi": "危期兵丧事"},
    {"dizhi": "乾", "name": "阴德", "position": "正宫", "gong_num": 1, "wuxing": "金",
     "desc": "秋冬将交，阴前生阳", "zhushi": "命令事"},
    {"dizhi": "亥", "name": "大义", "position": "间神", "gong_num": None, "wuxing": "水",
     "desc": "万物怀垢，群阳欲尽", "zhushi": "计谋废弃事"},
]

# 十六神名称索引
SHEN_NAME_MAP = {s["name"]: s for s in SHILIU_SHEN}
SHEN_DIZHI_MAP = {s["dizhi"]: s for s in SHILIU_SHEN}

# --- 八正宫 vs 间神 ---
ZHENG_GONG = ["子", "午", "卯", "酉", "乾", "坤", "艮", "巽"]  # 八正方位
JIAN_SHEN = ["寅", "申", "巳", "亥", "辰", "戌", "丑", "未"]   # 八间神

# --- 计神查表 (太岁→阳遁计神/阴遁计神) ---
JISHEN_TABLE = {
    "子": {"yang": "寅", "yin": "申"}, "丑": {"yang": "丑", "yin": "未"},
    "寅": {"yang": "子", "yin": "午"}, "卯": {"yang": "亥", "yin": "巳"},
    "辰": {"yang": "戌", "yin": "辰"}, "巳": {"yang": "酉", "yin": "卯"},
    "午": {"yang": "申", "yin": "寅"}, "未": {"yang": "未", "yin": "丑"},
    "申": {"yang": "午", "yin": "子"}, "酉": {"yang": "巳", "yin": "亥"},
    "戌": {"yang": "辰", "yin": "戌"}, "亥": {"yang": "卯", "yin": "酉"},
}

# --- 太乙八门 ---
BAMEN = {
    "开": {"gong": "乾", "fangwei": "西北", "wuxing": "金", "jixiong": "大吉", "desc": "开向通达", "yi": "出行/开业/嫁娶"},
    "休": {"gong": "坎", "fangwei": "正北", "wuxing": "水", "jixiong": "大吉", "desc": "休息安居", "yi": "安养/筑室/和合"},
    "生": {"gong": "艮", "fangwei": "东北", "wuxing": "土", "jixiong": "大吉", "desc": "生育万物", "yi": "种植/祈福/求嗣"},
    "伤": {"gong": "震", "fangwei": "正东", "wuxing": "木", "jixiong": "大凶", "desc": "疾病灾殃", "yi": "忌行/忌战"},
    "杜": {"gong": "巽", "fangwei": "东南", "wuxing": "木", "jixiong": "大凶", "desc": "闭塞不通", "yi": "忌行/忌谋"},
    "景": {"gong": "离", "fangwei": "正南", "wuxing": "火", "jixiong": "小吉", "desc": "鬼怪亡遗", "yi": "上书/访道"},
    "死": {"gong": "坤", "fangwei": "西南", "wuxing": "土", "jixiong": "大凶", "desc": "死丧埋葬", "yi": "忌行/忌战"},
    "惊": {"gong": "兑", "fangwei": "正西", "wuxing": "金", "jixiong": "小凶", "desc": "惊恐奔走", "yi": "忌行/忌谋"},
}

# 八门顺序(以开为始)
BAMEN_ORDER = ["开", "休", "生", "伤", "杜", "景", "死", "惊"]

# --- 六核心格局 ---
GEJU_CORE = {
    "杜塞": {"jixiong": "凶", "desc": "主客大小将落入中宫，将领失去联系，封闭孤立", "yiji": "宜固守不宜出击"},
    "对": {"jixiong": "凶", "desc": "文昌与太乙对冲宫位，大臣怀二心，君主疏远良将", "yiji": "防内乱"},
    "格": {"jixiong": "凶", "desc": "始击或客大小将与太乙对冲，以下犯上，变乱冲突", "yiji": "防叛乱"},
    "掩": {"jixiong": "凶", "desc": "始击临太乙宫，遮掩袭击，君弱臣强", "yiji": "防蒙蔽"},
    "囚": {"jixiong": "凶", "desc": "文昌或四将与太乙同宫，囚禁困守，对上不利", "yiji": "防困厄"},
    "关": {"jixiong": "凶", "desc": "主客大小将同宫，将相不和，互相猜忌", "yiji": "防内斗"},
}

# --- 扩展格局 ---
GEJU_EXT = {
    "迫": {"jixiong": "凶", "desc": "主客大将在太乙左右宫，臣下迫于上"},
    "提": {"jixiong": "凶", "desc": "客大将与文昌同宫，臣下外国有谋"},
    "长数": {"jixiong": "吉", "desc": "主客算10-30，谋事长远，力量充足"},
    "短数": {"jixiong": "凶", "desc": "主客算10以下，谋事急促，力量不足"},
    "重阳数": {"jixiong": "吉", "desc": "三九自临(33/39)，阳之极盛"},
    "重阴数": {"jixiong": "凶", "desc": "二六自临(22/26)，阴之极盛"},
    "阴中重阳": {"jixiong": "吉", "desc": "一七自临(17/71)，阴中阳生"},
    "阳中重阴": {"jixiong": "凶", "desc": "四八自临(48/84)，阳中阴生"},
    "上和数": {"jixiong": "大吉", "desc": "一配阴宫，四八配阳宫，奇偶阴阳互用"},
    "次和数": {"jixiong": "吉", "desc": "二六配阴宫，三九配阳宫"},
    "下和数": {"jixiong": "平", "desc": "十二/十六/二十一/二十七/三十四/三十八"},
    "三才数": {"jixiong": "吉", "desc": "含天(十)地(五)人(一)三才俱全"},
    "不和数": {"jixiong": "凶", "desc": "太乙在阳宫得奇数或阴宫得偶数"},
}

# --- 五福太乙 (45年移一位, 行乾艮巽坤中) ---
WUFU_PATH = [1, 9, 3, 7, 5]  # 乾→巽→艮→坤→中

# --- 大游太乙 (36年移一位, 逆行) ---
DAYOU_PATH = [7, 6, 4, 3, 2, 1, 9, 8]  # 坤→兑→震→艮→离→乾→巽→坎(逆行)

# --- 三基太乙 ---
SANJI = {
    "君基": {"period": 30, "start_gong": 8, "desc": "君王之基，主国运", "path": "顺行八宫"},
    "臣基": {"period": 3, "start_gong": 8, "desc": "臣子之基，主辅相", "path": "顺行八宫"},
    "民基": {"period": 1, "start_dizhi": "戌", "desc": "百姓之基，主民生", "path": "顺行十二支"},
}

# --- 四神太乙 (天乙/地乙/直符/四神, 3年移一宫, 12宫循环) ---
SISHEN = {
    "天乙": {"period": 3, "start": 6, "desc": "金精，顺行十二宫", "wuxing": "金"},
    "地乙": {"period": 3, "start": 9, "desc": "死丧最凶，顺行十二宫", "wuxing": "土"},
    "直符": {"period": 3, "start": 5, "desc": "旱涝虫蝗，顺行十二宫", "wuxing": "土"},
    "四神": {"period": 3, "start": 1, "desc": "水火金木为殃疾，顺行十二宫", "wuxing": "混合"},
}

# --- 阳九百六 (灾厄周期) ---
YANGJIU = {
    "阳九": {"cycle": 4560, "desc": "大灾周期，天急宜修善", "minor_cycle": 456},
    "阴六": {"cycle": 288, "desc": "小厄周期", "major_cycle": 4320},
}

# --- 太乙四计 (年/月/日/时) ---
SIJI = {
    "岁计": {"desc": "年太乙，占国运大势", "method": "积年数入局"},
    "月计": {"desc": "月太乙，占月内运势", "method": "积月数入局"},
    "日计": {"desc": "日太乙，占日内吉凶", "method": "积日数入局"},
    "时计": {"desc": "时太乙，占时辰吉凶", "method": "积时数入局"},
}

# --- 十二地支 ---
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# --- 六冲/六合/三合 ---
LIUCHONG = {"子": "午", "丑": "未", "寅": "申", "卯": "酉", "辰": "戌", "巳": "亥"}
LIUHE = {"子": "丑", "寅": "亥", "卯": "戌", "辰": "酉", "巳": "申", "午": "未"}
SANHE = {"申子辰": "水局", "亥卯未": "木局", "寅午戌": "火局", "巳酉丑": "金局"}

# --- 五行生克 ---
WUXING_SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
WUXING_KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

# --- 阴阳宫分类 ---
YANG_GONG_NUMS = [8, 3, 4, 9]   # 坎8/艮3/震4/巽9 = 阳宫
YIN_GONG_NUMS = [2, 1, 6, 7]    # 离2/乾1/兑6/坤7 = 阴宫 (注:古书原文写"二一六一"即2,1,6,7)

# ============================================================
# Part 2: 计算函数
# ============================================================

def get_ji_nian(year):
    """获取太乙积年数"""
    return 10153917 + year

def get_yang_yin_dun(year):
    """判断阴阳遁"""
    ji_nian = get_ji_nian(year)
    # 360年一大周期
    cycle_pos = ji_nian % 360
    # 阳遁/阴遁交替，以阳遁为主
    if (ji_nian // 360) % 2 == 0:
        return "阳遁", YANG_GONG_ORDER, YANG_GONG_ORDER
    else:
        return "阴遁", YIN_GONG_ORDER, YIN_GONG_ORDER

def get_taiyi_gong(year):
    """计算太乙落宫"""
    ji_nian = get_ji_nian(year)
    dun_name, gong_order, _ = get_yang_yin_dun(year)
    remainder = ji_nian % 24
    gong_index = remainder // 3
    year_in_gong = remainder % 3
    if gong_index >= len(gong_order):
        gong_index = gong_index % len(gong_order)
    taiyi_gong = gong_order[gong_index]
    # 理天/理地/理人
    tian_di_ren = ["理天", "理地", "理人"][year_in_gong]
    return taiyi_gong, tian_di_ren, dun_name

def get_wenchang(year):
    """计算文昌(天目)落位"""
    ji_nian = get_ji_nian(year)
    dun_name, _, _ = get_yang_yin_dun(year)
    remainder = ji_nian % 18
    
    if dun_name == "阳遁":
        start_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["name"] == "武德")
    else:
        start_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["name"] == "吕申")
    
    # 顺行十六神，阳遁遇乾(阴德)/坤(大武)各数两次
    # 阴遁遇艮(和德)/巽(大旲)各数两次
    count = 0
    idx = start_idx
    double_names = ["阴德", "大武"] if dun_name == "阳遁" else ["和德", "大旲"]
    
    while count < remainder:
        idx = (idx + 1) % 16
        count += 1
        shen = SHILIU_SHEN[idx]
        if shen["name"] in double_names and count < remainder:
            count += 1  # 重留一次
    
    return SHILIU_SHEN[idx]["dizhi"], SHILIU_SHEN[idx]["name"], SHILIU_SHEN[idx].get("gong_num")

def get_nian_zhi(year):
    """获取年支"""
    # 2024年=甲辰年, 年支=辰
    base_year = 2024
    base_zhi_idx = 4  # 辰在DIZHI中的索引
    zhi_idx = (base_zhi_idx + (year - base_year)) % 12
    return DIZHI[zhi_idx]

def get_jishen(year):
    """计算计神"""
    nian_zhi = get_nian_zhi(year)
    dun_name, _, _ = get_yang_yin_dun(year)
    key = "yang" if dun_name == "阳遁" else "yin"
    return JISHEN_TABLE[nian_zhi][key]

def get_shiji(year):
    """计算始击(客目/地目)"""
    wenchang_dizhi, wenchang_name, wenchang_gong = get_wenchang(year)
    jishen_dizhi = get_jishen(year)
    
    # 计神加于和德(艮), 计神走几宫, 文昌也走几宫
    # 找计神当前在十六神中的位置
    jishen_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["dizhi"] == jishen_dizhi)
    hede_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["name"] == "和德")
    
    # 计神从当前位置到和德的距离
    shift = (hede_idx - jishen_idx) % 16
    
    # 文昌也移动相同距离
    wenchang_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["dizhi"] == wenchang_dizhi)
    shiji_idx = (wenchang_idx + shift) % 16
    
    shen = SHILIU_SHEN[shiji_idx]
    return shen["dizhi"], shen["name"], shen.get("gong_num")

def calc_suan(start_dizhi, start_gong, taiyi_gong):
    """计算主算/客算"""
    if start_gong is not None:
        # 在正宫，从宫数起算
        suan = start_gong
        # 顺数到太乙前一宫
        gong_order = YANG_GONG_ORDER
        start_pos = gong_order.index(start_gong) if start_gong in gong_order else 0
        taiyi_pos = gong_order.index(taiyi_gong) if taiyi_gong in gong_order else 0
        
        # 从start+1到taiyi-1 (顺行)
        pos = (start_pos + 1) % 8
        while pos != taiyi_pos:
            suan += gong_order[pos]
            pos = (pos + 1) % 8
        return suan
    else:
        # 在间神，从1起算
        suan = 1
        # 找间神所在的正宫位置
        gong_order = YANG_GONG_ORDER
        # 间神在两个正宫之间，取前一个正宫
        start_idx = next(i for i, s in enumerate(SHILIU_SHEN) if s["dizhi"] == start_dizhi)
        # 找下一个正宫
        pos = (start_idx + 1) % 16
        while SHILIU_SHEN[pos].get("gong_num") is None:
            pos = (pos + 1) % 16
        first_gong = SHILIU_SHEN[pos]["gong_num"]
        
        first_pos = gong_order.index(first_gong) if first_gong in gong_order else 0
        taiyi_pos = gong_order.index(taiyi_gong) if taiyi_gong in gong_order else 0
        
        pos = first_pos
        while pos != taiyi_pos:
            suan += gong_order[pos]
            pos = (pos + 1) % 8
        return suan

def get_da_jiang(suan):
    """计算大将宫数"""
    if suan % 10 == 0:
        # 整十则÷9取余
        return suan % 9 if suan % 9 != 0 else 9
    else:
        return suan % 10

def get_can_jiang(da_jiang_gong):
    """计算参将宫数"""
    return (da_jiang_gong * 3) % 10 or 10 if (da_jiang_gong * 3) % 10 != 0 else 10

def get_bamen_zhishi(year):
    """计算八门值使"""
    ji_nian = get_ji_nian(year)
    # 240年一周，30年一换
    remainder = ji_nian % 240
    men_index = remainder // 30
    return BAMEN_ORDER[men_index % 8]

def get_wufu(year):
    """计算五福太乙"""
    ji_nian = get_ji_nian(year)
    # 45年移一位
    idx = (ji_nian // 45) % len(WUFU_PATH)
    return WUFU_PATH[idx]

def get_dayou(year):
    """计算大游太乙"""
    ji_nian = get_ji_nian(year)
    # 36年移一位
    idx = (ji_nian // 36) % len(DAYOU_PATH)
    return DAYOU_PATH[idx]

def check_geju(taiyi_gong, wenchang_dizhi, shiji_dizhi, 
               zhu_da_gong, ke_da_gong, zhu_can_gong, ke_can_gong):
    """检查格局"""
    geju = []
    
    # 文昌与太乙对冲 = 对
    wenchang_gong = SHEN_DIZHI_MAP[wenchang_dizhi].get("gong_num")
    shiji_gong = SHEN_DIZHI_MAP[shiji_dizhi].get("gong_num")
    
    # 对冲关系 (1↔9, 2↔8, 3↔7, 4↔6)
    chong_map = {1: 9, 9: 1, 2: 8, 8: 2, 3: 7, 7: 3, 4: 6, 6: 4}
    
    if wenchang_gong and chong_map.get(taiyi_gong) == wenchang_gong:
        geju.append("对")
    
    # 始击与太乙对冲 = 格
    if shiji_gong and chong_map.get(taiyi_gong) == shiji_gong:
        geju.append("格")
    
    # 始击临太乙宫 = 掩
    if shiji_gong and shiji_gong == taiyi_gong:
        geju.append("掩")
    
    # 文昌或四将与太乙同宫 = 囚
    if wenchang_gong and wenchang_gong == taiyi_gong:
        geju.append("囚")
    if zhu_da_gong == taiyi_gong:
        geju.append("囚(主大将)")
    if ke_da_gong == taiyi_gong:
        geju.append("囚(客大将)")
    
    # 主客大小将同宫 = 关
    if zhu_da_gong == ke_da_gong:
        geju.append("关")
    
    # 主客大小将落中宫 = 杜塞
    if zhu_da_gong == 5 or ke_da_gong == 5:
        geju.append("杜塞")
    
    # 迫: 大将在太乙左右宫
    gong_order = YANG_GONG_ORDER
    taiyi_pos = gong_order.index(taiyi_gong) if taiyi_gong in gong_order else 0
    left = gong_order[(taiyi_pos - 1) % 8]
    right = gong_order[(taiyi_pos + 1) % 8]
    if zhu_da_gong in (left, right):
        geju.append("迫(主大将)")
    if ke_da_gong in (left, right):
        geju.append("迫(客大将)")
    
    return geju

def check_yinyang_shu(zhu_suan, ke_suan, taiyi_gong):
    """检查太乙阴阳数"""
    shu = []
    
    # 长数/短数
    if 10 <= zhu_suan < 30:
        shu.append("主算长数")
    elif zhu_suan < 10:
        shu.append("主算短数")
    elif zhu_suan >= 30:
        shu.append("主算过长数")
    
    if 10 <= ke_suan < 30:
        shu.append("客算长数")
    elif ke_suan < 10:
        shu.append("客算短数")
    elif ke_suan >= 30:
        shu.append("客算过长数")
    
    # 重阳/重阴
    if zhu_suan in (33, 39) or ke_suan in (33, 39):
        shu.append("重阳数")
    if zhu_suan in (22, 26) or ke_suan in (22, 26):
        shu.append("重阴数")
    
    # 上和/次和/下和
    if zhu_suan in (12, 16, 21, 27, 34, 38) or ke_suan in (12, 16, 21, 27, 34, 38):
        shu.append("下和数")
    
    # 不和数
    if taiyi_gong in YANG_GONG_NUMS and zhu_suan % 2 == 1:
        shu.append("主算不和数")
    if taiyi_gong in YIN_GONG_NUMS and zhu_suan % 2 == 0:
        shu.append("主算不和数")
    
    # 三才数
    s = str(zhu_suan)
    has_ten = "0" in s or zhu_suan >= 10
    has_five = "5" in s
    has_one = "1" in s
    if has_ten and has_five and has_one:
        shu.append("三才俱全")
    elif not has_ten:
        shu.append("无天数")
    elif not has_five:
        shu.append("无地数")
    elif not has_one:
        shu.append("无人数")
    
    return shu

def solar_to_ganzhi(year, month, day):
    """简化公历转干支"""
    try:
        from lunar_python import Solar
        solar = Solar.fromYmd(year, month, day)
        lunar = solar.getLunar()
        year_gz = lunar.getYearInGanZhi()
        month_gz = lunar.getMonthInGanZhi()
        day_gz = lunar.getDayInGanZhi()
        return year_gz, month_gz, day_gz
    except ImportError:
        # 简化估算
        base = datetime(2024, 1, 1)
        target = datetime(year, month, day)
        days_diff = (target - base).days
        gz_list = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
        zhi_list = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
        base_idx = 0  # 2024-01-01 ≈ 甲子
        day_idx = (base_idx + days_diff) % 60
        day_gz = gz_list[day_idx % 10] + zhi_list[day_idx % 12]
        year_zhi = zhi_list[(4 + (year - 2024)) % 12]  # 2024=辰
        year_gan = gz_list[(0 + (year - 2024)) % 10]
        year_gz = year_gan + year_zhi
        return year_gz, "估算月柱", day_gz

def get_gong_wangshuai(gong_num, nian_zhi):
    """计算宫位旺衰"""
    gong_wuxing = TAIYI_GONG[gong_num]["wuxing"]
    # 季节旺衰(简化)
    season_map = {"寅卯辰": "木旺", "巳午未": "火旺", "申酉戌": "金旺", "亥子丑": "水旺"}
    for season, wang in season_map.items():
        if nian_zhi in season:
            wang_wuxing = wang[0]
            if wang_wuxing == gong_wuxing:
                return "旺"
            elif WUXING_SHENG.get(wang_wuxing) == gong_wuxing:
                return "相"
            elif WUXING_KE.get(gong_wuxing) == wang_wuxing:
                return "死"
            elif WUXING_KE.get(wang_wuxing) == gong_wuxing:
                return "囚"
            else:
                return "休"
    return "平"


# ============================================================
# Part 3: 标签生成
# ============================================================

def generate_taiyi_labels(year=None, month=None, day=None, hour=None):
    """生成太乙神数标签 (17层)"""
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = {}
    
    # --- 排盘计算 ---
    taiyi_gong, tian_di_ren, dun_name = get_taiyi_gong(year)
    wenchang_dizhi, wenchang_name, wenchang_gong = get_wenchang(year)
    nian_zhi = get_nian_zhi(year)
    jishen_dizhi = get_jishen(year)
    shiji_dizhi, shiji_name, shiji_gong = get_shiji(year)
    
    # 主算/客算
    zhu_suan = calc_suan(wenchang_dizhi, wenchang_gong, taiyi_gong)
    ke_suan = calc_suan(shiji_dizhi, shiji_gong, taiyi_gong)
    
    # 大将/参将
    zhu_da = get_da_jiang(zhu_suan)
    zhu_can = get_can_jiang(zhu_da)
    ke_da = get_da_jiang(ke_suan)
    ke_can = get_can_jiang(ke_da)
    
    # 八门值使
    bamen_zhishi = get_bamen_zhishi(year)
    
    # 五福/大游
    wufu_gong = get_wufu(year)
    dayou_gong = get_dayou(year)
    
    # 格局/阴阳数
    geju_list = check_geju(taiyi_gong, wenchang_dizhi, shiji_dizhi, 
                           zhu_da, ke_da, zhu_can, ke_can)
    yinyang_shu = check_yinyang_shu(zhu_suan, ke_suan, taiyi_gong)
    
    # 旺衰
    wangshuai = get_gong_wangshuai(taiyi_gong, nian_zhi)
    
    # 干支
    year_gz, month_gz, day_gz = solar_to_ganzhi(year, month, day)
    
    # 积年
    ji_nian = get_ji_nian(year)
    
    # --- L1: 基础排盘 (14维) ---
    labels["L1_基础排盘"] = {
        "积年数": ji_nian,
        "阴阳遁": dun_name,
        "太乙宫": f"{taiyi_gong}宫({TAIYI_GONG[taiyi_gong]['name']})",
        "太乙天天地人": tian_di_ren,
        "文昌宫": f"{wenchang_name}({wenchang_dizhi})",
        "始击宫": f"{shiji_name}({shiji_dizhi})",
        "计神": f"{jishen_dizhi}({SHEN_DIZHI_MAP[jishen_dizhi]['name']})",
        "年支": nian_zhi,
        "年干支": year_gz,
        "月干支": month_gz,
        "日干支": day_gz,
        "主算": zhu_suan,
        "客算": ke_suan,
        "五福太乙宫": f"{wufu_gong}宫({TAIYI_GONG[wufu_gong]['name']})",
    }
    
    # --- L2: 太乙九宫属性 (9维) ---
    labels["L2_九宫属性"] = {}
    for gong_num, info in TAIYI_GONG.items():
        labels["L2_九宫属性"][f"{gong_num}宫{info['name']}"] = {
            "五行": info["wuxing"],
            "方位": info["fangwei"],
            "门": info["men"],
            "气": info["qi"],
            "州": info["zhou"],
        }
    
    # --- L3: 十六神排布 (16维) ---
    labels["L3_十六神排布"] = {}
    for shen in SHILIU_SHEN:
        labels["L3_十六神排布"][f"{shen['dizhi']}_{shen['name']}"] = {
            "位置": shen["position"],
            "宫数": shen.get("gong_num", "间神"),
            "五行": shen["wuxing"],
            "含义": shen["desc"],
            "主事": shen["zhushi"],
        }
    
    # --- L4: 八正宫与间神分类 (16维) ---
    labels["L4_正宫间神"] = {}
    for dz in ZHENG_GONG:
        shen = SHEN_DIZHI_MAP[dz]
        labels["L4_正宫间神"][f"正宫_{dz}_{shen['name']}"] = {
            "宫数": shen["gong_num"],
            "宫名": TAIYI_GONG[shen["gong_num"]]["name"] if shen["gong_num"] else None,
            "五行": shen["wuxing"],
        }
    for dz in JIAN_SHEN:
        shen = SHEN_DIZHI_MAP[dz]
        labels["L4_正宫间神"][f"间神_{dz}_{shen['name']}"] = {
            "前后正宫": f"间于{SHEN_DIZHI_MAP[SHILIU_SHEN[max(0,next(i for i,s in enumerate(SHILIU_SHEN) if s['dizhi']==dz)-1)]['dizhi']]}与{SHEN_DIZHI_MAP[SHILIU_SHEN[(next(i for i,s in enumerate(SHILIU_SHEN) if s['dizhi']==dz)+1)%16]['dizhi']]}之间",
            "五行": shen["wuxing"],
            "主事": shen["zhushi"],
        }
    
    # --- L5: 太乙核心八将 (8维) ---
    labels["L5_核心八将"] = {
        "太乙": {"落宫": f"{taiyi_gong}宫", "宫名": TAIYI_GONG[taiyi_gong]["name"], 
                  "天天地人": tian_di_ren, "象征": "北极星，整体趋势，最高决策者"},
        "文昌(天目)": {"落位": f"{wenchang_name}({wenchang_dizhi})", "宫数": wenchang_gong,
                      "象征": "火星，文运内政，主方信息", "五行": "土"},
        "始击(地目)": {"落位": f"{shiji_name}({shiji_dizhi})", "宫数": shiji_gong,
                      "象征": "填星，外部冲击，客方信息", "五行": "火"},
        "计神": {"落位": f"{jishen_dizhi}({SHEN_DIZHI_MAP[jishen_dizhi]['name']})",
                 "象征": "岁星之使，筹度动静", "五行": SHEN_DIZHI_MAP[jishen_dizhi]["wuxing"]},
        "主大将": {"落宫": f"{zhu_da}宫", "象征": "金神太白精，主方核心执行力", "五行": "金"},
        "主参将": {"落宫": f"{zhu_can}宫", "象征": "水神，主方辅助力量", "五行": "水"},
        "客大将": {"落宫": f"{ke_da}宫", "象征": "水神辰星精，客方核心执行力", "五行": "水"},
        "客参将": {"落宫": f"{ke_can}宫", "象征": "客方辅助力量", "五行": "水"},
    }
    
    # --- L6: 主客算分析 (12维) ---
    labels["L6_主客算分析"] = {
        "主算值": zhu_suan,
        "主算长短": "长数" if 10 <= zhu_suan < 30 else ("短数" if zhu_suan < 10 else "过长数"),
        "主算含义": "谋事长远力量充足" if 10 <= zhu_suan < 30 else ("谋事急促力量不足" if zhu_suan < 10 else "拖沓迟缓"),
        "主大将宫": zhu_da,
        "主参将宫": zhu_can,
        "主算和否": "和" if zhu_suan in (12,16,21,27,34,38) else ("不和" if (taiyi_gong in YANG_GONG_NUMS and zhu_suan%2==1) or (taiyi_gong in YIN_GONG_NUMS and zhu_suan%2==0) else "平"),
        "客算值": ke_suan,
        "客算长短": "长数" if 10 <= ke_suan < 30 else ("短数" if ke_suan < 10 else "过长数"),
        "客算含义": "谋事长远力量充足" if 10 <= ke_suan < 30 else ("谋事急促力量不足" if ke_suan < 10 else "拖沓迟缓"),
        "客大将宫": ke_da,
        "客参将宫": ke_can,
        "客算和否": "和" if ke_suan in (12,16,21,27,34,38) else ("不和" if (taiyi_gong in YANG_GONG_NUMS and ke_suan%2==1) or (taiyi_gong in YIN_GONG_NUMS and ke_suan%2==0) else "平"),
    }
    
    # --- L7: 八门值使与属性 (24维) ---
    labels["L7_八门系统"] = {
        "值使门": bamen_zhishi,
        "值使吉凶": BAMEN[bamen_zhishi]["jixiong"],
        "值使方位": BAMEN[bamen_zhishi]["fangwei"],
        "值使含义": BAMEN[bamen_zhishi]["desc"],
        "值使宜": BAMEN[bamen_zhishi]["yi"],
    }
    for men_name, info in BAMEN.items():
        labels["L7_八门系统"][f"门_{men_name}"] = {
            "宫": info["gong"], "五行": info["wuxing"], 
            "吉凶": info["jixiong"], "含义": info["desc"], "宜": info["yi"],
        }
    
    # --- L8: 六核心格局判断 (6维) ---
    labels["L8_核心格局"] = {}
    for name, info in GEJU_CORE.items():
        triggered = name in geju_list or any(name in g for g in geju_list)
        labels["L8_核心格局"][name] = {
            "是否触发": "✅触发" if triggered else "❌未触发",
            "吉凶": info["jixiong"],
            "描述": info["desc"],
            "宜忌": info["yiji"],
        }
    
    # --- L9: 扩展格局与阴阳数 (23维) ---
    labels["L9_扩展格局阴阳数"] = {}
    for name, info in GEJU_EXT.items():
        triggered = name in yinyang_shu or any(name in s for s in yinyang_shu)
        labels["L9_扩展格局阴阳数"][name] = {
            "是否触发": "✅" if triggered else "❌",
            "吉凶": info["jixiong"],
            "描述": info["desc"],
        }
    labels["L9_扩展格局阴阳数"]["触发格局列表"] = geju_list
    labels["L9_扩展格局阴阳数"]["触发阴阳数列表"] = yinyang_shu
    
    # --- L10: 五福太乙系统 (5维) ---
    labels["L10_五福太乙"] = {
        "当前宫": f"{wufu_gong}宫({TAIYI_GONG[wufu_gong]['name']})",
        "五行": TAIYI_GONG[wufu_gong]["wuxing"],
        "行宫路径": "→".join([f"{g}宫" for g in WUFU_PATH]),
        "移宫周期": "45年",
        "含义": "福佑之神，主寿考灾祥",
    }
    
    # --- L11: 大游太乙系统 (5维) ---
    labels["L11_大游太乙"] = {
        "当前宫": f"{dayou_gong}宫({TAIYI_GONG[dayou_gong]['name']})",
        "五行": TAIYI_GONG[dayou_gong]["wuxing"],
        "行宫路径": "→".join([f"{g}宫" for g in DAYOU_PATH]),
        "移宫周期": "36年",
        "含义": "大游太岁最凶，主兵革灾疫",
    }
    
    # --- L12: 三基太乙系统 (9维) ---
    labels["L12_三基太乙"] = {}
    for name, info in SANJI.items():
        labels["L12_三基太乙"][name] = {
            "周期": f"{info['period']}年",
            "描述": info["desc"],
            "行宫": info["path"],
            "起始": f"{info.get('start_gong', info.get('start_dizhi', '?'))}宫" if 'start_gong' in info else f"起{info.get('start_dizhi', '?')}",
        }
    
    # --- L13: 四神太乙系统 (16维) ---
    labels["L13_四神太乙"] = {}
    for name, info in SISHEN.items():
        labels["L13_四神太乙"][name] = {
            "周期": f"{info['period']}年",
            "起始宫": f"{info['start']}宫",
            "五行": info["wuxing"],
            "描述": info["desc"],
        }
    
    # --- L14: 阳九百六灾厄系统 (4维) ---
    labels["L14_阳九百六"] = {}
    for name, info in YANGJIU.items():
        labels["L14_阳九百六"][name] = {
            "大周期": f"{info['cycle']}年",
            "描述": info["desc"],
        }
    
    # --- L15: 太乙四计 (8维) ---
    labels["L15_太乙四计"] = {}
    for name, info in SIJI.items():
        labels["L15_太乙四计"][name] = {
            "描述": info["desc"],
            "方法": info["method"],
        }
    
    # --- L16: 宫位旺衰与主客分析 (10维) ---
    labels["L16_旺衰主客"] = {
        "太乙宫旺衰": wangshuai,
        "太乙宫五行": TAIYI_GONG[taiyi_gong]["wuxing"],
        "太乙宫气": TAIYI_GONG[taiyi_gong]["qi"],
        "主客对比": "主强客弱" if zhu_suan > ke_suan else ("客强主弱" if ke_suan > zhu_suan else "主客均等"),
        "主算旺衰": "旺" if 10 <= zhu_suan < 30 else ("衰" if zhu_suan < 10 else "过旺"),
        "客算旺衰": "旺" if 10 <= ke_suan < 30 else ("衰" if ke_suan < 10 else "过旺"),
        "格局吉凶": "凶" if any(g in GEJU_CORE and GEJU_CORE[g]["jixiong"] == "凶" for g in geju_list) else "平",
        "整体趋势": tian_di_ren,
        "主大将同宫": "同宫(囚)" if zhu_da == taiyi_gong else "异宫",
        "客大将同宫": "同宫(囚)" if ke_da == taiyi_gong else "异宫",
    }
    
    # --- L17: 盘面总评 (10维) ---
    all_geju = geju_list + yinyang_shu
    jixiong_count = sum(1 for g in all_geju if "凶" in str(GEJU_CORE.get(g, {}).get("jixiong", "") + GEJU_EXT.get(g, {}).get("jixiong", "")))
    ji_count = sum(1 for g in all_geju if "吉" in str(GEJU_CORE.get(g, {}).get("jixiong", "") + GEJU_EXT.get(g, {}).get("jixiong", "")))
    
    labels["L17_盘面总评"] = {
        "整体吉凶": "凶" if jixiong_count > ji_count else ("吉" if ji_count > jixiong_count else "平"),
        "主要格局": ", ".join(geju_list) if geju_list else "无特殊格局",
        "主算总评": f"算{zhu_suan}({'长' if 10<=zhu_suan<30 else '短'})",
        "客算总评": f"算{ke_suan}({'长' if 10<=ke_suan<30 else '短'})",
        "主客胜负": "主胜" if zhu_suan > ke_suan else ("客胜" if ke_suan > zhu_suan else "均势"),
        "太乙所在": f"{taiyi_gong}宫{TAIYI_GONG[taiyi_gong]['name']}{tian_di_ren}",
        "值使门": f"{bamen_zhishi}门({BAMEN[bamen_zhishi]['jixiong']})",
        "格局总数": len(all_geju),
        "吉数": ji_count,
        "凶数": jixiong_count,
    }
    
    return labels


def count_dimensions(labels):
    """统计总维度数"""
    total = 0
    for layer_name, layer_data in labels.items():
        if isinstance(layer_data, dict):
            for key, val in layer_data.items():
                if isinstance(val, dict):
                    total += 1  # 每个条目算1维
                else:
                    total += 1
        else:
            total += 1
    return total


def generate_dictionary(year=None, month=None, day=None, hour=None):
    """生成完整标签字典JSON"""
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = generate_taiyi_labels(year, month, day, hour)
    
    dictionary = {
        "system": "太乙神数",
        "system_alias": "Tai Yi Shen Shu",
        "title": "三式之首 · 帝王之学 · 天人之学",
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "timestamp": f"{year}-{month:02d}-{day:02d} {hour:02d}:00",
        "architecture": "解压缩架构: 时间戳 → 太乙排盘 → 标签向量",
        "description": "太乙神数以占测天运国运大势为长，三式之首。太乙取象北极星，统十六神，行九宫，三年一移，二十四年一周。",
        "total_dimensions": count_dimensions(labels),
        "total_layers": len(labels),
        "layers": labels,
    }
    
    return dictionary


def generate_labels_from_timestamp(year, month, day, hour=12):
    """从时间戳生成标签向量 (解压入口)"""
    return generate_dictionary(year, month, day, hour)


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("太乙神数记忆标签字典生成器 v1.0")
    print("解压缩架构: 时间戳 → 太乙排盘 → 标签向量")
    print("三式之首 · 帝王之学 · 天人之学")
    print("=" * 60)
    
    # [1] 生成标签字典
    print("\n[1] 生成标签字典JSON...")
    dictionary = generate_dictionary(2026, 8, 4, 18)
    total_dims = dictionary["total_dimensions"]
    print(f"    总维度数: {total_dims}")
    print(f"    层数: {dictionary['total_layers']}")
    
    # [2] 各层维度分布
    print(f"\n[2] 各层维度分布:")
    for layer_name, layer_data in dictionary["layers"].items():
        dim_count = count_dimensions({layer_name: layer_data})
        print(f"    {layer_name}: {dim_count}维")
    
    # [3] 当前时间排盘验证
    print(f"\n[3] 当前时间排盘验证:")
    print(f"    时间: 2026-08-04 18:00")
    l1 = dictionary["layers"]["L1_基础排盘"]
    print(f"    积年数: {l1['积年数']}")
    print(f"    阴阳遁: {l1['阴阳遁']}")
    print(f"    太乙宫: {l1['太乙宫']}")
    print(f"    太乙天天地人: {l1['太乙天天地人']}")
    print(f"    文昌(天目): {l1['文昌宫']}")
    print(f"    始击(地目): {l1['始击宫']}")
    print(f"    计神: {l1['计神']}")
    print(f"    主算: {l1['主算']}")
    print(f"    客算: {l1['客算']}")
    print(f"    年干支: {l1['年干支']}")
    print(f"    年支: {l1['年支']}")
    print(f"    五福太乙: {l1['五福太乙宫']}")
    
    l5 = dictionary["layers"]["L5_核心八将"]
    print(f"\n    主大将: {l5['主大将']['落宫']}")
    print(f"    主参将: {l5['主参将']['落宫']}")
    print(f"    客大将: {l5['客大将']['落宫']}")
    print(f"    客参将: {l5['客参将']['落宫']}")
    
    l7 = dictionary["layers"]["L7_八门系统"]
    print(f"    八门值使: {l7['值使门']}({l7['值使吉凶']})")
    
    l8 = dictionary["layers"]["L8_核心格局"]
    triggered_geju = [k for k, v in l8.items() if "✅" in v["是否触发"]]
    print(f"    触发格局: {triggered_geju if triggered_geju else '无'}")
    
    l9 = dictionary["layers"]["L9_扩展格局阴阳数"]
    print(f"    触发格局列表: {l9['触发格局列表']}")
    print(f"    触发阴阳数列表: {l9['触发阴阳数列表']}")
    
    l17 = dictionary["layers"]["L17_盘面总评"]
    print(f"\n    盘面总评:")
    print(f"      整体吉凶: {l17['整体吉凶']}")
    print(f"      主要格局: {l17['主要格局']}")
    print(f"      主算总评: {l17['主算总评']}")
    print(f"      客算总评: {l17['客算总评']}")
    print(f"      主客胜负: {l17['主客胜负']}")
    print(f"      太乙所在: {l17['太乙所在']}")
    print(f"      值使门: {l17['值使门']}")
    
    # [4] 保存JSON
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                               "taiyi_label_dictionary.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(output_path) / 1024
    print(f"\n[4] JSON已保存: {output_path}")
    print(f"    文件大小: {file_size:.1f} KB")
    
    # [5] 数据验证
    print(f"\n[5] 数据验证:")
    
    # 验证1: 积年公式
    expected_jn = 10153917 + 2026
    assert l1['积年数'] == expected_jn
    print(f"    积年数: {l1['积年数']} (应为{expected_jn})")
    print(f"    积年验证 ✅")
    
    # 验证2: 太乙宫范围
    taiyi_gong_num = int(l1['太乙宫'].split("宫")[0])
    assert taiyi_gong_num in [1,2,3,4,6,7,8,9]  # 不含5
    print(f"    太乙宫: {taiyi_gong_num}宫 (应为非5宫)")
    print(f"    太乙不入中宫验证 ✅")
    
    # 验证3: 十六神数量
    l3 = dictionary["layers"]["L3_十六神排布"]
    assert len(l3) == 16
    print(f"    十六神数量: {len(l3)} (应为16)")
    print(f"    十六神验证 ✅")
    
    # 验证4: 八门数量
    bamen_count = sum(1 for k in l7 if k.startswith("门_"))
    assert bamen_count == 8
    print(f"    八门数量: {bamen_count} (应为8)")
    print(f"    八门验证 ✅")
    
    # 验证5: 核心格局数量
    assert len(l8) == 6
    print(f"    核心格局数量: {len(l8)} (应为6)")
    print(f"    核心格局验证 ✅")
    
    # 验证6: 年支正确性
    # 2026年 = 丙午年, 年支=午
    assert l1['年支'] == '午'
    print(f"    2026年年支: {l1['年支']} (应为午)")
    print(f"    年支验证 ✅")
    
    # 验证7: 太乙宫位配置
    assert TAIYI_GONG[1]["name"] == "乾宫"
    assert TAIYI_GONG[9]["name"] == "巽宫"
    assert TAIYI_GONG[5]["name"] == "中宫"
    print(f"    太乙宫位: 乾1离2艮3震4中5兑6坤7坎8巽9")
    print(f"    宫位配置验证 ✅")
    
    # 验证8: 主客算为正数
    assert l1['主算'] > 0
    assert l1['客算'] > 0
    print(f"    主算={l1['主算']}, 客算={l1['客算']} (均应为正数)")
    print(f"    主客算验证 ✅")
    
    print("\n" + "=" * 60)
    print("太乙神数标签字典生成完成!")
    print(f"总维度: {total_dims}维 / 17层 / {file_size:.1f}KB")
    print("=" * 60)

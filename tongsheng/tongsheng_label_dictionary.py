#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通胜择日记忆标签字典生成器 v1.0
解压缩架构: 时间戳 → 通胜择日排盘 → 标签向量
"""

import json
import os
from datetime import datetime

# ============================================================
# Part 1: 基础数据表
# ============================================================

DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# --- 建除十二神 ---
JIANCHU = ["建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭"]
JIANCHU_ATTR = {
    "建": {"jixiong": "黑道", "desc": "万物生育之日", "yi": "赴任/上任", "ji": "动土/开仓"},
    "除": {"jixiong": "黄道", "desc": "除旧布新之日", "yi": "治病/清扫/出行", "ji": "嫁娶"},
    "满": {"jixiong": "黑道", "desc": "丰满圆满之日", "yi": "祭祀/祈福", "ji": "嫁娶/安葬"},
    "平": {"jixiong": "黑道", "desc": "平平无奇之日", "yi": "修造/动土", "ji": "开渠/掘井"},
    "定": {"jixiong": "黄道", "desc": "安定守成之日", "yi": "冠笄/立券/交易", "ji": "出行/词讼"},
    "执": {"jixiong": "黄道", "desc": "执持守固之日", "yi": "捕捉/狩猎", "ji": "开市/立券"},
    "破": {"jixiong": "大凶", "desc": "破坏衰败之日", "yi": "破屋/坏垣", "ji": "万事不宜"},
    "危": {"jixiong": "黄道", "desc": "危险但可成之日", "yi": "祭祀/祈福/安床", "ji": "登山/乘船"},
    "成": {"jixiong": "大吉", "desc": "成就成功之日", "yi": "嫁娶/开市/入学/迁居", "ji": "词讼"},
    "收": {"jixiong": "黑道", "desc": "收敛收藏之日", "yi": "纳财/捕捉/开市", "ji": "出行/安葬"},
    "开": {"jixiong": "大吉", "desc": "开张通达之日", "yi": "开业/嫁娶/出行/迁居", "ji": "安葬"},
    "闭": {"jixiong": "大凶", "desc": "封闭停滞之日", "yi": "筑堤/塞穴", "ji": "万事不宜"},
}

# --- 二十八宿 ---
ERSHIBA_XIU = [
    # 东方青龙七宿(木)
    {"name": "角", "xiang": "青龙", "fangwei": "东", "wuxing": "木", "jixiong": "吉", "desc": "造作婚嫁添人口", "yi": "造作/嫁娶/出行", "ji": "葬埋"},
    {"name": "亢", "xiang": "青龙", "fangwei": "东", "wuxing": "金", "jixiong": "凶", "desc": "婚姻不吉有灾殃", "yi": "祭祀", "ji": "嫁娶/修造"},
    {"name": "氐", "xiang": "青龙", "fangwei": "东", "wuxing": "土", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "种植", "ji": "嫁娶/出行"},
    {"name": "房", "xiang": "青龙", "fangwei": "东", "wuxing": "日", "jixiong": "吉", "desc": "田园进益人口安", "yi": "祈福/嫁娶/造作", "ji": "葬埋"},
    {"name": "心", "xiang": "青龙", "fangwei": "东", "wuxing": "月", "jixiong": "凶", "desc": "凶恶之星惹灾殃", "yi": "祭祀", "ji": "嫁娶/出行"},
    {"name": "尾", "xiang": "青龙", "fangwei": "东", "wuxing": "火", "jixiong": "吉", "desc": "造作百事皆如意", "yi": "造作/嫁娶", "ji": "葬埋"},
    {"name": "箕", "xiang": "青龙", "fangwei": "东", "wuxing": "水", "jixiong": "吉", "desc": "造作仓廪福寿长", "yi": "造仓/掘井", "ji": "嫁娶"},
    # 北方玄武七宿(水)
    {"name": "斗", "xiang": "玄武", "fangwei": "北", "wuxing": "木", "jixiong": "凶", "desc": "婚姻祭祀不吉昌", "yi": "开渠/穿井", "ji": "嫁娶/葬埋"},
    {"name": "牛", "xiang": "玄武", "fangwei": "北", "wuxing": "金", "jixiong": "凶", "desc": "凡事不利有灾殃", "yi": "祭祀", "ji": "嫁娶/动土"},
    {"name": "女", "xiang": "玄武", "fangwei": "北", "wuxing": "土", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "学艺", "ji": "嫁娶/造作"},
    {"name": "虚", "xiang": "玄武", "fangwei": "北", "wuxing": "日", "jixiong": "凶", "desc": "葬埋不可用此日", "yi": "祭祀", "ji": "葬埋/出行"},
    {"name": "危", "xiang": "玄武", "fangwei": "北", "wuxing": "月", "jixiong": "凶", "desc": "凡事不利招灾殃", "yi": "祭祀", "ji": "登山/乘船"},
    {"name": "室", "xiang": "玄武", "fangwei": "北", "wuxing": "火", "jixiong": "吉", "desc": "造作婚嫁福禄昌", "yi": "造作/嫁娶/迁居", "ji": "葬埋"},
    {"name": "壁", "xiang": "玄武", "fangwei": "北", "wuxing": "水", "jixiong": "吉", "desc": "造作嫁娶事事昌", "yi": "造作/嫁娶/入宅", "ji": "葬埋"},
    # 西方白虎七宿(金)
    {"name": "奎", "xiang": "白虎", "fangwei": "西", "wuxing": "木", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "学艺", "ji": "嫁娶/造作"},
    {"name": "娄", "xiang": "白虎", "fangwei": "西", "wuxing": "金", "jixiong": "吉", "desc": "婚姻祭祀大吉昌", "yi": "嫁娶/祭祀/造作", "ji": "葬埋"},
    {"name": "胃", "xiang": "白虎", "fangwei": "西", "wuxing": "土", "jixiong": "吉", "desc": "造作嫁娶福禄昌", "yi": "造作/嫁娶", "ji": "葬埋"},
    {"name": "昴", "xiang": "白虎", "fangwei": "西", "wuxing": "日", "jixiong": "凶", "desc": "凡事不吉有灾殃", "yi": "祭祀", "ji": "嫁娶/出行"},
    {"name": "毕", "xiang": "白虎", "fangwei": "西", "wuxing": "月", "jixiong": "吉", "desc": "造作婚嫁皆如意", "yi": "造作/嫁娶/开市", "ji": "葬埋"},
    {"name": "觜", "xiang": "白虎", "fangwei": "西", "wuxing": "火", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "祭祀", "ji": "嫁娶/动土"},
    {"name": "参", "xiang": "白虎", "fangwei": "西", "wuxing": "水", "jixiong": "吉", "desc": "造作婚嫁福禄昌", "yi": "造作/嫁娶", "ji": "葬埋"},
    # 南方朱雀七宿(火)
    {"name": "井", "xiang": "朱雀", "fangwei": "南", "wuxing": "木", "jixiong": "吉", "desc": "造作婚嫁皆如意", "yi": "造作/嫁娶/祭祀", "ji": "葬埋"},
    {"name": "鬼", "xiang": "朱雀", "fangwei": "南", "wuxing": "金", "jixiong": "凶", "desc": "葬埋不可用此日", "yi": "祭祀", "ji": "嫁娶/葬埋"},
    {"name": "柳", "xiang": "朱雀", "fangwei": "南", "wuxing": "土", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "种植", "ji": "嫁娶/造作"},
    {"name": "星", "xiang": "朱雀", "fangwei": "南", "wuxing": "日", "jixiong": "凶", "desc": "凡事不吉有灾殃", "yi": "祭祀", "ji": "嫁娶/出行"},
    {"name": "张", "xiang": "朱雀", "fangwei": "南", "wuxing": "月", "jixiong": "吉", "desc": "造作婚嫁福禄昌", "yi": "造作/嫁娶/入宅", "ji": "葬埋"},
    {"name": "翼", "xiang": "朱雀", "fangwei": "南", "wuxing": "火", "jixiong": "凶", "desc": "凡事不吉有忧愁", "yi": "祭祀", "ji": "嫁娶/造作"},
    {"name": "轸", "xiang": "朱雀", "fangwei": "南", "wuxing": "水", "jixiong": "吉", "desc": "造作婚嫁事事昌", "yi": "造作/嫁娶/出行", "ji": "葬埋"},
]

# --- 十二黄黑道 (日值天神) ---
HUANG_HEI_DAO = {
    "青龙": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜造作/嫁娶/出行"},
    "明堂": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜造作/嫁娶/上任"},
    "金匮": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜嫁娶/纳财/开市"},
    "天德": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜祈福/祭祀/嫁娶"},
    "玉堂": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜入宅/安床/开市"},
    "司命": {"dao": "黄道", "jixiong": "吉", "desc": "吉神，宜祭祀/祈福/安葬"},
    "白虎": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌嫁娶/出行"},
    "天刑": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌上任/词讼"},
    "朱雀": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌词讼/出行"},
    "天牢": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌祭祀/上任"},
    "玄武": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌嫁娶/安葬"},
    "勾陈": {"dao": "黑道", "jixiong": "凶", "desc": "凶神，忌造作/嫁娶"},
}
HUANG_HEI_ORDER = ["青龙", "明堂", "天刑", "朱雀", "金匮", "天德", "白虎", "玉堂", "天牢", "玄武", "司命", "勾陈"]

# --- 六十甲子纳音五行 (30种) ---
NAYIN = {
    "甲子乙丑": "海中金", "丙寅丁卯": "炉中火", "戊辰己巳": "大林木",
    "庚午辛未": "路旁土", "壬申癸酉": "剑锋金", "甲戌乙亥": "山头火",
    "丙子丁丑": "涧下水", "戊寅己卯": "城头土", "庚辰辛巳": "白蜡金",
    "壬午癸未": "杨柳木", "甲申乙酉": "泉中水", "丙戌丁亥": "屋上土",
    "戊子己丑": "霹雳火", "庚寅辛卯": "松柏木", "壬辰癸巳": "长流水",
    "甲午乙未": "沙中金", "丙申丁酉": "山下火", "戊戌己亥": "平地木",
    "庚子辛丑": "壁上土", "壬寅癸卯": "金箔金", "甲辰乙巳": "覆灯火",
    "丙午丁未": "天河水", "戊申己酉": "大驿土", "庚戌辛亥": "钗钏金",
    "壬子癸丑": "桑柘木", "甲寅乙卯": "大溪水", "丙辰丁巳": "沙中土",
    "戊午己未": "天上火", "庚申辛酉": "石榴木", "壬戌癸亥": "大海水",
}

# --- 六冲/六合/三合/六害 ---
LIUCHONG = {"子":"午","丑":"未","寅":"申","卯":"酉","辰":"戌","巳":"亥"}
LIUHE = {"子":"丑","寅":"亥","卯":"戌","辰":"酉","巳":"申","午":"未"}
LIUHAI = {"子":"未","丑":"午","寅":"巳","卯":"辰","申":"亥","酉":"戌"}
SANHE = {"申子辰":"水局","亥卯未":"木局","寅午戌":"火局","巳酉丑":"金局"}

# --- 三煞 ---
SANSHA = {"申子辰": "巳午未", "亥卯未": "申酉戌", "寅午戌": "亥子丑", "巳酉丑": "寅卯辰"}

# --- 天乙贵人 ---
TIANYI_GUIREN = {"甲":"丑未", "乙":"子申", "丙":"亥酉", "丁":"亥酉", "戊":"丑未", 
                   "己":"子申", "庚":"丑未", "辛":"午寅", "壬":"卯巳", "癸":"卯巳"}

# --- 喜神方位 ---
XISHEN_FANGWEI = {"甲":"艮(东北)", "乙":"乾(西北)", "丙":"坤(西南)", "丁":"离(正南)",
                   "戊":"巽(东南)", "己":"艮(东北)", "庚":"乾(西北)", "辛":"坤(西南)",
                   "壬":"离(正南)", "癸":"巽(东南)"}

# --- 财神方位 ---
CAISHEN_FANGWEI = {"甲":"东北", "乙":"东北", "丙":"正西", "丁":"正西",
                    "戊":"正北", "己":"正北", "庚":"正东", "辛":"正东",
                    "壬":"正南", "癸":"正南"}

# --- 六曜 (日本版，源自小六壬) ---
LIUYAO = ["大安", "赤口", "先胜", "友引", "先负", "佛灭"]
LIUYAO_ATTR = {
    "大安": {"jixiong": "大吉", "desc": "万事大吉", "yi": "婚嫁/开业/搬家/入学"},
    "赤口": {"jixiong": "凶", "desc": "午时吉余凶", "yi": "正午行事", "ji": "火/刃/开业"},
    "先胜": {"jixiong": "吉", "desc": "上午吉下午凶", "yi": "上午急事", "ji": "下午行事"},
    "友引": {"jixiong": "吉", "desc": "早晚吉午凶", "yi": "婚嫁", "ji": "丧事"},
    "先负": {"jixiong": "平", "desc": "上午凶下午吉", "yi": "下午行事", "ji": "上午急事/争讼"},
    "佛灭": {"jixiong": "大凶", "desc": "万事凶", "yi": "无", "ji": "万事不宜"},
}

# --- 二十四山 ---
ERSHISI_SHAN = [
    {"shan": "壬", "gua": "坎", "wuxing": "水", "yuan": "地", "desc": "正北偏东"},
    {"shan": "子", "gua": "坎", "wuxing": "水", "yuan": "天", "desc": "正北"},
    {"shan": "癸", "gua": "坎", "wuxing": "水", "yuan": "人", "desc": "正北偏西"},
    {"shan": "丑", "gua": "艮", "wuxing": "土", "yuan": "天", "desc": "东北偏北"},
    {"shan": "艮", "gua": "艮", "wuxing": "土", "yuan": "人", "desc": "东北"},
    {"shan": "寅", "gua": "艮", "wuxing": "土", "yuan": "地", "desc": "东北偏东"},
    {"shan": "甲", "gua": "震", "wuxing": "木", "yuan": "地", "desc": "正东偏北"},
    {"shan": "卯", "gua": "震", "wuxing": "木", "yuan": "天", "desc": "正东"},
    {"shan": "乙", "gua": "震", "wuxing": "木", "yuan": "人", "desc": "正东偏南"},
    {"shan": "辰", "gua": "巽", "wuxing": "木", "yuan": "天", "desc": "东南偏东"},
    {"shan": "巽", "gua": "巽", "wuxing": "木", "yuan": "人", "desc": "东南"},
    {"shan": "巳", "gua": "巽", "wuxing": "木", "yuan": "地", "desc": "东南偏南"},
    {"shan": "丙", "gua": "离", "wuxing": "火", "yuan": "地", "desc": "正南偏东"},
    {"shan": "午", "gua": "离", "wuxing": "火", "yuan": "天", "desc": "正南"},
    {"shan": "丁", "gua": "离", "wuxing": "火", "yuan": "人", "desc": "正南偏西"},
    {"shan": "未", "gua": "坤", "wuxing": "土", "yuan": "天", "desc": "西南偏南"},
    {"shan": "坤", "gua": "坤", "wuxing": "土", "yuan": "人", "desc": "西南"},
    {"shan": "申", "gua": "坤", "wuxing": "土", "yuan": "地", "desc": "西南偏西"},
    {"shan": "庚", "gua": "兑", "wuxing": "金", "yuan": "地", "desc": "正西偏南"},
    {"shan": "酉", "gua": "兑", "wuxing": "金", "yuan": "天", "desc": "正西"},
    {"shan": "辛", "gua": "兑", "wuxing": "金", "yuan": "人", "desc": "正西偏北"},
    {"shan": "戌", "gua": "乾", "wuxing": "金", "yuan": "天", "desc": "西北偏西"},
    {"shan": "乾", "gua": "乾", "wuxing": "金", "yuan": "人", "desc": "西北"},
    {"shan": "亥", "gua": "乾", "wuxing": "金", "yuan": "地", "desc": "西北偏北"},
]

# --- 五行生克 ---
WUXING_SHENG = {"金":"水","水":"木","木":"火","火":"土","土":"金"}
WUXING_KE = {"金":"木","木":"土","土":"水","水":"火","火":"金"}

# --- 月建 (正月建寅) ---
YUEJIAN = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

# --- 四离四绝 ---
SLJJ = {
    "四离": ["春分", "夏至", "秋分", "冬至"],
    "四绝": ["立春", "立夏", "立秋", "立冬"],
    "desc": "季节交替大凶之日，逢吉不吉逢凶必凶"
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
        gz_list = TIANGAN
        zhi_list = DIZHI
        base_idx = 0
        day_idx = (base_idx + days_diff) % 60
        day_gan = gz_list[day_idx % 10]
        day_zhi = zhi_list[day_idx % 12]
        day_gz = day_gan + day_zhi
        year_zhi = zhi_list[(4 + (year - 2024)) % 12]
        year_gan = gz_list[(0 + (year - 2024)) % 10]
        return (year_gan + year_zhi, "估算", day_gz, day_gan, day_zhi)

def get_jianchu(day_zhi, month_zhi):
    """计算建除十二神"""
    jian_pos = DIZHI.index(month_zhi) if month_zhi in DIZHI else 0
    day_pos = DIZHI.index(day_zhi) if day_zhi in DIZHI else 0
    offset = (day_pos - jian_pos) % 12
    return JIANCHU[offset]

def get_xiu(day_gan_zhi_index):
    """计算二十八宿值日 (简化)"""
    # 以角宿为基准, 28天循环
    return ERSHIBA_XIU[day_gan_zhi_index % 28]

def get_huang_hei_dao(day_gan, day_zhi):
    """计算黄黑道 (简化: 以日支起青龙)"""
    # 青龙起子时, 按日支轮转
    zhi_idx = DIZHI.index(day_zhi) if day_zhi in DIZHI else 0
    return HUANG_HEI_ORDER[zhi_idx % 12]

def get_nayin(day_gan, day_zhi):
    """获取纳音五行"""
    key = day_gan + day_zhi
    for k, v in NAYIN.items():
        if key in k:
            return v
    return "未知"

def get_liuyao(lunar_month, lunar_day):
    """计算六曜"""
    remainder = (lunar_month + lunar_day) % 6
    return LIUYAO[remainder]

def get_richong(day_zhi):
    """计算日冲"""
    return LIUCHONG.get(day_zhi, "未知")

def get_riha(day_zhi):
    """计算日害"""
    return LIUHAI.get(day_zhi, "未知")

def get_sui_po(year_zhi, day_zhi):
    """检查岁破"""
    year_chong = LIUCHONG.get(year_zhi, "")
    if day_zhi == year_chong:
        return True
    return False

def get_yue_po(month_zhi, day_zhi):
    """检查月破"""
    month_chong = LIUCHONG.get(month_zhi, "")
    if day_zhi == month_chong:
        return True
    return False

def get_san_sha_fangwei(year_zhi):
    """获取三煞方位"""
    for k, v in SANSHA.items():
        if year_zhi in k:
            return v
    return "未知"


# ============================================================
# Part 3: 标签生成
# ============================================================

def generate_tongsheng_labels(year=None, month=None, day=None, hour=None):
    """生成通胜择日标签 (17层)"""
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = {}
    
    # 排盘计算
    year_gz, month_gz, day_gz, day_gan, day_zhi = solar_to_ganzhi(year, month, day)
    year_zhi = year_gz[-1] if len(year_gz) >= 2 else "?"
    month_zhi = month_gz[-1] if len(month_gz) >= 2 else "?"
    
    # 简化: 取日柱索引
    base = datetime(2024, 1, 1)
    target = datetime(year, month, day)
    days_diff = (target - base).days
    day_index = days_diff % 60
    
    jianchu = get_jianchu(day_zhi, month_zhi)
    xiu = get_xiu(day_index % 28)
    huang_hei = get_huang_hei_dao(day_gan, day_zhi)
    nayin = get_nayin(day_gan, day_zhi)
    richong = get_richong(day_zhi)
    riha = get_riha(day_zhi)
    is_sui_po = get_sui_po(year_zhi, day_zhi)
    is_yue_po = get_yue_po(month_zhi, day_zhi)
    san_sha = get_san_sha_fangwei(year_zhi)
    
    # 六曜 (简化估算)
    liuyao = get_liuyao(month, day)
    
    # 喜神/财神
    xishen = XISHEN_FANGWEI.get(day_gan, "未知")
    caishen = CAISHEN_FANGWEI.get(day_gan, "未知")
    tianyi = TIANYI_GUIREN.get(day_gan, "未知")
    
    # --- L1: 基础排盘 (16维) ---
    labels["L1_基础排盘"] = {
        "年干支": year_gz,
        "月干支": month_gz,
        "日干支": day_gz,
        "日干": day_gan,
        "日支": day_zhi,
        "年支": year_zhi,
        "月支": month_zhi,
        "建除值日": jianchu,
        "二十八宿值日": f"{xiu['name']}宿({xiu['xiang']})",
        "黄黑道": huang_hei,
        "纳音五行": nayin,
        "六曜": liuyao,
        "日冲": f"冲{richong}",
        "日害": f"害{riha}",
        "喜神方位": xishen,
        "财神方位": caishen,
    }
    
    # --- L2: 建除十二神属性 (12维) ---
    labels["L2_建除十二神"] = {}
    for name, attr in JIANCHU_ATTR.items():
        labels["L2_建除十二神"][name] = {
            "黄黑道": attr["jixiong"],
            "描述": attr["desc"],
            "宜": attr["yi"],
            "忌": attr["ji"],
            "今日是否值日": "✅" if name == jianchu else "❌",
        }
    
    # --- L3: 二十八宿完整属性 (28维) ---
    labels["L3_二十八宿"] = {}
    for xiu_info in ERSHIBA_XIU:
        labels["L3_二十八宿"][f"{xiu_info['name']}宿"] = {
            "四象": xiu_info["xiang"],
            "方位": xiu_info["fangwei"],
            "五行": xiu_info["wuxing"],
            "吉凶": xiu_info["jixiong"],
            "描述": xiu_info["desc"],
            "宜": xiu_info["yi"],
            "忌": xiu_info["ji"],
            "今日是否值日": "✅" if xiu_info["name"] == xiu["name"] else "❌",
        }
    
    # --- L4: 黄黑道十二神 (12维) ---
    labels["L4_黄黑道神"] = {}
    for name, attr in HUANG_HEI_DAO.items():
        labels["L4_黄黑道神"][name] = {
            "道": attr["dao"],
            "吉凶": attr["jixiong"],
            "描述": attr["desc"],
            "今日是否值日": "✅" if name == huang_hei else "❌",
        }
    
    # --- L5: 六十甲子纳音五行 (30维) ---
    labels["L5_纳音五行"] = {}
    for k, v in NAYIN.items():
        labels["L5_纳音五行"][k] = {
            "纳音": v,
            "五行": v[-1] if v else "?",
            "今日纳音": "✅" if v == nayin else "❌",
        }
    
    # --- L6: 六曜系统 (6维) ---
    labels["L6_六曜系统"] = {}
    for name, attr in LIUYAO_ATTR.items():
        labels["L6_六曜系统"][name] = {
            "吉凶": attr["jixiong"],
            "描述": attr["desc"],
            "宜": attr.get("yi", ""),
            "忌": attr.get("ji", ""),
            "今日六曜": "✅" if name == liuyao else "❌",
        }
    
    # --- L7: 二十四山系统 (24维) ---
    labels["L7_二十四山"] = {}
    for shan_info in ERSHISI_SHAN:
        labels["L7_二十四山"][shan_info["shan"]] = {
            "卦": shan_info["gua"],
            "五行": shan_info["wuxing"],
            "三元": shan_info["yuan"],
            "方位": shan_info["desc"],
        }
    
    # --- L8: 神煞系统-吉神 (12维) ---
    labels["L8_吉神系统"] = {
        "天乙贵人": {"方位": tianyi, "desc": "万福之神，最强贵人星"},
        "喜神": {"方位": xishen, "desc": "主姻缘喜乐"},
        "财神": {"方位": caishen, "desc": "主财运"},
        "天德": {"desc": "天德贵人，逢凶化吉"},
        "月德": {"desc": "月德贵人，万事可为"},
        "岁德": {"desc": "岁德星，年吉神"},
        "天赦": {"desc": "天赦日，百无禁忌"},
        "福星": {"desc": "福星贵人"},
        "天官": {"desc": "天官贵人，赐福之神"},
        "青龙": {"desc": "黄道吉神之首"},
        "明堂": {"desc": "黄道吉神"},
        "金匮": {"desc": "黄道吉神，主财"},
    }
    
    # --- L9: 神煞系统-凶煞 (12维) ---
    labels["L9_凶煞系统"] = {
        "太岁": {"方位": year_zhi, "desc": "年最大凶神", "今日冲太岁": "✅" if is_sui_po else "❌"},
        "岁破": {"desc": "与太岁对冲之日", "今日是否岁破": "✅" if is_sui_po else "❌"},
        "月破": {"desc": "与月建对冲之日", "今日是否月破": "✅" if is_yue_po else "❌"},
        "三煞": {"方位": san_sha, "desc": "年三煞方位"},
        "日冲": {"冲": richong, "desc": f"今日冲{richong}"},
        "日害": {"害": riha, "desc": f"今日害{riha}"},
        "四离四绝": {"desc": "季节交替大凶", "日期": str(SLJJ)},
        "白虎": {"desc": "黑道凶神"},
        "天刑": {"desc": "黑道凶神"},
        "朱雀": {"desc": "黑道凶神"},
        "天牢": {"desc": "黑道凶神"},
        "玄武": {"desc": "黑道凶神"},
    }
    
    # --- L10: 六冲六合三合 (12维) ---
    labels["L10_地支关系"] = {}
    for dz in DIZHI:
        labels["L10_地支关系"][dz] = {
            "六冲": LIUCHONG.get(dz, ""),
            "六合": LIUHE.get(dz, ""),
            "六害": LIUHAI.get(dz, ""),
        }
    
    # --- L11: 三合局与三煞 (8维) ---
    labels["L11_三合三煞"] = {}
    for k, v in SANHE.items():
        labels["L11_三合三煞"][f"三合_{k}"] = {"局": v, "desc": f"{k}三合{v}"}
    for k, v in SANSHA.items():
        labels["L11_三合三煞"][f"三煞_{k}"] = {"煞方": v, "desc": f"{k}年三煞在{v}"}
    
    # --- L12: 择日宜忌分析 (10维) ---
    jianchu_attr = JIANCHU_ATTR.get(jianchu, {})
    xiu_attr = next((x for x in ERSHIBA_XIU if x["name"] == xiu["name"]), {})
    huang_hei_attr = HUANG_HEI_DAO.get(huang_hei, {})
    
    labels["L12_择日宜忌"] = {
        "建除宜": jianchu_attr.get("yi", ""),
        "建除忌": jianchu_attr.get("ji", ""),
        "建除吉凶": jianchu_attr.get("jixiong", ""),
        "星宿宜": xiu_attr.get("yi", ""),
        "星宿忌": xiu_attr.get("ji", ""),
        "星宿吉凶": xiu_attr.get("jixiong", ""),
        "黄黑道吉凶": huang_hei_attr.get("jixiong", ""),
        "岁破": "是" if is_sui_po else "否",
        "月破": "是" if is_yue_po else "否",
        "综合吉凶": "凶" if (is_sui_po or is_yue_po or jianchu in ("破","闭")) else ("吉" if jianchu in ("成","开","除","危","定","执") and huang_hei_attr.get("jixiong")=="吉" else "平"),
    }
    
    # --- L13: 五行生克分析 (10维) ---
    labels["L13_五行分析"] = {
        "日干五行": TIANGAN.index(day_gan) % 5 if day_gan in TIANGAN else 0,
        "日支五行": DIZHI.index(day_zhi) % 12 if day_zhi in DIZHI else 0,
        "纳音五行": nayin,
        "纳音属性": nayin[-1] if nayin and len(nayin) > 0 else "?",
        "日干生": WUXING_SHENG.get(nayin[-1] if nayin else "", ""),
        "日干克": WUXING_KE.get(nayin[-1] if nayin else "", ""),
        "年支五行": "未知",
        "月支五行": "未知",
        "日支冲": richong,
        "日支合": LIUHE.get(day_zhi, ""),
    }
    
    # --- L14: 时辰择吉 (12维) ---
    labels["L14_时辰择吉"] = {}
    # 十二时辰黄黑道 (以日支起子时)
    for i, dz in enumerate(DIZHI):
        shen_name = HUANG_HEI_ORDER[(DIZHI.index(day_zhi) + i) % 12] if day_zhi in DIZHI else "?"
        shen_attr = HUANG_HEI_DAO.get(shen_name, {})
        labels["L14_时辰择吉"][f"{dz}时"] = {
            "值神": shen_name,
            "黄黑道": shen_attr.get("dao", ""),
            "吉凶": shen_attr.get("jixiong", ""),
        }
    
    # --- L15: 民俗择日要点 (10维) ---
    labels["L15_民俗择日"] = {
        "建除口诀": "建满平收黑，除危定执黄；成开皆可用，闭破不相当",
        "今日建除": f"{jianchu}日({jianchu_attr.get('jixiong','')})",
        "今日星宿": f"{xiu['name']}宿({xiu['jixiong']})",
        "今日黄黑道": f"{huang_hei}({huang_hei_attr.get('jixiong','')})",
        "今日纳音": nayin,
        "今日六曜": f"{liuyao}({LIUYAO_ATTR[liuyao]['jixiong']})",
        "岁破日": "是" if is_sui_po else "否",
        "月破日": "是" if is_yue_po else "否",
        "日冲生肖": f"冲{richong}",
        "综合建议": "诸事不宜" if (is_sui_po or is_yue_po or jianchu in ("破","闭")) else ("宜" + jianchu_attr.get("yi","")),
    }
    
    # --- L16: 二十八宿分类宜忌 (7维) ---
    labels["L16_星宿分类"] = {
        "木宿(角井奎斗)": {"宜": "开业嫁娶栽种", "忌": "拆屋伐木"},
        "金宿(亢鬼娄牛)": {"宜": "讨债签约五金", "忌": "破土放贷"},
        "土宿(氐柳胃女)": {"宜": "建房安葬囤货", "忌": "迁居拆改"},
        "日宿(房星昴虚)": {"宜": "祈福出行开市", "忌": "官非久病"},
        "月宿(心张毕危)": {"宜": "经商求医水产", "忌": "破土造坟"},
        "火宿(尾翼觜室)": {"宜": "拆旧冶炼驱邪", "忌": "入宅蓄水"},
        "水宿(箕轸参壁)": {"宜": "开渠水路远行", "忌": "生火筑台"},
    }
    
    # --- L17: 盘面总评 (10维) ---
    ji_count = 0
    xiong_count = 0
    if jianchu_attr.get("jixiong") in ("黄道", "大吉"): ji_count += 1
    elif jianchu_attr.get("jixiong") in ("黑道", "大凶"): xiong_count += 1
    if xiu_attr.get("jixiong") == "吉": ji_count += 1
    elif xiu_attr.get("jixiong") == "凶": xiong_count += 1
    if huang_hei_attr.get("jixiong") == "吉": ji_count += 1
    elif huang_hei_attr.get("jixiong") == "凶": xiong_count += 1
    if LIUYAO_ATTR[liuyao]["jixiong"] in ("大吉", "吉"): ji_count += 1
    elif LIUYAO_ATTR[liuyao]["jixiong"] in ("大凶", "凶"): xiong_count += 1
    if is_sui_po: xiong_count += 2
    if is_yue_po: xiong_count += 1
    
    labels["L17_盘面总评"] = {
        "整体吉凶": "吉" if ji_count > xiong_count else ("凶" if xiong_count > ji_count else "平"),
        "建除总评": f"{jianchu}日-{jianchu_attr.get('jixiong','')}",
        "星宿总评": f"{xiu['name']}宿-{xiu['jixiong']}",
        "黄黑道总评": f"{huang_hei}-{huang_hei_attr.get('jixiong','')}",
        "六曜总评": f"{liuyao}-{LIUYAO_ATTR[liuyao]['jixiong']}",
        "纳音": nayin,
        "日冲": f"冲{richong}",
        "吉数": ji_count,
        "凶数": xiong_count,
        "综合建议": "诸事不宜" if xiong_count >= 3 else ("大吉日" if ji_count >= 4 else "平日常规"),
    }
    
    return labels


def count_dimensions(labels):
    """统计总维度数"""
    total = 0
    for layer_name, layer_data in labels.items():
        if isinstance(layer_data, dict):
            total += len(layer_data)
        else:
            total += 1
    return total


def generate_dictionary(year=None, month=None, day=None, hour=None):
    """生成完整标签字典JSON"""
    if year is None:
        now = datetime.now()
        year, month, day, hour = now.year, now.month, now.day, now.hour
    
    labels = generate_tongsheng_labels(year, month, day, hour)
    
    dictionary = {
        "system": "通胜择日",
        "system_alias": "Tong Shu Date Selection",
        "title": "建除十二神 · 二十八宿 · 黄黑道 · 神煞系统",
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "timestamp": f"{year}-{month:02d}-{day:02d} {hour:02d}:00",
        "architecture": "解压缩架构: 时间戳 → 通胜择日排盘 → 标签向量",
        "description": "通胜择日融合建除十二神、二十八宿值日、黄黑道、神煞、纳音五行、六曜等系统，为日常活动提供择吉参考。",
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
    print("通胜择日记忆标签字典生成器 v1.0")
    print("解压缩架构: 时间戳 → 通胜择日排盘 → 标签向量")
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
    print(f"    月干支: {l1['月干支']}")
    print(f"    日干支: {l1['日干支']}")
    print(f"    建除值日: {l1['建除值日']}")
    print(f"    二十八宿: {l1['二十八宿值日']}")
    print(f"    黄黑道: {l1['黄黑道']}")
    print(f"    纳音: {l1['纳音五行']}")
    print(f"    六曜: {l1['六曜']}")
    print(f"    日冲: {l1['日冲']}")
    print(f"    喜神: {l1['喜神方位']}")
    print(f"    财神: {l1['财神方位']}")
    
    l17 = dictionary["layers"]["L17_盘面总评"]
    print(f"\n    盘面总评:")
    print(f"      整体吉凶: {l17['整体吉凶']}")
    print(f"      建除总评: {l17['建除总评']}")
    print(f"      星宿总评: {l17['星宿总评']}")
    print(f"      黄黑道总评: {l17['黄黑道总评']}")
    print(f"      六曜总评: {l17['六曜总评']}")
    print(f"      综合建议: {l17['综合建议']}")
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "tongsheng_label_dictionary.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(output_path) / 1024
    print(f"\n[4] JSON已保存: {output_path}")
    print(f"    文件大小: {file_size:.1f} KB")
    
    print(f"\n[5] 数据验证:")
    
    # 验证1: 建除十二神
    assert len(JIANCHU) == 12
    print(f"    建除十二神数量: {len(JIANCHU)} (应为12) ✅")
    
    # 验证2: 二十八宿
    assert len(ERSHIBA_XIU) == 28
    print(f"    二十八宿数量: {len(ERSHIBA_XIU)} (应为28) ✅")
    
    # 验证3: 黄黑道
    assert len(HUANG_HEI_DAO) == 12
    huang_count = sum(1 for v in HUANG_HEI_DAO.values() if v["dao"]=="黄道")
    hei_count = sum(1 for v in HUANG_HEI_DAO.values() if v["dao"]=="黑道")
    assert huang_count == 6 and hei_count == 6
    print(f"    黄道{huang_count}位+黑道{hei_count}位=12神 ✅")
    
    # 验证4: 纳音
    assert len(NAYIN) == 30
    print(f"    纳音五行数量: {len(NAYIN)} (应为30) ✅")
    
    # 验证5: 二十四山
    assert len(ERSHISI_SHAN) == 24
    print(f"    二十四山数量: {len(ERSHISI_SHAN)} (应为24) ✅")
    
    # 验证6: 六曜
    assert len(LIUYAO) == 6
    print(f"    六曜数量: {len(LIUYAO)} (应为6) ✅")
    
    # 验证7: 六冲六合
    assert len(LIUCHONG) == 6 and len(LIUHE) == 6
    assert LIUCHONG["子"] == "午" and LIUHE["子"] == "丑"
    print(f"    子午冲/子丑合 验证 ✅")
    
    # 验证8: 天乙贵人
    assert TIANYI_GUIREN["甲"] == "丑未"
    print(f"    甲日天乙贵人=丑未 ✅")
    
    print("\n" + "=" * 60)
    print("通胜择日标签字典生成完成!")
    print(f"总维度: {total_dims}维 / 17层 / {file_size:.1f}KB")
    print("=" * 60)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字四柱记忆标签字典生成器 (BaZi Label Dictionary Generator)
系统②: 八字四柱 - 全术数记忆维度体系
解压方法: 公历时间→四柱排盘→多维标签向量
"""

import json
import os
from datetime import datetime as dt, date
from collections import Counter

# ============================================================
# Part 1: 基础数据表
# ============================================================

# --- 天干 ---
TIANGAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
GAN_WX = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
GAN_YY = {'甲':'阳','乙':'阴','丙':'阳','丁':'阴','戊':'阳','己':'阴','庚':'阳','辛':'阴','壬':'阳','癸':'阴'}
GAN_FANG = {'甲':'东','乙':'东','丙':'南','丁':'南','戊':'中','己':'中','庚':'西','辛':'西','壬':'北','癸':'北'}
GAN_SEASON = {'甲':'春','乙':'春','丙':'夏','丁':'夏','戊':'长夏','己':'长夏','庚':'秋','辛':'秋','壬':'冬','癸':'冬'}
GAN_WUCHANG = {'甲':'仁','乙':'仁','丙':'礼','丁':'礼','戊':'信','己':'信','庚':'义','辛':'义','壬':'智','癸':'智'}

# --- 地支 ---
DIZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
ZHI_WX = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}
ZHI_YY = {'子':'阳','丑':'阴','寅':'阳','卯':'阴','辰':'阳','巳':'阴','午':'阳','未':'阴','申':'阳','酉':'阴','戌':'阳','亥':'阴'}
ZHI_SX = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇','午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'}
ZHI_FANG = {'子':'北','丑':'东北','寅':'东北','卯':'东','辰':'东南','巳':'东南','午':'南','未':'西南','申':'西南','酉':'西','戌':'西北','亥':'西北'}
ZHI_HOUR = {'子':'23-1','丑':'1-3','寅':'3-5','卯':'5-7','辰':'7-9','巳':'9-11','午':'11-13','未':'13-15','申':'15-17','酉':'17-19','戌':'19-21','亥':'21-23'}
ZHI_MONTH = {'寅':'正月','卯':'二月','辰':'三月','巳':'四月','午':'五月','未':'六月','申':'七月','酉':'八月','戌':'九月','亥':'十月','子':'十一月','丑':'十二月'}

# --- 藏干 ---
ZHI_CANG = {
    '子': [('癸','本气')],
    '丑': [('己','本气'),('癸','中气'),('辛','余气')],
    '寅': [('甲','本气'),('丙','中气'),('戊','余气')],
    '卯': [('乙','本气')],
    '辰': [('戊','本气'),('乙','中气'),('癸','余气')],
    '巳': [('丙','本气'),('庚','中气'),('戊','余气')],
    '午': [('丁','本气'),('己','中气')],
    '未': [('己','本气'),('丁','中气'),('乙','余气')],
    '申': [('庚','本气'),('壬','中气'),('戊','余气')],
    '酉': [('辛','本气')],
    '戌': [('戊','本气'),('辛','中气'),('丁','余气')],
    '亥': [('壬','本气'),('甲','中气')],
}

# --- 五行 ---
WX = ['木','火','土','金','水']
WX_SHENG = {'木':'火','火':'土','土':'金','金':'水','水':'木'}
WX_KE = {'木':'土','火':'金','土':'水','金':'木','水':'火'}
WX_FANG = {'木':'东','火':'南','土':'中','金':'西','水':'北'}
WX_SEASON = {'木':'春','火':'夏','土':'长夏','金':'秋','水':'冬'}
WX_COLOR = {'木':'青','火':'赤','土':'黄','金':'白','水':'黑'}
WX_TASTE = {'木':'酸','火':'苦','土':'甘','金':'辛','水':'咸'}
WX_EMOTION = {'木':'怒','火':'喜','土':'思','金':'悲','水':'恐'}
WX_ORGAN = {'木':'肝','火':'心','土':'脾','金':'肺','水':'肾'}
WX_WUCHANG = {'木':'仁','火':'礼','土':'信','金':'义','水':'智'}

# --- 天干五合 ---
GAN_HE = {('甲','己'):'化土',('己','甲'):'化土',('乙','庚'):'化金',('庚','乙'):'化金',
          ('丙','辛'):'化水',('辛','丙'):'化水',('丁','壬'):'化木',('壬','丁'):'化木',
          ('戊','癸'):'化火',('癸','戊'):'化火'}

# --- 天干相冲 ---
GAN_CHONG = [('甲','庚'),('乙','辛'),('丙','壬'),('丁','癸')]

# --- 地支六合 ---
ZHI_LIUHE = {('子','丑'):'化土',('丑','子'):'化土',('寅','亥'):'化木',('亥','寅'):'化木',
              ('卯','戌'):'化火',('戌','卯'):'化火',('辰','酉'):'化金',('酉','辰'):'化金',
              ('巳','申'):'化水',('申','巳'):'化水',('午','未'):'化土',('未','午'):'化土'}

# --- 地支三合局 ---
ZHI_SANHE = {'申子辰':'水局','寅午戌':'火局','巳酉丑':'金局','亥卯未':'木局'}

# --- 地支六冲 ---
ZHI_CHONG = [('子','午'),('丑','未'),('寅','申'),('卯','酉'),('辰','戌'),('巳','亥')]

# --- 地支三刑 ---
ZHI_XING = [('寅','巳'),('巳','申'),('申','寅'),('丑','戌'),('戌','未'),('未','丑'),('子','卯'),('卯','子')]
ZHI_ZIXING = [('辰','辰'),('午','午'),('酉','酉'),('亥','亥')]

# --- 地支相害 ---
ZHI_HAI = [('子','未'),('丑','午'),('寅','巳'),('卯','辰'),('申','亥'),('酉','戌')]

# --- 地支相破 ---
ZHI_PO = [('子','酉'),('丑','辰'),('寅','亥'),('卯','午'),('巳','申'),('未','戌')]

# --- 地支三会局(方局) ---
ZHI_SANHUI = {'寅卯辰':'木方','巳午未':'火方','申酉戌':'金方','亥子丑':'水方'}

# --- 六十甲子 ---
LIUJIAZI = [TIANGAN[i%10] + DIZHI[i%12] for i in range(60)]

# --- 纳音 ---
NAYIN = {
    '甲子':'海中金','乙丑':'海中金','丙寅':'炉中火','丁卯':'炉中火',
    '戊辰':'大林木','己巳':'大林木','庚午':'路旁土','辛未':'路旁土',
    '壬申':'剑锋金','癸酉':'剑锋金','甲戌':'山头火','乙亥':'山头火',
    '丙子':'涧下水','丁丑':'涧下水','戊寅':'城头土','己卯':'城头土',
    '庚辰':'白蜡金','辛巳':'白蜡金','壬午':'杨柳木','癸未':'杨柳木',
    '甲申':'泉中水','乙酉':'泉中水','丙戌':'屋上土','丁亥':'屋上土',
    '戊子':'霹雳火','己丑':'霹雳火','庚寅':'松柏木','辛卯':'松柏木',
    '壬辰':'长流水','癸巳':'长流水','甲午':'沙中金','乙未':'沙中金',
    '丙申':'山下火','丁酉':'山下火','戊戌':'平地木','己亥':'平地木',
    '庚子':'壁上土','辛丑':'壁上土','壬寅':'金箔金','癸卯':'金箔金',
    '甲辰':'覆灯火','乙巳':'覆灯火','丙午':'天河水','丁未':'天河水',
    '戊申':'大驿土','己酉':'大驿土','庚戌':'钗钏金','辛亥':'钗钏金',
    '壬子':'桑柘木','癸丑':'桑柘木','甲寅':'大溪水','乙卯':'大溪水',
    '丙辰':'沙中土','丁巳':'沙中土','戊午':'天上火','己未':'天上火',
    '庚申':'石榴木','辛酉':'石榴木','壬戌':'大海水','癸亥':'大海水',
}
NAYIN_WX = {n: wx for n in set(NAYIN.values()) for wx in WX if n.endswith(wx)}

# --- 十二长生 ---
CHANGSHENG = {
    '甲': {'亥':'长生','子':'沐浴','丑':'冠带','寅':'临官','卯':'帝旺','辰':'衰','巳':'病','午':'死','未':'墓','申':'绝','酉':'胎','戌':'养'},
    '乙': {'午':'长生','巳':'沐浴','辰':'冠带','卯':'临官','寅':'帝旺','丑':'衰','子':'病','亥':'死','戌':'墓','酉':'绝','申':'胎','未':'养'},
    '丙': {'寅':'长生','卯':'沐浴','辰':'冠带','巳':'临官','午':'帝旺','未':'衰','申':'病','酉':'死','戌':'墓','亥':'绝','子':'胎','丑':'养'},
    '丁': {'酉':'长生','申':'沐浴','未':'冠带','午':'临官','巳':'帝旺','辰':'衰','卯':'病','寅':'死','丑':'墓','子':'绝','亥':'胎','戌':'养'},
    '戊': {'寅':'长生','卯':'沐浴','辰':'冠带','巳':'临官','午':'帝旺','未':'衰','申':'病','酉':'死','戌':'墓','亥':'绝','子':'胎','丑':'养'},
    '己': {'酉':'长生','申':'沐浴','未':'冠带','午':'临官','巳':'帝旺','辰':'衰','卯':'病','寅':'死','丑':'墓','子':'绝','亥':'胎','戌':'养'},
    '庚': {'巳':'长生','午':'沐浴','未':'冠带','申':'临官','酉':'帝旺','戌':'衰','亥':'病','子':'死','丑':'墓','寅':'绝','卯':'胎','辰':'养'},
    '辛': {'子':'长生','亥':'沐浴','戌':'冠带','酉':'临官','申':'帝旺','未':'衰','午':'病','巳':'死','辰':'墓','卯':'绝','寅':'胎','丑':'养'},
    '壬': {'申':'长生','酉':'沐浴','戌':'冠带','亥':'临官','子':'帝旺','丑':'衰','寅':'病','卯':'死','辰':'墓','巳':'绝','午':'胎','未':'养'},
    '癸': {'卯':'长生','寅':'沐浴','丑':'冠带','子':'临官','亥':'帝旺','戌':'衰','酉':'病','申':'死','未':'墓','午':'绝','巳':'胎','辰':'养'},
}

# --- 节气近似日期 (月,日) → 月支 ---
JIEQI = [(2,4),(3,6),(4,5),(5,6),(6,6),(7,7),(8,8),(9,8),(10,8),(11,7),(12,7),(1,6)]
JIEQI_ZHI = ['寅','卯','辰','巳','午','未','申','酉','戌','亥','子','丑']

# --- 五虎遁年起月 (年干→正月天干索引) ---
WUHU_DUN = {'甲':2,'己':2,'乙':4,'庚':4,'丙':6,'辛':6,'丁':8,'壬':8,'戊':0,'癸':0}

# --- 五鼠遁日起时 (日干→子时天干索引) ---
WUSHU_DUN = {'甲':0,'己':0,'乙':2,'庚':2,'丙':4,'辛':4,'丁':6,'壬':6,'戊':8,'癸':8}

# --- 旺衰 (季节→五行状态) ---
WANG_SHUAI = {
    '春': {'木':'旺','火':'相','水':'休','金':'囚','土':'死'},
    '夏': {'火':'旺','土':'相','木':'休','水':'囚','金':'死'},
    '长夏': {'土':'旺','金':'相','火':'休','木':'囚','水':'死'},
    '秋': {'金':'旺','水':'相','土':'休','火':'囚','木':'死'},
    '冬': {'水':'旺','木':'相','金':'休','土':'囚','火':'死'},
}
MONTH_TO_SEASON = {'寅':'春','卯':'春','辰':'春','巳':'夏','午':'夏','未':'夏',
                   '申':'秋','酉':'秋','戌':'秋','亥':'冬','子':'冬','丑':'冬'}

# --- 空亡表 (旬首→空亡地支) ---
KONG_WANG = {'甲子':['戌','亥'],'甲戌':['申','酉'],'甲申':['午','未'],
             '甲午':['辰','巳'],'甲辰':['寅','卯'],'甲寅':['子','丑']}

# --- 三合局归属 ---
SANHE_GROUP = {'申':'申子辰','子':'申子辰','辰':'申子辰','寅':'寅午戌','午':'寅午戌','戌':'寅午戌',
               '巳':'巳酉丑','酉':'巳酉丑','丑':'巳酉丑','亥':'亥卯未','卯':'亥卯未','未':'亥卯未'}

# ========== 神煞查表 ==========

# 日干起神煞
SHENSHA_GAN = {
    '天乙贵人': {'甲':['丑','未'],'戊':['丑','未'],'庚':['丑','未'],'乙':['子','申'],'己':['子','申'],
                 '丙':['亥','酉'],'丁':['亥','酉'],'壬':['卯','巳'],'癸':['卯','巳'],'辛':['午','寅']},
    '文昌贵人': {'甲':'巳','乙':'午','丙':'申','丁':'酉','戊':'申','己':'酉','庚':'亥','辛':'子','壬':'寅','癸':'卯'},
    '太极贵人': {'甲':['子','午'],'乙':['子','午'],'丙':['卯','酉'],'丁':['卯','酉'],
                 '戊':['辰','戌','丑','未'],'己':['辰','戌','丑','未'],'庚':['寅','亥'],'辛':['寅','亥'],
                 '壬':['巳','申'],'癸':['巳','申']},
    '国印贵人': {'甲':'戌','乙':'亥','丙':'丑','丁':'寅','戊':'丑','己':'寅','庚':'辰','辛':'巳','壬':'未','癸':'申'},
    '禄神': {'甲':'寅','乙':'卯','丙':'巳','丁':'午','戊':'巳','己':'午','庚':'申','辛':'酉','壬':'亥','癸':'子'},
    '羊刃': {'甲':'卯','乙':'辰','丙':'午','丁':'未','戊':'午','己':'未','庚':'酉','辛':'戌','壬':'子','癸':'丑'},
    '金舆': {'甲':'辰','乙':'巳','丙':'未','丁':'申','戊':'未','己':'申','庚':'戌','辛':'亥','壬':'丑','癸':'寅'},
    '流霞': {'甲':'酉','乙':'戌','丙':'未','丁':'申','戊':'巳','己':'午','庚':'辰','辛':'卯','壬':'亥','癸':'寅'},
}

# 三合局起神煞
SHENSHA_SANHE = {
    '驿马': {'申子辰':'寅','寅午戌':'申','巳酉丑':'亥','亥卯未':'巳'},
    '桃花': {'申子辰':'酉','寅午戌':'卯','巳酉丑':'午','亥卯未':'子'},
    '华盖': {'申子辰':'辰','寅午戌':'戌','巳酉丑':'丑','亥卯未':'未'},
    '将星': {'申子辰':'子','寅午戌':'午','巳酉丑':'酉','亥卯未':'卯'},
    '劫煞': {'申子辰':'巳','寅午戌':'亥','巳酉丑':'寅','亥卯未':'申'},
    '亡神': {'申子辰':'亥','寅午戌':'巳','巳酉丑':'申','亥卯未':'寅'},
    '灾煞': {'申子辰':'午','寅午戌':'子','巳酉丑':'卯','亥卯未':'酉'},
}

# 年支起神煞
SHENSHA_ZHI = {
    '红鸾': {'子':'卯','丑':'寅','寅':'丑','卯':'子','辰':'亥','巳':'戌','午':'酉','未':'申','申':'未','酉':'午','戌':'巳','亥':'辰'},
    '天喜': {'子':'酉','丑':'申','寅':'未','卯':'午','辰':'巳','巳':'辰','午':'卯','未':'寅','申':'丑','酉':'子','戌':'亥','亥':'戌'},
    '披麻': {'子':'巳','丑':'辰','寅':'卯','卯':'寅','辰':'丑','巳':'子','午':'亥','未':'戌','申':'酉','酉':'申','戌':'未','亥':'午'},
    '吊客': {'子':'亥','丑':'戌','寅':'酉','卯':'申','辰':'未','巳':'午','午':'巳','未':'辰','申':'卯','酉':'寅','戌':'丑','亥':'子'},
}

# 孤辰寡宿
GUCHEN = {'亥子丑':'寅','寅卯辰':'巳','巳午未':'申','申酉戌':'亥'}
GUASHU = {'亥子丑':'戌','寅卯辰':'丑','巳午未':'辰','申酉戌':'未'}

# 月支起
TIANDE = {'寅':'丁','卯':'申','辰':'壬','巳':'辛','午':'亥','未':'甲','申':'癸','酉':'寅','戌':'丙','亥':'乙','子':'巳','丑':'庚'}
YUEDE = {'寅':'丙','午':'丙','戌':'丙','申':'壬','子':'壬','辰':'壬','亥':'甲','卯':'甲','未':'甲','巳':'庚','酉':'庚','丑':'庚'}
DEXIU_DE = {'寅':'丙丁','午':'丙丁','戌':'丙丁','申':'壬癸戊己','子':'壬癸戊己','辰':'壬癸戊己','巳':'庚辛','酉':'庚辛','丑':'庚辛','亥':'甲乙','卯':'甲乙','未':'甲乙'}
DEXIU_XIU = {'寅':'戊癸','午':'戊癸','戌':'戊癸','申':'丙辛甲己','子':'丙辛甲己','辰':'丙辛甲己','巳':'乙庚','酉':'乙庚','丑':'乙庚','亥':'丁壬','卯':'丁壬','未':'丁壬'}

# 日柱特定神煞
SHENSHA_DAY = {
    '魁罡': ['壬辰','庚戌','庚辰','戊戌'],
    '孤鸾煞': ['乙巳','丁巳','辛亥','戊申','甲寅','壬子','丙午'],
    '阴阳差错': ['丙子','丁丑','戊寅','辛卯','壬辰','癸巳','丙午','丁未','戊申','辛酉','壬戌','癸亥'],
    '十恶大败': ['甲辰','乙巳','壬申','丙申','丁亥','庚辰','戊戌','癸亥','辛巳','己丑'],
    '十灵日': ['甲辰','乙亥','丙辰','丁酉','戊午','庚寅','辛亥','壬寅','癸未','庚戌'],
}
LIUXIU = ['壬午','壬子','辛亥','辛巳','戊午','戊子']
JINSHEN = ['甲子','甲午','己卯','己酉']

# 学堂/词馆
XUETANG = {'金':'巳','木':'亥','水':'申','土':'申','火':'寅'}
CIGUAN = {'甲':'庚寅','乙':'辛卯','丙':'乙巳','丁':'戊午','戊':'丁巳','己':'庚午','庚':'壬申','辛':'癸酉','壬':'癸亥','癸':'壬戌'}
FUXING = {'甲':'寅','乙':'丑亥','丙':'子申','丁':'亥','戊':'未','己':'申酉','庚':'申午','辛':'巳午','壬':'巳辰','癸':'卯寅'}
SANQI = {'天上三奇': ['甲','戊','庚'],'地上三奇': ['辛','壬','癸'],'人中三奇': ['乙','丙','丁']}

# 地支冲合查表
ZHI_CHONG_MAP = {**{a:b for a,b in ZHI_CHONG}, **{b:a for a,b in ZHI_CHONG}}

# ============================================================
# Part 2: 计算函数
# ============================================================

def get_xun(jiazi):
    """获取旬首"""
    idx = LIUJIAZI.index(jiazi)
    return LIUJIAZI[(idx // 10) * 10]

def get_shishen(day_gan, other_gan):
    """计算十神"""
    dw, ow = GAN_WX[day_gan], GAN_WX[other_gan]
    same = GAN_YY[day_gan] == GAN_YY[other_gan]
    if dw == ow: return '比肩' if same else '劫财'
    if WX_SHENG[dw] == ow: return '食神' if same else '伤官'
    if WX_KE[dw] == ow: return '偏财' if same else '正财'
    if WX_KE[ow] == dw: return '七杀' if same else '正官'
    if WX_SHENG[ow] == dw: return '偏印' if same else '正印'
    return '未知'

def solar_to_bazi(year, month, day, hour):
    """公历转四柱八字"""
    # === 年柱 (立春为界) ===
    if date(year, month, day) < date(year, 2, 4):
        yg = TIANGAN[(year - 1 - 4) % 10]
        yz = DIZHI[(year - 1 - 4) % 12]
    else:
        yg = TIANGAN[(year - 4) % 10]
        yz = DIZHI[(year - 4) % 12]

    # === 月柱 (节气定月支, 五虎遁定月干) ===
    month_zhi = None
    for i, (m, d) in enumerate(JIEQI):
        if month == m:
            month_zhi = JIEQI_ZHI[i] if day >= d else JIEQI_ZHI[(i - 1) % 12]
            break
    if month_zhi is None:
        month_zhi = '丑' if month == 1 else '子'

    mg_start = WUHU_DUN[yg]
    zhi_offset = (DIZHI.index(month_zhi) - 2) % 12
    mg = TIANGAN[(mg_start + zhi_offset) % 10]

    # === 日柱 (儒略日法) ===
    # 基准日 2000-01-07 = 甲子日 (60甲子索引0)
    # 修复: 原代码offset=54错误(误认基准日为戊午)，实际甲子索引=0
    days_diff = (date(year, month, day) - date(2000, 1, 7)).days
    day_idx = days_diff % 60
    dg = TIANGAN[day_idx % 10]
    dz = DIZHI[day_idx % 12]

    # === 时柱 (时辰定时支, 五鼠遁定时干) ===
    hour_zhi = ['子','子','丑','丑','寅','寅','卯','卯','辰','辰','巳','巳',
                '午','午','未','未','申','申','酉','酉','戌','戌','亥','亥'][hour % 24]
    hg_start = WUSHU_DUN[dg]
    hg = TIANGAN[(hg_start + DIZHI.index(hour_zhi)) % 10]

    return {'year': (yg, yz), 'month': (mg, month_zhi), 'day': (dg, dz), 'hour': (hg, hour_zhi)}

def find_shensha(pillars):
    """查找四柱中所有神煞"""
    dg, dz = pillars['day']
    yz, mz, hz = pillars['year'][1], pillars['month'][1], pillars['hour'][1]
    all_zhi = [yz, mz, dz, hz]
    all_gan = [pillars['year'][0], pillars['month'][0], dg, pillars['hour'][0]]
    day_jiazi = dg + dz
    res = {}

    # 日干起
    for name, table in SHENSHA_GAN.items():
        target = table.get(dg, [])
        if isinstance(target, list):
            res[name] = [z for z in target if z in all_zhi]
        else:
            res[name] = target if target in all_zhi else ''

    # 三合局起 (年支)
    yg_group = SANHE_GROUP.get(yz, '')
    for name, table in SHENSHA_SANHE.items():
        target = table.get(yg_group, '')
        res[name] = target if target in all_zhi else ''

    # 年支起
    for name, table in SHENSHA_ZHI.items():
        target = table.get(yz, '')
        res[name] = target if target in all_zhi else ''

    # 孤辰寡宿
    for gk in GUCHEN:
        if yz in gk:
            gc, gs = GUCHEN[gk], GUASHU[gk]
            res['孤辰'] = gc if gc in all_zhi else ''
            res['寡宿'] = gs if gs in all_zhi else ''
            break

    # 月支起 (天德/月德/德秀)
    td = TIANDE.get(mz, '')
    res['天德贵人'] = td if td in all_gan else ''
    yd = YUEDE.get(mz, '')
    res['月德贵人'] = yd if yd in all_gan else ''
    de = DEXIU_DE.get(mz, '')
    xiu = DEXIU_XIU.get(mz, '')
    res['德秀_德'] = next((g for g in all_gan if g in de), '')
    res['德秀_秀'] = next((g for g in all_gan if g in xiu), '')

    # 日柱特定
    for name, jl in SHENSHA_DAY.items():
        res[name] = '是' if day_jiazi in jl else ''

    # 六秀/进神
    res['六秀'] = '是' if day_jiazi in LIUXIU else ''
    res['进神'] = '是' if day_jiazi in JINSHEN else ''

    # 天赦
    res['天赦'] = '是' if day_jiazi in ['戊寅','甲午','戊申','甲子'] else ''

    # 学堂 (纳音五行)
    day_nayin = NAYIN.get(day_jiazi, '')
    dnw = NAYIN_WX.get(day_nayin, '')
    xt = XUETANG.get(dnw, '')
    res['学堂'] = xt if xt in all_zhi else ''

    # 词馆
    res['词馆'] = '是' if CIGUAN.get(dg) == day_jiazi else ''

    # 福星贵人
    fx = FUXING.get(dg, '')
    res['福星贵人'] = next((z for z in all_zhi if z in fx), '')

    # 三奇贵人
    for qn, qgs in SANQI.items():
        res[qn] = '是' if all(g in all_gan for g in qgs) else ''

    # 空亡
    xun = get_xun(day_jiazi)
    kw = KONG_WANG.get(xun, [])
    res['空亡'] = [z for z in kw if z in all_zhi]

    # 飞刃 (羊刃对宫)
    yr = SHENSHA_GAN['羊刃'].get(dg, '')
    fr = ZHI_CHONG_MAP.get(yr, '')
    res['飞刃'] = fr if fr in all_zhi else ''

    return res

def find_xingchonghehai(pillars):
    """查找四柱刑冲合害"""
    all_zhi = [p[1] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    all_gan = [p[0] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    pn = ['年','月','日','时']
    res = {}

    def find_pairs(pairs_list):
        """查找地支对"""
        found = []
        for i in range(4):
            for j in range(i + 1, 4):
                for pair in pairs_list:
                    if (all_zhi[i] == pair[0] and all_zhi[j] == pair[1]) or \
                       (all_zhi[i] == pair[1] and all_zhi[j] == pair[0]):
                        found.append(f'{pn[i]}{pn[j]}')
        return found

    # 天干五合
    res['天干五合'] = [f'{pn[i]}{pn[j]}合({GAN_HE[(all_gan[i],all_gan[j])]})'
                       for i in range(4) for j in range(i+1,4) if (all_gan[i],all_gan[j]) in GAN_HE]

    # 天干相冲
    res['天干相冲'] = [f'{pn[i]}{pn[j]}冲'
                       for i in range(4) for j in range(i+1,4)
                       for pair in GAN_CHONG
                       if (all_gan[i]==pair[0] and all_gan[j]==pair[1]) or (all_gan[i]==pair[1] and all_gan[j]==pair[0])]

    # 地支六合
    res['地支六合'] = [f'{pn[i]}{pn[j]}合({ZHI_LIUHE.get((all_zhi[i],all_zhi[j]),"")})'
                       for i in range(4) for j in range(i+1,4) if (all_zhi[i],all_zhi[j]) in ZHI_LIUHE]

    # 地支三合
    zhi_set = set(all_zhi)
    res['地支三合局'] = [ZHI_SANHE[g] for g in ZHI_SANHE if all(z in zhi_set for z in [g[0],g[1],g[2]])]

    # 地支六冲
    res['地支六冲'] = find_pairs(ZHI_CHONG)

    # 地支三刑
    xing = []
    for i in range(4):
        for j in range(4):
            if i != j:
                for pair in ZHI_XING:
                    if all_zhi[i]==pair[0] and all_zhi[j]==pair[1]:
                        xing.append(f'{pn[i]}{pn[j]}刑')
    for i in range(4):
        if (all_zhi[i],all_zhi[i]) in ZHI_ZIXING:
            xing.append(f'{pn[i]}自刑')
    res['地支三刑'] = xing

    # 地支相害
    res['地支相害'] = find_pairs(ZHI_HAI)

    # 地支相破
    res['地支相破'] = find_pairs(ZHI_PO)

    # 地支三会
    res['地支三会局'] = [ZHI_SANHUI[g] for g in ZHI_SANHUI if all(z in zhi_set for z in [g[0],g[1],g[2]])]

    # 干支关系
    rel = []
    for i in range(4):
        gw, zw = GAN_WX[all_gan[i]], ZHI_WX[all_zhi[i]]
        if gw == zw: rel.append(f'{pn[i]}同气')
        elif WX_SHENG[gw] == zw: rel.append(f'{pn[i]}干生支')
        elif WX_SHENG[zw] == gw: rel.append(f'{pn[i]}支生干')
        elif WX_KE[gw] == zw: rel.append(f'{pn[i]}盖头')
        elif WX_KE[zw] == gw: rel.append(f'{pn[i]}截脚')
    res['干支关系'] = rel

    # 坐禄/坐旺/坐长生
    zuo = []
    for i in range(4):
        lu = SHENSHA_GAN['禄神'].get(all_gan[i],'')
        ren = SHENSHA_GAN['羊刃'].get(all_gan[i],'')
        cs = CHANGSHENG.get(all_gan[i],{}).get(all_zhi[i],'')
        if all_zhi[i] == lu: zuo.append(f'{pn[i]}坐禄')
        elif all_zhi[i] == ren: zuo.append(f'{pn[i]}坐刃')
        elif cs == '帝旺': zuo.append(f'{pn[i]}坐旺')
        elif cs == '长生': zuo.append(f'{pn[i]}坐长生')
    res['坐禄坐旺'] = zuo

    # 坐空
    day_jiazi = all_gan[2] + all_zhi[2]
    kw = KONG_WANG.get(get_xun(day_jiazi), [])
    res['坐空'] = [f'{pn[i]}坐空' for i in range(4) if all_zhi[i] in kw]

    return res

def get_wuxing_balance(pillars):
    """五行平衡分析"""
    all_gan = [p[0] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    all_zhi = [p[1] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    dg = pillars['day'][0]

    wx_count = {'木':0,'火':0,'土':0,'金':0,'水':0}
    for g in all_gan: wx_count[GAN_WX[g]] += 1
    for z in all_zhi:
        wx_count[ZHI_WX[z]] += 1
        for cg, _ in ZHI_CANG[z]: wx_count[GAN_WX[cg]] += 0.5

    season = MONTH_TO_SEASON.get(pillars['month'][1], '')
    ws = WANG_SHUAI.get(season, {}).get(GAN_WX[dg], '')

    # 通根
    tonggen = []
    for i, z in enumerate(all_zhi):
        for cg, qi in ZHI_CANG[z]:
            if GAN_WX[cg] == GAN_WX[dg]:
                tonggen.append(f'{["年","月","日","时"][i]}支{qi}{cg}')

    zhi_wx_all = [ZHI_WX[z] for z in all_zhi]
    liutong = [f'{wx}生{WX_SHENG[wx]}' for wx in WX if wx_count[wx] > 0 and wx_count[WX_SHENG[wx]] > 0]

    return {
        '五行个数': {k: int(v) if v == int(v) else v for k, v in wx_count.items()},
        '五行最旺': max(wx_count, key=wx_count.get),
        '五行最弱': min(wx_count, key=wx_count.get),
        '五行缺失': [k for k, v in wx_count.items() if v == 0],
        '日主月令旺衰': ws,
        '得令': '是' if ws in ['旺','相'] else '否',
        '通根': tonggen,
        '寒暖': '寒' if pillars['month'][1] in ['亥','子','丑'] else '暖' if pillars['month'][1] in ['巳','午','未'] else '温' if pillars['month'][1] in ['寅','卯','辰'] else '凉',
        '燥湿': '湿' if '水' in zhi_wx_all and '火' not in zhi_wx_all else '燥' if '火' in zhi_wx_all and '水' not in zhi_wx_all else '平衡',
        '五行流通': liutong,
    }

def get_geju(pillars):
    """格局判断"""
    dg = pillars['day'][0]
    mz = pillars['month'][1]
    all_gan = [p[0] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    all_zhi = [p[1] for p in [pillars['year'], pillars['month'], pillars['day'], pillars['hour']]]
    cang = ZHI_CANG[mz]
    benqi = cang[0][0]
    benqi_ss = get_shishen(dg, benqi)

    wx_all = [GAN_WX[g] for g in all_gan] + [ZHI_WX[z] for z in all_zhi]
    wx_cnt = Counter(wx_all)
    most_wx, most_cnt = wx_cnt.most_common(1)[0]

    zw_map = {'木':'曲直格','火':'炎上格','土':'稼穑格','金':'从革格','水':'润下格'}
    ss_geju_map = {'正官':'正官格','七杀':'七杀格','正财':'正财格','偏财':'偏财格',
                   '正印':'正印格','偏印':'偏印格','食神':'食神格','伤官':'伤官格',
                   '比肩':'建禄格','劫财':'月刃格'}

    day_wx = GAN_WX[dg]
    day_cnt = wx_cnt.get(day_wx, 0)

    if most_cnt >= 7 and day_wx == most_wx:
        geju_type, geju_detail = '专旺格', zw_map.get(most_wx, '')
    elif day_cnt <= 1:
        other_wx = max((k for k in wx_cnt if k != day_wx), key=lambda x: wx_cnt[x], default='')
        cong_map = {WX_KE[day_wx]: '从财格', day_wx: '从杀格', WX_SHENG[day_wx]: '从儿格'}
        geju_type = '从格'
        geju_detail = cong_map.get(other_wx, '从势格')
    else:
        geju_type = '正格'
        geju_detail = ss_geju_map.get(benqi_ss, '待定')

    # 身强弱
    season = MONTH_TO_SEASON.get(mz, '')
    ws = WANG_SHUAI.get(season, {}).get(day_wx, '')
    sheng_cnt = wx_cnt.get(WX_SHENG[day_wx], 0)
    if ws in ['旺','相'] and (day_cnt + sheng_cnt) >= 3:
        shen = '身强'
    elif ws in ['死','囚'] and (day_cnt + sheng_cnt) <= 2:
        shen = '身弱'
    else:
        shen = '中和'

    yongshen = '克泄耗(官杀/食伤/财星)' if shen == '身强' else '生扶(印星/比劫)' if shen == '身弱' else '调候通关'
    tiaohou = '需暖(丙丁火)' if mz in ['亥','子','丑'] else '需凉(壬癸水)' if mz in ['巳','午','未'] else '适中'

    return {
        '月令本气十神': benqi_ss,
        '格局类型': geju_type,
        '格局细分': geju_detail,
        '身强弱': shen,
        '用神方向': yongshen,
        '调候': tiaohou,
    }

# ============================================================
# Part 3: 标签生成
# ============================================================

def generate_bazi_labels(pillars, timestamp_info=None):
    """生成八字四柱完整标签"""
    labels = {}
    dg = pillars['day'][0]
    all_gan = [pillars['year'][0], pillars['month'][0], dg, pillars['hour'][0]]
    all_zhi = [pillars['year'][1], pillars['month'][1], pillars['day'][1], pillars['hour'][1]]
    pn = ['年','月','日','时']

    # === L1: 四柱基础 (8维) ===
    for i, p in enumerate(pn):
        labels[f'L1_{p}柱天干'] = all_gan[i]
        labels[f'L1_{p}柱地支'] = all_zhi[i]

    # === L2: 天干属性 (20维) ===
    for i, p in enumerate(pn):
        labels[f'L2_{p}干五行'] = GAN_WX[all_gan[i]]
        labels[f'L2_{p}干阴阳'] = GAN_YY[all_gan[i]]
        labels[f'L2_{p}干方位'] = GAN_FANG[all_gan[i]]
        labels[f'L2_{p}干季节'] = GAN_SEASON[all_gan[i]]
        labels[f'L2_{p}干五常'] = GAN_WUCHANG[all_gan[i]]

    # === L3: 地支属性 (24维) ===
    for i, p in enumerate(pn):
        labels[f'L3_{p}支五行'] = ZHI_WX[all_zhi[i]]
        labels[f'L3_{p}支阴阳'] = ZHI_YY[all_zhi[i]]
        labels[f'L3_{p}支生肖'] = ZHI_SX[all_zhi[i]]
        labels[f'L3_{p}支方位'] = ZHI_FANG.get(all_zhi[i],'')
        labels[f'L3_{p}支时辰'] = ZHI_HOUR[all_zhi[i]]
        labels[f'L3_{p}支月份'] = ZHI_MONTH[all_zhi[i]]

    # === L4: 藏干 (24维) ===
    for i, p in enumerate(pn):
        cang = ZHI_CANG[all_zhi[i]]
        for j, (cg, qi) in enumerate(cang):
            if j == 0:
                labels[f'L4_{p}支本气'] = cg
                labels[f'L4_{p}支本气十神'] = get_shishen(dg, cg)
            elif j == 1:
                labels[f'L4_{p}支中气'] = cg
                labels[f'L4_{p}支中气十神'] = get_shishen(dg, cg)
            elif j == 2:
                labels[f'L4_{p}支余气'] = cg
                labels[f'L4_{p}支余气十神'] = get_shishen(dg, cg)
        if len(cang) < 2:
            labels[f'L4_{p}支中气'] = '无'
            labels[f'L4_{p}支中气十神'] = '无'
        if len(cang) < 3:
            labels[f'L4_{p}支余气'] = '无'
            labels[f'L4_{p}支余气十神'] = '无'

    # === L5: 十神系统 (21维) ===
    for i, p in enumerate(pn):
        if i == 2:
            labels['L5_日主'] = dg
            labels['L5_日主五行'] = GAN_WX[dg]
            labels['L5_日主阴阳'] = GAN_YY[dg]
        else:
            labels[f'L5_{p}干十神'] = get_shishen(dg, all_gan[i])
    for i, p in enumerate(pn):
        labels[f'L5_{p}支本气十神'] = get_shishen(dg, ZHI_CANG[all_zhi[i]][0][0])

    all_ss = [get_shishen(dg, all_gan[i]) for i in range(4) if i != 2]
    for z in all_zhi:
        for cg, _ in ZHI_CANG[z]: all_ss.append(get_shishen(dg, cg))
    ss_cnt = {ss: all_ss.count(ss) for ss in ['比肩','劫财','食神','伤官','偏财','正财','七杀','正官','偏印','正印']}
    for name, cnt in ss_cnt.items():
        labels[f'L5_十神_{name}'] = cnt

    geju = get_geju(pillars)
    labels['L5_用神方向'] = geju.get('用神方向', '')

    # === L6: 纳音 (8维) ===
    for i, p in enumerate(pn):
        jiazi = all_gan[i] + all_zhi[i]
        ny = NAYIN.get(jiazi, '')
        labels[f'L6_{p}柱纳音'] = ny
        labels[f'L6_{p}柱纳音五行'] = NAYIN_WX.get(ny, '')

    # === L7: 十二长生 (4维) ===
    for i, p in enumerate(pn):
        labels[f'L7_日干在{p}支长生'] = CHANGSHENG.get(dg, {}).get(all_zhi[i], '')

    # === L8: 神煞 (41维) ===
    ss = find_shensha(pillars)
    ss_order = ['天乙贵人','文昌贵人','太极贵人','国印贵人','禄神','羊刃','金舆','流霞',
                '驿马','桃花','华盖','将星','劫煞','亡神','灾煞',
                '红鸾','天喜','披麻','吊客','孤辰','寡宿',
                '天德贵人','月德贵人','德秀_德','德秀_秀',
                '魁罡','孤鸾煞','阴阳差错','十恶大败','十灵日','天赦','学堂','词馆',
                '福星贵人','天上三奇','地上三奇','人中三奇','六秀','进神','飞刃','空亡']
    for name in ss_order:
        val = ss.get(name, '')
        labels[f'L8_{name}'] = ','.join(val) if isinstance(val, list) else val

    # === L9: 格局 (6维) ===
    for k, v in geju.items():
        labels[f'L9_{k}'] = v

    # === L10: 宫位 (16维) ===
    gwm = {'年':'祖业宫','月':'父母宫','日':'夫妻宫','时':'子女宫'}
    for i, p in enumerate(pn):
        labels[f'L10_{p}柱宫位'] = gwm[p]
        labels[f'L10_{p}柱宫位十神'] = get_shishen(dg, all_gan[i]) if i != 2 else '日主'
        labels[f'L10_{p}柱宫位五行'] = GAN_WX[all_gan[i]]
    for i in range(3):
        g1, g2, z1, z2 = all_gan[i], all_gan[i+1], all_zhi[i], all_zhi[i+1]
        rel = []
        if (g1,g2) in GAN_HE or (g2,g1) in GAN_HE: rel.append('干合')
        for pair in GAN_CHONG:
            if (g1==pair[0] and g2==pair[1]) or (g1==pair[1] and g2==pair[0]): rel.append('干冲')
        for pair in ZHI_CHONG:
            if (z1==pair[0] and z2==pair[1]) or (z1==pair[1] and z2==pair[0]): rel.append('支冲')
        if (z1,z2) in ZHI_LIUHE or (z2,z1) in ZHI_LIUHE: rel.append('支合')
        labels[f'L10_{pn[i]}{pn[i+1]}柱关系'] = ','.join(rel) if rel else '无明显关系'
    labels['L10_年时柱关系'] = '需看大运'

    # === L11: 五行平衡 (14维) ===
    wb = get_wuxing_balance(pillars)
    for k, v in wb.items():
        if isinstance(v, dict):
            for k2, v2 in v.items(): labels[f'L11_五行_{k2}'] = v2
        elif isinstance(v, list):
            labels[f'L11_{k}'] = ','.join(v) if v else ''
        else:
            labels[f'L11_{k}'] = v

    # === L12: 刑冲合害 (12维) ===
    xch = find_xingchonghehai(pillars)
    for k, v in xch.items():
        labels[f'L12_{k}'] = ','.join(v) if isinstance(v, list) and v else (v if not isinstance(v, list) else '')

    # === L13: 大运流年 (12维) ===
    if timestamp_info:
        lg = timestamp_info.get('liunian_gan','')
        lz = timestamp_info.get('liunian_zhi','')
        labels['L13_当前流年干'] = lg
        labels['L13_当前流年支'] = lz
        labels['L13_流年十神'] = get_shishen(dg, lg) if lg else ''
        labels['L13_流年与日主关系'] = GAN_WX.get(lg,'') + '与' + GAN_WX[dg] + '的生克关系'
        labels['L13_太岁'] = lz
        labels['L13_岁破'] = ZHI_CHONG_MAP.get(lz, '')
        labels['L13_大运方向'] = '待计算(需性别)'
        labels['L13_起运岁数'] = '待计算(需性别)'
        labels['L13_当前大运干'] = '待计算'
        labels['L13_当前大运支'] = '待计算'
        labels['L13_大运十神'] = '待计算'
        labels['L13_岁运并临'] = '待计算'
    else:
        for i in range(12):
            labels[f'L13_时间依赖_{i+1}'] = '需输入当前时间'

    # === L14: 旬空 (4维) ===
    day_jiazi = all_gan[2] + all_zhi[2]
    xun = get_xun(day_jiazi)
    kw = KONG_WANG.get(xun, [])
    labels['L14_旬'] = xun
    labels['L14_空亡地支'] = ','.join(kw)
    kw_pillars = [pn[i] for i in range(4) if all_zhi[i] in kw]
    labels['L14_空亡宫位'] = ','.join(kw_pillars) if kw_pillars else '无'
    labels['L14_空亡影响'] = '力量减弱' if kw_pillars else '无'

    # === L15: 特殊组合 (10维) ===
    labels['L15_天元一气'] = '是' if len(set(all_gan)) == 1 else ''
    labels['L15_地元一气'] = '是' if len(set(all_zhi)) == 1 else ''
    all_wx_set = set([GAN_WX[g] for g in all_gan] + [ZHI_WX[z] for z in all_zhi])
    labels['L15_两神成象'] = '是' if len(all_wx_set) == 2 else ''
    zhi_set = set(all_zhi)
    sanhe_c = [ZHI_SANHE[g] for g in ZHI_SANHE if all(z in zhi_set for z in [g[0],g[1],g[2]])]
    labels['L15_三合成局'] = ','.join(sanhe_c) if sanhe_c else ''
    sanhui_c = [ZHI_SANHUI[g] for g in ZHI_SANHUI if all(z in zhi_set for z in [g[0],g[1],g[2]])]
    labels['L15_三会成方'] = ','.join(sanhui_c) if sanhui_c else ''
    labels['L15_魁罡日'] = '是' if day_jiazi in SHENSHA_DAY['魁罡'] else ''
    labels['L15_金神格'] = ''  # 需配合月令判断
    labels['L15_日德'] = '是' if day_jiazi in ['甲寅','乙辰','丙辰','丁巳','戊午','己未','庚申','辛酉','壬戌','癸亥'] else ''
    labels['L15_十恶大败'] = '是' if day_jiazi in SHENSHA_DAY['十恶大败'] else ''
    labels['L15_进神'] = '是' if day_jiazi in JINSHEN else ''

    # === L16: 命局层次 (8维) ===
    has_zheng = any('正' in s for s in all_ss)
    has_pian = any('偏' in s for s in all_ss)
    labels['L16_清浊'] = '清' if not (has_zheng and has_pian and '官' in ''.join(all_ss) and '杀' in ''.join(all_ss)) else '浊'
    labels['L16_寒暖'] = wb.get('寒暖', '')
    labels['L16_燥湿'] = wb.get('燥湿', '')
    has_chong = any('冲' in str(v) for v in xch.values() if v)
    labels['L16_动静'] = '动' if has_chong else '静'
    yang_cnt = sum(1 for g in all_gan if GAN_YY[g] == '阳')
    labels['L16_刚柔'] = '刚' if yang_cnt >= 3 else '柔' if yang_cnt <= 1 else '刚柔并济'
    labels['L16_隐显'] = '显' if len(set(all_gan)) >= 3 else '隐'
    labels['L16_流通'] = ','.join(wb.get('五行流通', [])) if wb.get('五行流通') else '不通'
    wx_counter = Counter([GAN_WX[g] for g in all_gan] + [ZHI_WX[z] for z in all_zhi])
    labels['L16_气势'] = f'{wx_counter.most_common(1)[0][0]}气为主'

    # === L17: 六亲 (10维) ===
    labels['L17_父母星'] = '正印' if ss_cnt.get('正印',0) > 0 else ('偏印' if ss_cnt.get('偏印',0) > 0 else '缺')
    labels['L17_兄弟星'] = '比肩' if ss_cnt.get('比肩',0) > 0 else ('劫财' if ss_cnt.get('劫财',0) > 0 else '缺')
    labels['L17_子女星'] = '食神' if ss_cnt.get('食神',0) > 0 else ('伤官' if ss_cnt.get('伤官',0) > 0 else '缺')
    labels['L17_配偶星'] = '正财' if ss_cnt.get('正财',0) > 0 else ('偏财' if ss_cnt.get('偏财',0) > 0 else '缺')
    labels['L17_事业星'] = '正官' if ss_cnt.get('正官',0) > 0 else ('七杀' if ss_cnt.get('七杀',0) > 0 else '缺')
    labels['L17_贵人星'] = '有' if ss.get('天乙贵人') else '无'
    labels['L17_桃花星'] = '有' if ss.get('桃花') else '无'
    labels['L17_驿马星'] = '有' if ss.get('驿马') else '无'
    labels['L17_孤寡星'] = '有' if ss.get('孤辰') or ss.get('寡宿') else '无'
    labels['L17_空亡星'] = '有' if ss.get('空亡') else '无'

    return labels

def generate_dictionary():
    """生成完整字典JSON"""
    dictionary = {
        'meta': {
            'system': '八字四柱',
            'version': '1.0',
            'decompression_method': '公历时间→四柱排盘→多维标签',
            'created': '2026-08-04',
            'description': '八字四柱记忆标签字典 - 全术数记忆维度体系系统②'
        },
        'decompression_rules': {
            'year_pillar': '公历年立春后(year-4)%60, 立春前用上一年',
            'month_pillar': '节气定月支, 五虎遁定月干',
            'day_pillar': '儒略日数mod60 (参考2000-01-07=戊午index54)',
            'hour_pillar': '时辰定时支, 五鼠遁定时干',
            'note': '节气使用近似日期(精度±1-2天), 实际应用建议安装lunar-python库'
        },
        'dimension_layers': {},
        'sixty_jiazi': {},
        'lookup_tables': {
            'tiangan': {g: {'wuxing': GAN_WX[g], 'yinyang': GAN_YY[g], 'fangwei': GAN_FANG[g],
                            'season': GAN_SEASON[g], 'wuchang': GAN_WUCHANG[g]} for g in TIANGAN},
            'dizhi': {z: {'wuxing': ZHI_WX[z], 'yinyang': ZHI_YY[z], 'shengxiao': ZHI_SX[z],
                          'fangwei': ZHI_FANG.get(z,''), 'hour': ZHI_HOUR[z],
                          'canggan': [(cg,qi) for cg,qi in ZHI_CANG[z]]} for z in DIZHI},
            'wuxing': {'sheng': WX_SHENG, 'ke': WX_KE, 'fang': WX_FANG, 'season': WX_SEASON,
                       'color': WX_COLOR, 'taste': WX_TASTE, 'emotion': WX_EMOTION,
                       'organ': WX_ORGAN, 'wuchang': WX_WUCHANG},
            'nayin': NAYIN,
            'nayin_wuxing': NAYIN_WX,
            'changsheng': CHANGSHENG,
            'wang_shuai': WANG_SHUAI,
            'kong_wang': KONG_WANG,
            'shensha_gan': {k: {g: v for g, v in tbl.items()} for k, tbl in SHENSHA_GAN.items()},
            'shensha_sanhe': SHENSHA_SANHE,
            'shensha_zhi': SHENSHA_ZHI,
            'shensha_day': SHENSHA_DAY,
            'gan_he': {f'{k[0]}{k[1]}': v for k, v in GAN_HE.items() if k[0] < k[1]},
            'gan_chong': [f'{p[0]}{p[1]}' for p in GAN_CHONG],
            'zhi_liuhe': {f'{k[0]}{k[1]}': v for k, v in ZHI_LIUHE.items() if k[0] < k[1]},
            'zhi_chong': [f'{p[0]}{p[1]}' for p in ZHI_CHONG],
            'zhi_xing': [f'{p[0]}{p[1]}' for p in ZHI_XING],
            'zhi_hai': [f'{p[0]}{p[1]}' for p in ZHI_HAI],
            'zhi_po': [f'{p[0]}{p[1]}' for p in ZHI_PO],
            'zhi_sanhe': ZHI_SANHE,
            'zhi_sanhui': ZHI_SANHUI,
            'jieqi': {JIEQI_ZHI[i]: f'{JIEQI[i][0]}月{JIEQI[i][1]}日' for i in range(12)},
            'wu_hu_dun': WUHU_DUN,
            'wu_shu_dun': WUSHU_DUN,
        }
    }

    # 60甲子属性表
    for jiazi in LIUJIAZI:
        g, z = jiazi[0], jiazi[1]
        ny = NAYIN.get(jiazi, '')
        dictionary['sixty_jiazi'][jiazi] = {
            'gan': g, 'zhi': z,
            'gan_wuxing': GAN_WX[g], 'zhi_wuxing': ZHI_WX[z],
            'nayin': ny, 'nayin_wuxing': NAYIN_WX.get(ny, ''),
            'canggan': [(cg, qi) for cg, qi in ZHI_CANG[z]],
            'xun': get_xun(jiazi),
            'kong_wang': KONG_WANG.get(get_xun(jiazi), []),
        }

    # 维度统计 (通过实际标签计数)
    sample_pillars = solar_to_bazi(2026, 8, 4, 17)
    sample_labels = generate_bazi_labels(sample_pillars, {'liunian_gan':'丙','liunian_zhi':'午'})
    layer_counts = {}
    for k in sample_labels:
        layer = k.split('_')[0]
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
    dictionary['dimension_layers'] = {k: v for k, v in sorted(layer_counts.items())}
    dictionary['meta']['dimension_count'] = len(sample_labels)

    return dictionary

def generate_labels_from_timestamp(dt_obj):
    """完整解压入口: 时间戳 → 多维标签向量"""
    pillars = solar_to_bazi(dt_obj.year, dt_obj.month, dt_obj.day, dt_obj.hour)
    lg = TIANGAN[(dt_obj.year - 4) % 10]
    lz = DIZHI[(dt_obj.year - 4) % 12]
    labels = generate_bazi_labels(pillars, {'liunian_gan': lg, 'liunian_zhi': lz})
    return {
        'timestamp': dt_obj.strftime('%Y-%m-%d %H:%M'),
        'four_pillars': {
            'year': pillars['year'][0] + pillars['year'][1],
            'month': pillars['month'][0] + pillars['month'][1],
            'day': pillars['day'][0] + pillars['day'][1],
            'hour': pillars['hour'][0] + pillars['hour'][1],
        },
        'day_master': pillars['day'][0],
        'labels': labels,
        'label_count': len(labels),
    }

# ============================================================
# 主程序
# ============================================================

if __name__ == '__main__':
    print("正在生成八字四柱记忆标签字典...")

    dictionary = generate_dictionary()

    # 生成当前时间样例
    now = dt.now()
    sample = generate_labels_from_timestamp(now)
    dictionary['sample_output'] = sample

    # 写入JSON
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bazi_label_dictionary.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(output_path) / 1024
    total_dims = dictionary['meta']['dimension_count']

    print(f"\n{'='*50}")
    print(f"八字四柱记忆标签字典生成完成!")
    print(f"{'='*50}")
    print(f"文件: {output_path}")
    print(f"大小: {file_size:.1f} KB")
    print(f"总维度: {total_dims}")
    print(f"\n维度分布:")
    for layer, count in dictionary['dimension_layers'].items():
        print(f"  {layer}: {count}维")
    print(f"\n当前时间: {sample['timestamp']}")
    print(f"四柱: {sample['four_pillars']}")
    print(f"日主: {sample['day_master']}")
    print(f"样例标签数: {sample['label_count']}")

    print(f"\n=== 样例标签 (前30) ===")
    for i, (k, v) in enumerate(sample['labels'].items()):
        if i >= 30: break
        print(f"  {k}: {v}")

    # 数据验证
    print(f"\n=== 数据验证 ===")
    assert NAYIN['甲子'] == '海中金', "纳音验证失败"
    assert NAYIN['壬戌'] == '大海水', "纳音验证失败"
    assert NAYIN['丙午'] == '天河水', "纳音验证失败"
    print("  纳音验证 ✅")

    assert get_shishen('甲','甲') == '比肩', "十神验证失败"
    assert get_shishen('甲','乙') == '劫财', "十神验证失败"
    assert get_shishen('甲','丙') == '食神', "十神验证失败"
    assert get_shishen('甲','丁') == '伤官', "十神验证失败"
    assert get_shishen('甲','戊') == '偏财', "十神验证失败"
    assert get_shishen('甲','己') == '正财', "十神验证失败"
    assert get_shishen('甲','庚') == '七杀', "十神验证失败"
    assert get_shishen('甲','辛') == '正官', "十神验证失败"
    assert get_shishen('甲','壬') == '偏印', "十神验证失败"
    assert get_shishen('甲','癸') == '正印', "十神验证失败"
    print("  十神验证 ✅")

    assert CHANGSHENG['甲']['亥'] == '长生', "十二长生验证失败"
    assert CHANGSHENG['甲']['卯'] == '帝旺', "十二长生验证失败"
    assert CHANGSHENG['庚']['巳'] == '长生', "十二长生验证失败"
    print("  十二长生验证 ✅")

    assert get_xun('甲子') == '甲子', "旬首验证失败"
    assert KONG_WANG['甲子'] == ['戌','亥'], "空亡验证失败"
    assert get_xun('癸酉') == '甲子', "旬首验证失败"
    assert get_xun('甲戌') == '甲戌', "旬首验证失败"
    print("  空亡验证 ✅")

    # 四柱排盘验证
    test_pillars = solar_to_bazi(2026, 8, 4, 17)
    print(f"\n=== 四柱排盘验证 ===")
    print(f"  2026-08-04 17:00")
    print(f"  年柱: {test_pillars['year'][0]}{test_pillars['year'][1]}")
    print(f"  月柱: {test_pillars['month'][0]}{test_pillars['month'][1]}")
    print(f"  日柱: {test_pillars['day'][0]}{test_pillars['day'][1]}")
    print(f"  时柱: {test_pillars['hour'][0]}{test_pillars['hour'][1]}")

    # 神煞验证
    test_ss = find_shensha(test_pillars)
    print(f"\n=== 神煞验证 ===")
    for name in ['天乙贵人','文昌贵人','禄神','羊刃','驿马','桃花','华盖','空亡']:
        print(f"  {name}: {test_ss.get(name, '')}")

    print(f"\n{'='*50}")
    print(f"全术数记忆维度体系进度:")
    print(f"  系统①易经: 232维 ✅")
    print(f"  系统②八字: {total_dims}维 ✅")
    print(f"  当前总计: {232 + total_dims}维")
    print(f"  目标: 1000-2000维")
    print(f"{'='*50}")

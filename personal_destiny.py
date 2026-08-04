#!/usr/bin/env python3
"""
出生命格模块 (Personal Destiny) — P0.43

基于 lunar_python 计算八字四柱和大运序列，
提取当前大运/流年的命格标签，用于三管叠加系统。

公共API:
  - PersonalDestiny(birth_year, birth_month, birth_day, birth_hour, gender)
  - .get_current_destiny(current_date=None) -> dict (≈15维标签)
  - PersonalDestiny.from_config(config_dict) -> PersonalDestiny
"""

from datetime import datetime, date
from typing import Optional

from lunar_python import Solar

# ─── 静态常量 ──────────────────────────────────────────────

TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

TIANGAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

TIANGAN_YINYANG = {
    "甲": "阳", "丙": "阳", "戊": "阳", "庚": "阳", "壬": "阳",
    "乙": "阴", "丁": "阴", "己": "阴", "辛": "阴", "癸": "阴",
}

DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 五行相生: A生B
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 五行相克: A克B
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 60甲子纳音表
_NAYIN_PAIRS = [
    ("甲子乙丑", "海中金"), ("丙寅丁卯", "炉中火"), ("戊辰己巳", "大林木"),
    ("庚午辛未", "路旁土"), ("壬申癸酉", "剑锋金"), ("甲戌乙亥", "山头火"),
    ("丙子丁丑", "涧下水"), ("戊寅己卯", "城头土"), ("庚辰辛巳", "白蜡金"),
    ("壬午癸未", "杨柳木"), ("甲申乙酉", "泉中水"), ("丙戌丁亥", "屋上土"),
    ("戊子己丑", "霹雳火"), ("庚寅辛卯", "松柏木"), ("壬辰癸巳", "长流水"),
    ("甲午乙未", "沙中金"), ("丙申丁酉", "山下火"), ("戊戌己亥", "平地木"),
    ("庚子辛丑", "壁上土"), ("壬寅癸卯", "金箔金"), ("甲辰乙巳", "覆灯火"),
    ("丙午丁未", "天河水"), ("戊申己酉", "大驿土"), ("庚戌辛亥", "钗钏金"),
    ("壬子癸丑", "桑柘木"), ("甲寅乙卯", "大溪水"), ("丙辰丁巳", "沙中土"),
    ("戊午己未", "天上火"), ("庚申辛酉", "石榴木"), ("壬戌癸亥", "大海水"),
]
NAYIN_TABLE = {}
for _pair, _nayin in _NAYIN_PAIRS:
    for _i in range(0, len(_pair), 2):
        NAYIN_TABLE[_pair[_i:_i + 2]] = _nayin

# 月令本气（地支 → 主气天干）
MONTH_BENQI = {
    "寅": "甲", "卯": "乙", "辰": "戊",
    "巳": "丙", "午": "丁", "未": "己",
    "申": "庚", "酉": "辛", "戌": "戊",
    "亥": "壬", "子": "癸", "丑": "己",
}

# 地支六冲
DIZHI_CHONG = {
    "子": "午", "午": "子", "丑": "未", "未": "丑",
    "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
}

# 地支六合
DIZHI_HE = {
    "子": "丑", "丑": "子", "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳", "午": "未", "未": "午",
}

# 天干五合
TIANGAN_HE = {
    "甲": "己", "己": "甲", "乙": "庚", "庚": "乙",
    "丙": "辛", "辛": "丙", "丁": "壬", "壬": "丁",
    "戊": "癸", "癸": "戊",
}


# ─── 十神计算 ──────────────────────────────────────────────

def calc_shishen(day_gan: str, other_gan: str) -> str:
    """
    根据日主天干和目标天干，计算十神关系。
    返回: 比肩/劫财/食神/伤官/偏财/正财/七杀/正官/偏印/正印
    """
    dm_wx = TIANGAN_WUXING[day_gan]
    ot_wx = TIANGAN_WUXING[other_gan]
    same_polarity = TIANGAN_YINYANG[day_gan] == TIANGAN_YINYANG[other_gan]

    if dm_wx == ot_wx:
        return "比肩" if same_polarity else "劫财"
    if WUXING_SHENG.get(dm_wx) == ot_wx:        # 我生
        return "食神" if same_polarity else "伤官"
    if WUXING_SHENG.get(ot_wx) == dm_wx:         # 生我
        return "偏印" if same_polarity else "正印"
    if WUXING_KE.get(dm_wx) == ot_wx:            # 我克
        return "偏财" if same_polarity else "正财"
    if WUXING_KE.get(ot_wx) == dm_wx:            # 克我
        return "七杀" if same_polarity else "正官"
    return "未知"


def _calc_ganzhi_relation(dayun_gz: str, liunian_gz: str) -> str:
    """计算流年与大运的天干地支组合关系。"""
    if not dayun_gz or not liunian_gz or len(dayun_gz) < 2 or len(liunian_gz) < 2:
        return "未知"
    dg, dz = dayun_gz[0], dayun_gz[1]
    lg, lz = liunian_gz[0], liunian_gz[1]

    # 天干关系
    if TIANGAN_HE.get(dg) == lg:
        gan_rel = "天合"
    elif TIANGAN_WUXING[dg] == TIANGAN_WUXING[lg]:
        gan_rel = "天比"
    elif WUXING_KE.get(TIANGAN_WUXING[dg]) == TIANGAN_WUXING[lg]:
        gan_rel = "天克"
    elif WUXING_SHENG.get(TIANGAN_WUXING[dg]) == TIANGAN_WUXING[lg]:
        gan_rel = "天生"
    else:
        gan_rel = "天无关"

    # 地支关系
    if DIZHI_HE.get(dz) == lz:
        zhi_rel = "地合"
    elif DIZHI_CHONG.get(dz) == lz:
        zhi_rel = "地冲"
    elif DIZHI_WUXING[dz] == DIZHI_WUXING[lz]:
        zhi_rel = "地比"
    elif WUXING_KE.get(DIZHI_WUXING[dz]) == DIZHI_WUXING[lz]:
        zhi_rel = "地克"
    elif WUXING_SHENG.get(DIZHI_WUXING[dz]) == DIZHI_WUXING[lz]:
        zhi_rel = "地生"
    else:
        zhi_rel = "地无关"

    # 组合判断
    if gan_rel == "天克" and zhi_rel == "地冲":
        return "天克地冲"
    if gan_rel == "天合" and zhi_rel == "地合":
        return "天合地合"
    if gan_rel == "天生" and zhi_rel == "地生":
        return "天生地生(顺势)"
    if gan_rel == "天克" and zhi_rel == "地克":
        return "天克地克(冲突)"
    if zhi_rel == "地冲":
        return f"地冲({gan_rel})"
    if zhi_rel == "地合":
        return f"地合({gan_rel})"
    return f"{gan_rel}+{zhi_rel}"


def _calc_geju(day_gan: str, month_zhi: str) -> str:
    """简化版格局判断：看月令本气与日主的十神关系。"""
    benqi = MONTH_BENQI.get(month_zhi, "")
    if not benqi:
        return "未知格局"
    ss = calc_shishen(day_gan, benqi)
    geju_map = {
        "比肩": "建禄格", "劫财": "羊刃格",
        "食神": "食神格", "伤官": "伤官格",
        "偏财": "偏财格", "正财": "正财格",
        "七杀": "七杀格", "正官": "正官格",
        "偏印": "偏印格", "正印": "正印格",
    }
    return geju_map.get(ss, "未知格局")


# ─── 主类 ──────────────────────────────────────────────────

class PersonalDestiny:
    """
    出生命格计算器。

    参数:
        birth_year:  出生年（公历）
        birth_month: 出生月（公历）
        birth_day:   出生日（公历）
        birth_hour:  出生时辰（0-23）
        gender:      'male' / 'female' 或 1/0
    """

    def __init__(self, birth_year: int, birth_month: int,
                 birth_day: int, birth_hour: int, gender):
        self.birth_year = birth_year
        self.birth_month = birth_month
        self.birth_day = birth_day
        self.birth_hour = birth_hour

        if isinstance(gender, str):
            self.gender_code = 1 if gender.lower() in ("male", "男", "m") else 0
        else:
            self.gender_code = 1 if int(gender) == 1 else 0
        self.gender = "male" if self.gender_code == 1 else "female"

        # lunar_python 计算
        solar = Solar.fromYmdHms(birth_year, birth_month, birth_day, birth_hour, 0, 0)
        lunar = solar.getLunar()
        self._ec = lunar.getEightChar()
        self._yun = self._ec.getYun(self.gender_code)
        self._dayun_list = self._yun.getDaYun()

        # 缓存基础信息
        self.day_gan = self._ec.getDayGan()
        self.day_zhi = self._ec.getDayZhi()
        self.month_gan = self._ec.getMonthGan()
        self.month_zhi = self._ec.getMonthZhi()
        self.year_gan = self._ec.getYearGan()
        self.year_zhi = self._ec.getYearZhi()
        self.time_gan = self._ec.getTimeGan()
        self.time_zhi = self._ec.getTimeZhi()

        self.day_master = self.day_gan
        self.day_master_wuxing = TIANGAN_WUXING[self.day_gan]
        self.qiyun_age = self._yun.getStartYear()
        self.is_forward = self._yun.isForward()
        self.dayun_count = len(self._dayun_list)
        self.geju = _calc_geju(self.day_gan, self.month_zhi)

    # ─── 公共方法 ───

    def get_current_destiny(self, current_date: Optional[datetime] = None) -> dict:
        """
        定位当前大运和流年，返回≈15维命格标签字典。

        标签维度:
          - dayun_ganzhi / dayun_gan / dayun_zhi / dayun_nayin / dayun_wuxing
          - dayun_step / dayun_year_in_step / dayun_shishen
          - liunian_ganzhi / liunian_gan / liunian_zhi / liunian_shishen
          - liunian_dayun_relation
          - dayun_total_steps / qiyun_age / dayun_direction
          - day_master / day_master_wuxing / geju
        """
        if current_date is None:
            current_date = datetime.now()
        current_year = current_date.year

        # 定位当前大运（跳过第0步——出生到起运前）
        current_dayun = None
        current_dayun_index = -1
        for i, dy in enumerate(self._dayun_list):
            start_year = dy.getStartYear()
            end_year = dy.getEndYear()
            if start_year <= current_year <= end_year:
                current_dayun = dy
                current_dayun_index = i
                break

        # 如果精确匹配失败，取最接近的
        if current_dayun is None and self._dayun_list:
            for i, dy in enumerate(self._dayun_list):
                if dy.getStartYear() <= current_year:
                    current_dayun = dy
                    current_dayun_index = i
            if current_dayun is None:
                current_dayun = self._dayun_list[-1]
                current_dayun_index = len(self._dayun_list) - 1

        dayun_gz = current_dayun.getGanZhi() if current_dayun else ""
        dayun_gan = dayun_gz[0] if len(dayun_gz) >= 1 else ""
        dayun_zhi = dayun_gz[1] if len(dayun_gz) >= 2 else ""
        dayun_nayin = NAYIN_TABLE.get(dayun_gz, "未知") if dayun_gz else "未知"
        dayun_wuxing = DIZHI_WUXING.get(dayun_zhi, "") if dayun_zhi else ""
        dayun_step = current_dayun_index if current_dayun_index >= 0 else 0
        dayun_year_in_step = current_year - (current_dayun.getStartYear() if current_dayun else current_year) + 1
        dayun_shishen = calc_shishen(self.day_gan, dayun_gan) if dayun_gan else "未知"

        # 定位流年
        liunian_gz = ""
        liunian_gan = ""
        liunian_zhi = ""
        liunian_shishen = "未知"
        if current_dayun:
            liunian_list = current_dayun.getLiuNian()
            for ly in liunian_list:
                if ly.getYear() == current_year:
                    liunian_gz = ly.getGanZhi()
                    liunian_gan = liunian_gz[0] if len(liunian_gz) >= 1 else ""
                    liunian_zhi = liunian_gz[1] if len(liunian_gz) >= 2 else ""
                    liunian_shishen = calc_shishen(self.day_gan, liunian_gan) if liunian_gan else "未知"
                    break

        # 流年与大运关系
        liunian_dayun_relation = _calc_ganzhi_relation(dayun_gz, liunian_gz)

        return {
            # 当前大运
            "dayun_ganzhi": dayun_gz,
            "dayun_gan": dayun_gan,
            "dayun_zhi": dayun_zhi,
            "dayun_nayin": dayun_nayin,
            "dayun_wuxing": dayun_wuxing,
            "dayun_step": dayun_step,
            "dayun_year_in_step": max(dayun_year_in_step, 1),
            "dayun_shishen": dayun_shishen,
            # 当前流年
            "liunian_ganzhi": liunian_gz,
            "liunian_gan": liunian_gan,
            "liunian_zhi": liunian_zhi,
            "liunian_shishen": liunian_shishen,
            "liunian_dayun_relation": liunian_dayun_relation,
            # 命局总览
            "dayun_total_steps": self.dayun_count,
            "qiyun_age": self.qiyun_age,
            "dayun_direction": "顺" if self.is_forward else "逆",
            "day_master": self.day_master,
            "day_master_wuxing": self.day_master_wuxing,
            "geju": self.geju,
        }

    @classmethod
    def from_config(cls, config_dict: dict) -> "PersonalDestiny":
        """
        从 config.json 的 personal 段加载。

        personal 段格式:
        {
            "birth_year": 1998,
            "birth_month": 5,
            "birth_day": 15,
            "birth_hour": 14,
            "gender": "male"
        }
        """
        p = config_dict.get("personal", config_dict)
        return cls(
            birth_year=int(p["birth_year"]),
            birth_month=int(p["birth_month"]),
            birth_day=int(p["birth_day"]),
            birth_hour=int(p["birth_hour"]),
            gender=p.get("gender", "male"),
        )


# ─── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="出生命格标签生成器")
    parser.add_argument("--year", type=int, default=1998, help="出生年")
    parser.add_argument("--month", type=int, default=5, help="出生月")
    parser.add_argument("--day", type=int, default=15, help="出生日")
    parser.add_argument("--hour", type=int, default=14, help="出生时辰(0-23)")
    parser.add_argument("--gender", type=str, default="male", help="性别 male/female")
    args = parser.parse_args()

    pd = PersonalDestiny(args.year, args.month, args.day, args.hour, args.gender)
    result = pd.get_current_destiny()
    print(json.dumps(result, ensure_ascii=False, indent=2))

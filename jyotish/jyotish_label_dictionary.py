#!/usr/bin/env python3
"""
印度占星（Jyotish / Vedic Astrology）标签字典系统
纯Python零依赖实现，使用Schlyter简化VSOP87行星位置算法

架构:
  Part 1: 天文计算引擎 (儒略日/行星位置/月球位置/升降交点/Lahiri岁差)
  Part 2: 占星转换层 (星座/星宿/Pada/大运/上升/宫位/Yoga检测)
  Part 3: 标签字典生成 (7层标签输出)
"""

import math
import json
import os
from datetime import datetime, timedelta

# ============================================
# Part 1: 天文计算引擎
# ============================================

def _day_number(year, month, day, hour=12, minute=0):
    """自2000-01-00 0:00 UT (JD 2451543.5)起的日数"""
    dt = datetime(year, month, day, hour, minute, 0)
    epoch = datetime(1999, 12, 31, 0, 0, 0)
    d = (dt - epoch).total_seconds() / 86400.0
    return d

def _rev(angle):
    """角度归一化到0-360"""
    return angle % 360.0

def _solve_kepler(M, e):
    """解开普勒方程(M均近点角, e离心率)→偏近点角E(度)"""
    M_rad = math.radians(M)
    E = M_rad
    for _ in range(15):
        delta = (E - e * math.sin(E) - M_rad) / (1 - e * math.cos(E))
        E -= delta
        if abs(delta) < 1e-10:
            break
    return math.degrees(E)

# --- 轨道根数 (J2000.0, Schlyter简化模型) ---

_SUN = {
    'w': 282.9404, 'w_rate': 4.70935e-5,
    'e': 0.016709, 'e_rate': -1.151e-9,
    'M': 356.0470, 'M_rate': 0.9856002585,
}

_MOON = {
    'N': 125.1228, 'N_rate': -0.0529538083,
    'i': 5.1454,
    'w': 318.0634, 'w_rate': 0.1643573223,
    'a': 60.2666,
    'e': 0.054900,
    'M': 115.3654, 'M_rate': 13.0649929509,
}

_PLANETS = {
    'Mercury': {
        'N': 48.3313, 'N_rate': 3.24587e-5,
        'i': 7.0047, 'i_rate': 5.00e-8,
        'w': 29.1241, 'w_rate': 1.01444e-5,
        'a': 0.387098,
        'e': 0.205635, 'e_rate': 5.59e-10,
        'M': 168.6562, 'M_rate': 4.0923344368,
    },
    'Venus': {
        'N': 76.6799, 'N_rate': 2.46590e-5,
        'i': 3.3946, 'i_rate': 2.75e-8,
        'w': 54.8910, 'w_rate': 1.38374e-5,
        'a': 0.723330,
        'e': 0.006773, 'e_rate': -1.302e-9,
        'M': 48.0052, 'M_rate': 1.6021302244,
    },
    'Mars': {
        'N': 49.5574, 'N_rate': 2.11081e-5,
        'i': 1.8497, 'i_rate': -1.78e-8,
        'w': 286.5016, 'w_rate': 2.92961e-5,
        'a': 1.523688,
        'e': 0.093405, 'e_rate': 2.516e-9,
        'M': 18.6021, 'M_rate': 0.5240207766,
    },
    'Jupiter': {
        'N': 100.4542, 'N_rate': 2.76854e-5,
        'i': 1.3030, 'i_rate': -1.557e-7,
        'w': 273.8777, 'w_rate': 1.64505e-5,
        'a': 5.20256,
        'e': 0.048498, 'e_rate': 4.469e-9,
        'M': 19.8950, 'M_rate': 0.0830853001,
    },
    'Saturn': {
        'N': 113.6634, 'N_rate': 2.38980e-5,
        'i': 2.4886, 'i_rate': -1.081e-7,
        'w': 339.3939, 'w_rate': 2.97661e-5,
        'a': 9.55475,
        'e': 0.055546, 'e_rate': -9.499e-9,
        'M': 316.9670, 'M_rate': 0.0334442282,
    },
}


def _sun_position(d):
    """太阳位置 → (黄经, 黄纬=0, 距离AU)"""
    w = _SUN['w'] + _SUN['w_rate'] * d
    e = _SUN['e'] + _SUN['e_rate'] * d
    M = _rev(_SUN['M'] + _SUN['M_rate'] * d)
    E = _solve_kepler(M, e)
    x = math.cos(math.radians(E)) - e
    y = math.sin(math.radians(E)) * math.sqrt(1 - e * e)
    r = math.sqrt(x * x + y * y)
    v = math.degrees(math.atan2(y, x))
    lon = _rev(v + w)
    return lon, 0.0, r


def _moon_position(d):
    """月球位置(含主要扰动项) → (黄经, 黄纬, 距离)"""
    N = _rev(_MOON['N'] + _MOON['N_rate'] * d)
    i = _MOON['i']
    w = _rev(_MOON['w'] + _MOON['w_rate'] * d)
    a = _MOON['a']
    e = _MOON['e']
    M = _rev(_MOON['M'] + _MOON['M_rate'] * d)

    E = _solve_kepler(M, e)
    xv = a * (math.cos(math.radians(E)) - e)
    yv = a * math.sin(math.radians(E)) * math.sqrt(1 - e * e)
    v = math.degrees(math.atan2(yv, xv))
    r = math.sqrt(xv * xv + yv * yv)

    # 黄道坐标
    Nrad = math.radians(N)
    irad = math.radians(i)
    vw = math.radians(v + w)
    xh = r * (math.cos(Nrad) * math.cos(vw) - math.sin(Nrad) * math.sin(vw) * math.cos(irad))
    yh = r * (math.sin(Nrad) * math.cos(vw) + math.cos(Nrad) * math.sin(vw) * math.cos(irad))
    zh = r * math.sin(vw) * math.sin(irad)

    lon = _rev(math.degrees(math.atan2(yh, xh)))
    lat = math.degrees(math.atan2(zh, math.sqrt(xh * xh + yh * yh)))

    # 主要扰动项
    Ms = _rev(_SUN['M'] + _SUN['M_rate'] * d)
    Mm = M
    Nm = N
    ws = _SUN['w'] + _SUN['w_rate'] * d
    wm = w
    Ls = _rev(Ms + ws)
    Lm = _rev(Mm + wm + N)
    D = _rev(Lm - Ls)
    F = _rev(Lm - Nm)

    def s(a):
        return math.sin(math.radians(a))

    lon += (-1.274 * s(Mm - 2 * D)    # Evection
            + 0.658 * s(2 * D)         # Variation
            - 0.186 * s(Ms)             # Yearly equation
            - 0.059 * s(2 * Mm - 2 * D)
            - 0.057 * s(Mm - 2 * D + Ms)
            + 0.053 * s(Mm + 2 * D)
            + 0.046 * s(2 * D - Ms)
            + 0.041 * s(Mm - Ms)
            - 0.035 * s(D)              # Parallactic
            - 0.031 * s(Mm + Ms)
            - 0.015 * s(2 * F - 2 * D)
            + 0.011 * s(Mm - 4 * D))

    lat += (-0.173 * s(F - 2 * D)
            - 0.055 * s(Mm - F - 2 * D)
            - 0.046 * s(Mm + F - 2 * D)
            + 0.033 * s(F + 2 * D)
            + 0.017 * s(2 * Mm + F))

    lon = _rev(lon)
    return lon, lat, r


def _planet_position(name, d):
    """行星位置 → (黄经, 黄纬, 距离AU)"""
    e = _PLANETS[name]
    N = _rev(e['N'] + e['N_rate'] * d)
    i = e['i'] + e['i_rate'] * d
    w = _rev(e['w'] + e['w_rate'] * d)
    a = e['a']
    ecc = e['e'] + e['e_rate'] * d
    M = _rev(e['M'] + e['M_rate'] * d)

    E = _solve_kepler(M, ecc)
    xv = a * (math.cos(math.radians(E)) - ecc)
    yv = a * math.sin(math.radians(E)) * math.sqrt(1 - ecc * ecc)
    v = math.degrees(math.atan2(yv, xv))
    r = math.sqrt(xv * xv + yv * yv)

    # 日心黄道坐标
    Nrad = math.radians(N)
    irad = math.radians(i)
    vw = math.radians(v + w)
    xh = r * (math.cos(Nrad) * math.cos(vw) - math.sin(Nrad) * math.sin(vw) * math.cos(irad))
    yh = r * (math.sin(Nrad) * math.cos(vw) + math.cos(Nrad) * math.sin(vw) * math.cos(irad))
    zh = r * math.sin(vw) * math.sin(irad)

    # 地球日心坐标 = 太阳地心坐标反向
    sun_lon, _, sun_r = _sun_position(d)
    xs = -sun_r * math.cos(math.radians(sun_lon))
    ys = -sun_r * math.sin(math.radians(sun_lon))

    # 转地心
    xg = xh - xs
    yg = yh - ys
    zg = zh

    lon = _rev(math.degrees(math.atan2(yg, xg)))
    lat = math.degrees(math.atan2(zg, math.sqrt(xg * xg + yg * yg)))
    dist = math.sqrt(xg * xg + yg * yg + zg * zg)

    # 木星土星扰动
    def s(a):
        return math.sin(math.radians(a))

    def c(a):
        return math.cos(math.radians(a))

    if name == 'Jupiter':
        Mj = M
        Msat = _rev(_PLANETS['Saturn']['M'] + _PLANETS['Saturn']['M_rate'] * d)
        lon += (-0.332 * s(2 * Mj - 5 * Msat - 67.6)
                - 0.056 * s(2 * Mj - 2 * Msat + 21)
                + 0.042 * s(Mj - 2 * Msat + 12))
        lat += 0.032 * s(Mj - 2 * Msat + 12)
        lon = _rev(lon)
    elif name == 'Saturn':
        Msat = M
        Mj = _rev(_PLANETS['Jupiter']['M'] + _PLANETS['Jupiter']['M_rate'] * d)
        lon += (0.812 * s(2 * Mj - 5 * Msat - 67.6)
                - 0.229 * c(2 * Mj - 4 * Msat - 2)
                + 0.119 * s(Mj - 2 * Msat - 3)
                + 0.046 * s(2 * Mj - 6 * Msat - 69)
                + 0.014 * s(Mj - 3 * Msat + 32))
        lat += (-0.020 * c(2 * Mj - 4 * Msat - 2)
                + 0.018 * s(2 * Mj - 6 * Msat - 49))
        lon = _rev(lon)

    return lon, lat, dist


def _lunar_nodes(d):
    """罗睺/计都黄经 → (rahu_lon, ketu_lon)"""
    N = _rev(_MOON['N'] + _MOON['N_rate'] * d)
    return N, _rev(N + 180.0)


def _lahiri_ayanamsa(d):
    """Lahiri岁差(度) — J2000.0时约23.853°，岁差约50.29角秒/年"""
    years = d / 365.25
    return 23.853 + (50.29 / 3600.0) * years


def _obliquity(d):
    """黄赤交角(度)"""
    return 23.4393 - 3.563e-7 * d


# ============================================
# Part 2: 占星转换层
# ============================================

RASI_NAMES_CN = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女',
                 '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼']
RASI_NAMES_EN = ['Mesha', 'Vrishabha', 'Mithuna', 'Karka', 'Simha', 'Kanya',
                 'Tula', 'Vrishchika', 'Dhanu', 'Makara', 'Kumbha', 'Meena']

# Vimshottari Dasha序列与周期
DASHA_SEQUENCE = ['Ketu', 'Venus', 'Sun', 'Moon', 'Mars', 'Rahu', 'Jupiter', 'Saturn', 'Mercury']
DASHA_PERIODS = {'Ketu': 7, 'Venus': 20, 'Sun': 6, 'Moon': 10,
                 'Mars': 7, 'Rahu': 18, 'Jupiter': 16, 'Saturn': 19, 'Mercury': 17}
DASHA_CN = {'Ketu': '计都', 'Venus': '金星', 'Sun': '太阳', 'Moon': '月亮',
            'Mars': '火星', 'Rahu': '罗睺', 'Jupiter': '木星', 'Saturn': '土星', 'Mercury': '水星'}

GRAHA_CN = {'Sun': '太阳', 'Moon': '月亮', 'Mars': '火星', 'Mercury': '水星',
            'Jupiter': '木星', 'Venus': '金星', 'Saturn': '土星',
            'Rahu': '罗睺', 'Ketu': '计都'}

NAK_NAMES_EN = ['Ashwini', 'Bharani', 'Krittika', 'Rohini', 'Mrigashira', 'Ardra',
                'Punarvasu', 'Pushya', 'Ashlesha', 'Magha', 'Purva Phalguni',
                'Uttara Phalguni', 'Hasta', 'Chitra', 'Swati', 'Vishakha',
                'Anuradha', 'Jyeshtha', 'Mula', 'Purva Ashadha', 'Uttara Ashadha',
                'Shravana', 'Dhanishta', 'Shatabhisha', 'Purva Bhadrapada',
                'Uttara Bhadrapada', 'Revati']


def _load_ref():
    """加载JSON参考数据"""
    json_path = os.path.join(os.path.dirname(__file__), 'jyotish_label_dictionary.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _sidereal_lon(tropical_lon, ayanamsa):
    """回归黄经→恒星黄经"""
    return _rev(tropical_lon - ayanamsa)


def _lon_to_rasi(lon):
    """黄经→星座序号(1-12)"""
    return int(lon / 30.0) + 1


def _lon_to_nakshatra(lon):
    """黄经→星宿序号(1-27)"""
    return int(lon / (360.0 / 27.0)) + 1


def _lon_to_pada(lon):
    """黄经→Pada(1-4)"""
    nak_span = 360.0 / 27.0
    pada_span = nak_span / 4.0
    pos_in_nak = lon % nak_span
    return int(pos_in_nak / pada_span) + 1


def _planet_status(planet, rasi, ref_data):
    """行星状态: 庙旺/落陷/本宫/友好/中性/敌对"""
    own = ref_data['own_signs'].get(planet, [])
    exalt = ref_data['exaltation'].get(planet, {})
    debil = ref_data['debilitation'].get(planet, {})

    if exalt.get('sign') == rasi:
        return '庙旺(exalted)'
    if debil.get('sign') == rasi:
        return '落陷(debilitated)'
    if rasi in own:
        return '本宫(own sign)'
    # 简化的友好关系
    friends = {
        'Sun': [1, 4, 5, 9, 11], 'Moon': [1, 3, 6, 7, 10, 11],
        'Mars': [1, 2, 4, 5, 7, 8, 9, 11], 'Mercury': [2, 6, 8, 9, 10, 11],
        'Jupiter': [1, 2, 3, 4, 8, 9, 11, 12], 'Venus': [1, 2, 3, 4, 7, 8, 9, 10, 11, 12],
        'Saturn': [1, 3, 4, 7, 8, 9, 10, 11, 12],
        'Rahu': [1, 2, 3, 6, 7, 9, 10, 11], 'Ketu': [1, 2, 3, 6, 7, 9, 10, 11],
    }
    if rasi in friends.get(planet, []):
        return '友好(friendly)'
    return '中性(neutral)'


def _is_kendra(house):
    """是否为角宫(1/4/7/10)"""
    return house in [1, 4, 7, 10]


def _is_trikona(house):
    """是否为三合宫(1/5/9)"""
    return house in [1, 5, 9]


def _detect_yogas(planets_rasi, lagna_rasi, moon_rasi, ref_data):
    """检测主要Yoga组合"""
    yogas = []

    def house_from(ref_sign, target_sign):
        """从ref_sign到target_sign的宫位(1-12)"""
        return ((target_sign - ref_sign) % 12) + 1

    # Pancha Mahapurusha Yogas
    pmp = {
        'Ruchaka': ('Mars', [1, 8]),
        'Bhadra': ('Mercury', [3, 6]),
        'Hamsa': ('Jupiter', [9, 12]),
        'Malavya': ('Venus', [2, 7]),
        'Sasa': ('Saturn', [10, 11]),
    }

    for yoga_name, (planet, signs) in pmp.items():
        if planet in planets_rasi:
            pr = planets_rasi[planet]
            if pr in signs:
                h = house_from(lagna_rasi, pr)
                if _is_kendra(h):
                    yogas.append(f"{yoga_name}({ref_data['yoga_definitions'][yoga_name]['effect']})")

    # Gajakesari: Jupiter in kendra from Moon
    if 'Jupiter' in planets_rasi and moon_rasi:
        h = house_from(moon_rasi, planets_rasi['Jupiter'])
        if _is_kendra(h):
            yogas.append(f"Gajakesari(智慧/名声/品德)")

    # Budhaditya: Sun + Mercury same sign
    if 'Sun' in planets_rasi and 'Mercury' in planets_rasi:
        if planets_rasi['Sun'] == planets_rasi['Mercury']:
            yogas.append(f"Budhaditya(智力/学问)")

    # Chandra-Mangala: Moon + Mars conjunction or opposition
    if 'Moon' in planets_rasi and 'Mars' in planets_rasi:
        h = house_from(planets_rasi['Moon'], planets_rasi['Mars'])
        if h in [1, 7]:  # conjunction or opposition
            yogas.append(f"ChandraMangala(财富/进取)")

    # Kemadruma: Moon with no planet on either side
    if moon_rasi:
        prev_sign = ((moon_rasi - 2) % 12) + 1
        next_sign = (moon_rasi % 12) + 1
        has_companion = False
        for pname, pr in planets_rasi.items():
            if pname != 'Moon' and (pr == prev_sign or pr == next_sign or pr == moon_rasi):
                has_companion = True
                break
        if not has_companion:
            yogas.append(f"Kemadruma(孤独/自力更生)")

    return yogas


def _calculate_vimshottari_dasha(moon_sidereal_lon, birth_dt, current_dt):
    """计算Vimshottari大运系统

    返回: (mahadasha_name, mahadasha_cn, remaining_years,
          antardasha_name, antardasha_cn, antardasha_remaining_years)
    """
    nak = _lon_to_nakshatra(moon_sidereal_lon)  # 1-27
    nak_index = nak - 1  # 0-26

    # 星宿主星序列: 9颗星循环3次 = 27
    dasha_lord_index = nak_index % 9
    dasha_lord = DASHA_SEQUENCE[dasha_lord_index]

    # 月亮在星宿中的位置比例
    nak_span = 360.0 / 27.0
    pos_in_nak = moon_sidereal_lon % nak_span
    fraction_elapsed = pos_in_nak / nak_span

    # 当前大运已过比例 × 该大运总年数 = 已过年数
    total_years = DASHA_PERIODS[dasha_lord]
    elapsed_years = fraction_elapsed * total_years
    remaining_years_in_maha = total_years - elapsed_years

    # 大运开始时间(往回推：出生前已过的年数)
    maha_start = birth_dt - timedelta(days=elapsed_years * 365.25)

    # 从maha_start开始，依次推算后续大运
    # 找到current_dt所在的大运
    current_lord = dasha_lord
    current_maha_start = maha_start
    lord_idx = DASHA_SEQUENCE.index(dasha_lord)

    while True:
        period = DASHA_PERIODS[current_lord]
        maha_end = current_maha_start + timedelta(days=period * 365.25)
        if current_dt < maha_end:
            break
        lord_idx = (lord_idx + 1) % 9
        current_lord = DASHA_SEQUENCE[lord_idx]
        current_maha_start = maha_end
        if lord_idx == DASHA_SEQUENCE.index(dasha_lord):
            # 完成一个120年循环，不太可能但防止死循环
            break

    # 当前大运剩余
    maha_remaining = (maha_end - current_dt).days / 365.25

    # 计算当前小运(Antardasha)
    # 小运序列 = 从当前大运主星开始，按DASHA_SEQUENCE顺序
    maha_elapsed_fraction = (current_dt - current_maha_start).days / (period * 365.25)
    antar_total = period * DASHA_PERIODS[current_lord] / 120.0  # 小运总年数

    # 小运序列
    antar_lord_idx = DASHA_SEQUENCE.index(current_lord)
    antar_start = current_maha_start
    current_antar_lord = current_lord
    antar_idx = antar_lord_idx

    while True:
        antar_period_years = period * DASHA_PERIODS[DASHA_SEQUENCE[antar_idx]] / 120.0
        antar_end = antar_start + timedelta(days=antar_period_years * 365.25)
        if current_dt < antar_end:
            break
        antar_start = antar_end
        antar_idx = (antar_idx + 1) % 9
        if antar_idx == antar_lord_idx:
            break

    current_antar_lord = DASHA_SEQUENCE[antar_idx]
    antar_remaining = (antar_end - current_dt).days / 365.25

    return (current_lord, DASHA_CN[current_lord], round(maha_remaining, 2),
            current_antar_lord, DASHA_CN[current_antar_lord], round(antar_remaining, 2))


def _calculate_lagna(d, latitude, longitude):
    """计算上升星座(恒星黄经)"""
    # 格林尼治平恒星时
    GMST0 = _rev((_SUN['M'] + _SUN['M_rate'] * d + _SUN['w'] + _SUN['w_rate'] * d))  # 太阳平黄经≈GMST0
    # 更精确: GMST = 280.46061837 + 360.98564736629 * d
    GMST = _rev(280.46061837 + 360.98564736629 * d)
    # 本地恒星时(度)
    LST = _rev(GMST + longitude)

    # 黄赤交角
    obl = _obliquity(d)
    obl_rad = math.radians(obl)
    lst_rad = math.radians(LST)
    lat_rad = math.radians(latitude)

    # 上升点黄经
    # Asc = atan2(cos(RAMC), sin(RAMC)*cos(obl) + tan(lat)*sin(obl))
    # RAMC = LST (度)
    asc_rad = math.atan2(
        math.cos(lst_rad),
        math.sin(lst_rad) * math.cos(obl_rad) + math.tan(lat_rad) * math.sin(obl_rad)
    )
    asc_lon = _rev(math.degrees(asc_rad))

    # 转恒星黄经
    ayanamsa = _lahiri_ayanamsa(d)
    asc_sidereal = _sidereal_lon(asc_lon, ayanamsa)

    return asc_sidereal


# ============================================
# Part 3: 标签字典生成
# ============================================

def generate_labels_from_timestamp(year, month, day, hour=12, minute=0,
                                     gender='male', lat=41.4, lon=119.6):
    """主入口：从时间戳生成印度占星标签字典

    Args:
        year, month, day, hour, minute: 时间
        gender: 性别 ('male'/'female')
        lat: 纬度 (默认辽宁建平41.4°N)
        lon: 经度 (默认辽宁建平119.6°E)

    Returns:
        dict: 7层标签字典
    """
    d = _day_number(year, month, day, hour, minute)
    ref = _load_ref()
    ayanamsa = _lahiri_ayanamsa(d)

    # 计算所有行星恒星黄经
    dt = datetime(year, month, day, hour, minute, 0)
    now = datetime.now()

    # 太阳
    sun_trop, _, _ = _sun_position(d)
    sun_sid = _sidereal_lon(sun_trop, ayanamsa)

    # 月亮
    moon_trop, _, _ = _moon_position(d)
    moon_sid = _sidereal_lon(moon_trop, ayanamsa)

    # 水星到土星
    planet_sids = {}
    for pname in ['Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn']:
        p_trop, _, _ = _planet_position(pname, d)
        planet_sids[pname] = _sidereal_lon(p_trop, ayanamsa)

    # 罗睺/计都
    rahu_trop, ketu_trop = _lunar_nodes(d)
    rahu_sid = _sidereal_lon(rahu_trop, ayanamsa)
    ketu_sid = _sidereal_lon(ketu_trop, ayanamsa)

    # 全部行星
    all_planets = {
        'Sun': sun_sid, 'Moon': moon_sid,
        'Mars': planet_sids['Mars'], 'Mercury': planet_sids['Mercury'],
        'Jupiter': planet_sids['Jupiter'], 'Venus': planet_sids['Venus'],
        'Saturn': planet_sids['Saturn'],
        'Rahu': rahu_sid, 'Ketu': ketu_sid,
    }

    # 行星星座
    planets_rasi = {name: _lon_to_rasi(lon) for name, lon in all_planets.items()}

    # 月亮星宿
    moon_nak = _lon_to_nakshatra(moon_sid)
    moon_pada = _lon_to_pada(moon_sid)

    # 上升星座
    lagna_sid = _calculate_lagna(d, lat, lon)
    lagna_rasi = _lon_to_rasi(lagna_sid)

    # Vimshottari Dasha
    maha, maha_cn, maha_rem, antar, antar_cn, antar_rem = _calculate_vimshottari_dasha(
        moon_sid, dt, now)

    # Yoga检测
    yogas = _detect_yogas(planets_rasi, lagna_rasi, _lon_to_rasi(moon_sid), ref)

    # ===== 生成7层标签 =====

    # L1: 行星位置
    L1 = {}
    for pname, lon in all_planets.items():
        rasi = _lon_to_rasi(lon)
        nak = _lon_to_nakshatra(lon)
        pada = _lon_to_pada(lon)
        rasi_info = ref['rasi_table'][str(rasi)]
        nak_info = ref['nakshatra_table'][str(nak)]
        status = _planet_status(pname, rasi, ref) if pname not in ['Rahu', 'Ketu'] else '影子行星'
        house_from_lagna = ((rasi - lagna_rasi) % 12) + 1

        L1[f"{pname}_{GRAHA_CN[pname]}"] = {
            '恒星黄经': round(lon, 3),
            '星座': f"{rasi_info['name_cn']}({rasi_info['name']})",
            '星宿': f"{nak_info['name_cn']}({nak_info['name']})",
            'pada': pada,
            '状态': status,
            '宫位(从上升)': house_from_lagna,
            '主管': ref['graha_attributes'][pname]['signifies'],
            '五行': ref['graha_attributes'][pname]['wuxing'],
        }

    # L2: 月亮系统(Chandra)
    moon_rasi = _lon_to_rasi(moon_sid)
    moon_rasi_info = ref['rasi_table'][str(moon_rasi)]
    moon_nak_info = ref['nakshatra_table'][str(moon_nak)]
    L2 = {
        '月亮星座': f"{moon_rasi_info['name_cn']}({moon_rasi_info['name']})",
        '月亮星宿': f"{moon_nak_info['name_cn']}({moon_nak_info['name']})",
        '月亮pada': moon_pada,
        '星宿主星': f"{moon_nak_info['ruler_cn']}({moon_nak_info['ruler']})",
        '星宿神明': moon_nak_info['deity_cn'],
        '星宿元素': moon_nak_info['element'],
        '星宿象征': moon_nak_info['symbol'],
        '月亮宫位(从上升)': ((moon_rasi - lagna_rasi) % 12) + 1,
    }

    # L3: 上升与宫位(Lagna & Bhava)
    lagna_info = ref['rasi_table'][str(lagna_rasi)]
    L3 = {
        '上升星座': f"{lagna_info['name_cn']}({lagna_info['name']})",
        '上升主星': f"{lagna_info['lord_cn']}({lagna_info['lord']})",
        '上升元素': lagna_info['element'],
        '上升性质': lagna_info['quality'],
    }
    # 12宫主星(Whole Sign制)
    for house in range(1, 13):
        sign = ((lagna_rasi - 1 + house - 1) % 12) + 1
        sign_info = ref['rasi_table'][str(sign)]
        # 该宫内的行星
        planets_in_house = [GRAHA_CN[p] for p, r in planets_rasi.items() if r == sign]
        house_type = ''
        if _is_kendra(house):
            house_type = '角宫(kendra)'
        elif _is_trikona(house):
            house_type = '三合宫(trikona)'
        elif house in [6, 8, 12]:
            house_type = '凶宫(dusthana)'
        else:
            house_type = '普通(upachaya)'

        L3[f"第{house}宫"] = {
            '星座': sign_info['name_cn'],
            '宫主': sign_info['lord_cn'],
            '宫位类型': house_type,
            '宫内行星': planets_in_house if planets_in_house else '空宫',
        }

    # L4: 大运系统(Vimshottari Dasha)
    L4 = {
        '当前大运(Mahadasha)': f"{maha_cn}({maha})",
        '大运剩余年数': maha_rem,
        '当前小运(Antardasha)': f"{antar_cn}({antar})",
        '小运剩余年数': antar_rem,
        '大运周期': '120年(Vimshottari)',
        '大运序列': '计都→金星→太阳→月亮→火星→罗睺→木星→土星→水星',
    }

    # L5: Yoga组合
    L5 = {
        '已激活Yoga': yogas if yogas else '无显著Yoga',
        'Yoga总数': len(yogas),
    }
    # 检查各行星庙旺/落陷
    for pname in ['Sun', 'Moon', 'Mars', 'Mercury', 'Jupiter', 'Venus', 'Saturn']:
        rasi = planets_rasi[pname]
        status = _planet_status(pname, rasi, ref)
        if '庙旺' in status or '落陷' in status:
            L5[f"{GRAHA_CN[pname]}特殊状态"] = status

    # L6: 元素与性质平衡
    element_count = {'火': 0, '土': 0, '风': 0, '水': 0}
    quality_count = {'开创': 0, '固定': 0, '变动': 0}
    for pname, rasi in planets_rasi.items():
        if pname in ['Rahu', 'Ketu']:
            continue
        rasi_info = ref['rasi_table'][str(rasi)]
        element_count[rasi_info['element']] = element_count.get(rasi_info['element'], 0) + 1
        quality_count[rasi_info['quality']] = quality_count.get(rasi_info['quality'], 0) + 1

    # 加入上升
    lagna_elem = lagna_info['element']
    element_count[lagna_elem] = element_count.get(lagna_elem, 0) + 1

    L6 = {
        '元素分布': element_count,
        '性质分布': quality_count,
        '主导元素': max(element_count, key=element_count.get),
        '主导性质': max(quality_count, key=quality_count.get),
        'Lahiri岁差': round(ayanamsa, 4),
    }

    # L7: 综合总评
    dominant_grahas = []
    for pname in ['Sun', 'Moon', 'Mars', 'Mercury', 'Jupiter', 'Venus', 'Saturn']:
        rasi = planets_rasi[pname]
        status = _planet_status(pname, rasi, ref)
        if '庙旺' in status or '本宫' in status:
            dominant_grahas.append(f"{GRAHA_CN[pname]}({status})")

    L7 = {
        '系统名称': '印度占星(Jyotish/Vedic Astrology)',
        '计算方法': 'Schlyter简化VSOP87+Brown月球理论',
        '岁差系统': 'Lahiri(Chitrapaksha)',
        '宫位制': 'Whole Sign(整宫制)',
        '强势行星': dominant_grahas if dominant_grahas else '无明显强势',
        'Yoga评估': f"共{len(yogas)}个Yoga" + (f": {'; '.join(yogas)}" if yogas else ''),
        '五行映射': {GRAHA_CN[p]: ref['graha_attributes'][p]['wuxing']
                      for p in ref['graha_attributes']},
    }

    # 更新声明维度数
    total_dims = 0
    for layer in [L1, L2, L3, L4, L5, L6, L7]:
        total_dims += len(layer)

    return {
        'L1_行星位置': L1,
        'L2_月亮系统': L2,
        'L3_上升与宫位': L3,
        'L4_大运系统': L4,
        'L5_Yoga组合': L5,
        'L6_元素平衡': L6,
        'L7_综合总评': L7,
        '_meta': {
            'system_name': 'jyotish',
            'system_name_cn': '印度占星',
            'total_dimensions': total_dims,
            'calculation_time': 'pure_math',
            'token_cost': 0,
            'ayanamsa': round(ayanamsa, 4),
            'birth_info': {'lat': lat, 'lon': lon, 'gender': gender},
        }
    }


# ============================================
# 测试入口
# ============================================

if __name__ == '__main__':
    import time

    print("=" * 60)
    print("印度占星(Jyotish)标签字典系统 测试")
    print("=" * 60)

    # 测试1: 当前时间
    t0 = time.time()
    result = generate_labels_from_timestamp(2026, 8, 4, 20, 0)
    t1 = time.time()

    print(f"\n计算耗时: {(t1-t0)*1000:.1f}ms")
    print(f"总维度数: {result['_meta']['total_dimensions']}")
    print(f"Lahiri岁差: {result['_meta']['ayanamsa']}°")

    print("\n--- L1 行星位置 ---")
    for k, v in result['L1_行星位置'].items():
        print(f"  {k}: 星座={v['星座']}, 星宿={v['星宿']}, pada={v['pada']}, 状态={v['状态']}, 宫位={v['宫位(从上升)']}")

    print("\n--- L2 月亮系统 ---")
    for k, v in result['L2_月亮系统'].items():
        print(f"  {k}: {v}")

    print("\n--- L3 上升与宫位(前4宫) ---")
    print(f"  上升星座: {result['L3_上升与宫位']['上升星座']}")
    print(f"  上升主星: {result['L3_上升与宫位']['上升主星']}")
    for i in range(1, 5):
        house = result['L3_上升与宫位'][f'第{i}宫']
        print(f"  第{i}宫: {house}")

    print("\n--- L4 大运系统 ---")
    for k, v in result['L4_大运系统'].items():
        print(f"  {k}: {v}")

    print("\n--- L5 Yoga组合 ---")
    for k, v in result['L5_Yoga组合'].items():
        print(f"  {k}: {v}")

    print("\n--- L6 元素平衡 ---")
    for k, v in result['L6_元素平衡'].items():
        print(f"  {k}: {v}")

    print("\n--- L7 综合总评 ---")
    for k, v in result['L7_综合总评'].items():
        print(f"  {k}: {v}")

    # 测试2: 用户出生时间
    print("\n" + "=" * 60)
    print("测试2: 用户出生时间 1997-10-26 14:45")
    print("=" * 60)
    t0 = time.time()
    result2 = generate_labels_from_timestamp(1997, 10, 26, 14, 45, 'male')
    t1 = time.time()
    print(f"计算耗时: {(t1-t0)*1000:.1f}ms")
    print(f"总维度数: {result2['_meta']['total_dimensions']}")
    print(f"\n--- 行星位置 ---")
    for k, v in result2['L1_行星位置'].items():
        print(f"  {k}: 星座={v['星座']}, 星宿={v['星宿']}, pada={v['pada']}, 状态={v['状态']}")
    print(f"\n--- 月亮 ---")
    print(f"  星座: {result2['L2_月亮系统']['月亮星座']}")
    print(f"  星宿: {result2['L2_月亮系统']['月亮星宿']} (pada {result2['L2_月亮系统']['月亮pada']})")
    print(f"  星宿主星: {result2['L2_月亮系统']['星宿主星']}")
    print(f"\n--- 上升 ---")
    print(f"  {result2['L3_上升与宫位']['上升星座']} (主星: {result2['L3_上升与宫位']['上升主星']})")
    print(f"\n--- 大运 ---")
    print(f"  当前大运: {result2['L4_大运系统']['当前大运(Mahadasha)']} (剩余{result2['L4_大运系统']['大运剩余年数']}年)")
    print(f"  当前小运: {result2['L4_大运系统']['当前小运(Antardasha)']} (剩余{result2['L4_大运系统']['小运剩余年数']}年)")
    print(f"\n--- Yogas ---")
    print(f"  {result2['L5_Yoga组合']['已激活Yoga']}")

    print("\n✅ 测试完成")

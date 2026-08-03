#!/usr/bin/env python3
"""
P0.24 数据修复+补全脚本
1. 修复八卦binary为bottom-to-top统一约定
2. 从trigram名重新计算所有64卦binary（消除手写错误）
3. 补全全部64卦大象传
"""
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 1. 正确的八卦binary（bottom-to-top, 第一个字符=初爻/最底爻）
# ============================================================
TRIGRAM_BINARY = {
    "乾": "111",  # 底=阳,中=阳,顶=阳
    "坤": "000",  # 全阴
    "震": "100",  # 底=阳,中=阴,顶=阴
    "巽": "011",  # 底=阴,中=阳,顶=阳
    "坎": "010",  # 底=阴,中=阳,顶=阴
    "离": "101",  # 底=阳,中=阴,顶=阳
    "艮": "001",  # 底=阴,中=阴,顶=阳
    "兑": "110",  # 底=阳,中=阳,顶=阴
}

TRIGRAM_VALUE = {k: int(v, 2) for k, v in TRIGRAM_BINARY.items()}

# ============================================================
# 2. 全部64卦大象传（周易原文，固定经典文本）
# ============================================================
XIANG_ZHUAN = {
    1: "天行健，君子以自强不息",
    2: "地势坤，君子以厚德载物",
    3: "云雷屯，君子以经纶",
    4: "山下出泉，蒙。君子以果行育德",
    5: "云上于天，需。君子以饮食宴乐",
    6: "天与水违行，讼。君子以作事谋始",
    7: "地中有水，师。君子以容民畜众",
    8: "地上有水，比。先王以建万国，亲诸侯",
    9: "风行天上，小畜。君子以懿文德",
    10: "上天下泽，履。君子以辩上下，定民志",
    11: "天地交，泰。后以财成天地之道，辅相天地之宜",
    12: "天地不交，否。君子以俭德辟难，不可荣以禄",
    13: "天与火，同人。君子以类族辨物",
    14: "火在天上，大有。君子以遏恶扬善，顺天休命",
    15: "地中有山，谦。君子以裒多益寡，称物平施",
    16: "雷出地奋，豫。先王以作乐崇德，殷荐之上帝",
    17: "泽中有雷，随。君子以向晦入宴息",
    18: "山下有风，蛊。君子以振民育德",
    19: "泽上有地，临。君子以教思无穷，容保民无疆",
    20: "风行地上，观。先王以省方观民设教",
    21: "雷电噬嗑。先王以明罚敕法",
    22: "山下有火，贲。君子以明庶政，无敢折狱",
    23: "山附于地，剥。上以厚下安宅",
    24: "雷在地中，复。先王以至日闭关，商旅不行，后不省方",
    25: "天下雷行，物与无妄。先王以茂对时育万物",
    26: "天在山中，大畜。君子以多识前言往行，以畜其德",
    27: "山下有雷，颐。君子以慎言语，节饮食",
    28: "泽灭木，大过。君子以独立不惧，遁世无闷",
    29: "水洊至，习坎。君子以常德行，习教事",
    30: "明两作，离。大人以继明照于四方",
    31: "山上有泽，咸。君子以虚受人",
    32: "雷风恒。君子以立不易方",
    33: "天下有山，遁。君子以远小人，不恶而严",
    34: "雷在天上，大壮。君子以非礼弗履",
    35: "明出地上，晋。君子以自昭明德",
    36: "明入地中，明夷。君子以莅众，用晦而明",
    37: "风自火出，家人。君子以言有物而行有恒",
    38: "上火下泽，睽。君子以同而异",
    39: "山上有水，蹇。君子以反身修德",
    40: "雷雨作，解。君子以赦过宥罪",
    41: "山下有泽，损。君子以惩忿窒欲",
    42: "风雷益。君子以见善则迁，有过则改",
    43: "泽上于天，夬。君子以施禄及下，居德则忌",
    44: "天下有风，姤。后以施命诰四方",
    45: "泽上于地，萃。君子以除戎器，戒不虞",
    46: "地中生木，升。君子以顺德，积小以高大",
    47: "泽无水，困。君子以致命遂志",
    48: "木上有水，井。君子以劳民劝相",
    49: "泽中有火，革。君子以治历明时",
    50: "木上有火，鼎。君子以正位凝命",
    51: "洊雷震。君子以恐惧修省",
    52: "兼山艮。君子以思不出其位",
    53: "山上有木，渐。君子以居贤德善俗",
    54: "泽上有雷，归妹。君子以永终知敝",
    55: "雷电皆至，丰。君子以折狱致刑",
    56: "山上有火，旅。君子以明慎用刑而不留狱",
    57: "随风巽。君子以申命行事",
    58: "丽泽兑。君子以朋友讲习",
    59: "风行水上，涣。先王以享于帝立庙",
    60: "泽上有水，节。君子以制数度，议德行",
    61: "泽上有风，中孚。君子以议狱缓死",
    62: "山上有雷，小过。君子以行过乎恭，丧过乎哀，用过乎俭",
    63: "水在火上，既济。君子以思患而预防之",
    64: "火在水上，未济。君子以慎辨物居方",
}

# ============================================================
# 3. 修复 trigram_table.json
# ============================================================
with open(os.path.join(DIR, "trigram_table.json"), "r", encoding="utf-8") as f:
    trigram_data = json.load(f)

# 修复八卦binary为bottom-to-top约定
fixed_trigrams = {}
for key, tri in trigram_data["trigrams"].items():
    name = tri["name"]
    correct_binary = TRIGRAM_BINARY[name]
    correct_value = TRIGRAM_VALUE[name]
    old_binary = tri["binary"]
    if old_binary != correct_binary:
        print(f"  修复 {name}: binary {old_binary} → {correct_binary}, value {tri['binary_value']} → {correct_value}")
    tri["binary"] = correct_binary
    tri["binary_value"] = correct_value
    tri["binary_convention"] = "bottom-to-top (第一个字符=初爻/最底爻)"
    fixed_trigrams[key] = tri

trigram_data["trigrams"] = fixed_trigrams
trigram_data["meta"]["binary_convention"] = "bottom-to-top: binary[0]=初爻(底), binary[5]=上爻(顶)"

with open(os.path.join(DIR, "trigram_table.json"), "w", encoding="utf-8") as f:
    json.dump(trigram_data, f, ensure_ascii=False, indent=2)
print(f"✅ trigram_table.json 已修复")

# ============================================================
# 4. 修复+补全 hexagram_strategies_base.json
# ============================================================
with open(os.path.join(DIR, "hexagram_strategies_base.json"), "r", encoding="utf-8") as f:
    base_data = json.load(f)

fixed_count = 0
xiang_count = 0
for h in base_data["hexagrams"]:
    # 4a. 重新计算binary（从upper/lower trigram名）
    lower_bin = TRIGRAM_BINARY[h["lower_trigram"]]
    upper_bin = TRIGRAM_BINARY[h["upper_trigram"]]
    correct_binary = lower_bin + upper_bin  # bottom-to-top: 下卦在前(底), 上卦在后(顶)
    
    if h["binary"] != correct_binary:
        print(f"  修复 #{h['num']} {h['name']}: binary {h['binary']} → {correct_binary}")
        h["binary"] = correct_binary
        fixed_count += 1
    
    # 4b. 补全象传
    if h["xiang_zhuan"] == "待补充" or not h["xiang_zhuan"]:
        h["xiang_zhuan"] = XIANG_ZHUAN[h["num"]]
        h["source"] = "天机爻Wiki + 周易原文（象传）"
        xiang_count += 1

base_data["meta"]["completeness"] = "64/64卦辞完整，64/64象传完整，8/64详细爻辞/现代应用完整"
base_data["meta"]["binary_convention"] = "bottom-to-top: binary[0]=初爻(底), binary[5]=上爻(顶)"
base_data["meta"]["notes"] = "象传（大象传）全部补全（来源：周易原文）。爻辞/现代应用目前完整覆盖8卦（乾坤屯蒙需讼泰否），其余56卦待从周易原文补充"

with open(os.path.join(DIR, "hexagram_strategies_base.json"), "w", encoding="utf-8") as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"\n✅ hexagram_strategies_base.json 已修复+补全")
print(f"  binary修复: {fixed_count}卦")
print(f"  象传补全: {xiang_count}卦")

# ============================================================
# 5. 验证
# ============================================================
print("\n--- 验证 ---")
with open(os.path.join(DIR, "hexagram_strategies_base.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

# 验证所有binary可正确拆分回上下卦
print("binary拆分验证（抽样）:")
for num in [1, 2, 3, 6, 11, 23, 24, 63, 64]:
    h = data["hexagrams"][num-1]
    lower = h["binary"][:3]
    upper = h["binary"][3:]
    lower_name = h["lower_trigram"]
    upper_name = h["upper_trigram"]
    lower_ok = lower == TRIGRAM_BINARY[lower_name]
    upper_ok = upper == TRIGRAM_BINARY[upper_name]
    status = "✅" if (lower_ok and upper_ok) else "❌"
    print(f"  {status} #{num} {h['name']}: binary={h['binary']} 下卦={lower}({lower_name}) 上卦={upper}({upper_name}) 象传={h['xiang_zhuan'][:15]}...")

# 验证互卦算法
print("\n互卦验证（水雷屯→应为山地剥）:")
h3 = data["hexagrams"][2]  # 水雷屯
bin_str = h3["binary"]
hu_lower = bin_str[1] + bin_str[2] + bin_str[3]  # 第2,3,4爻
hu_upper = bin_str[2] + bin_str[3] + bin_str[4]  # 第3,4,5爻
hu_binary = hu_lower + hu_upper
print(f"  水雷屯 binary={bin_str}")
print(f"  互卦 binary={hu_binary}")
# 查找互卦对应哪一卦
for h in data["hexagrams"]:
    if h["binary"] == hu_binary:
        print(f"  互卦={h['name']} (#{h['num']})")
        break

# 统计
xiang_complete = sum(1 for h in data["hexagrams"] if h["xiang_zhuan"] and h["xiang_zhuan"] != "待补充")
detail_complete = sum(1 for h in data["hexagrams"] if h["modern_application"] and h["modern_application"] != "待补充")
print(f"\n总计: {xiang_complete}/64象传完整, {detail_complete}/64详细策略完整")

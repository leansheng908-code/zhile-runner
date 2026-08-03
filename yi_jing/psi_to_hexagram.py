#!/usr/bin/env python3
"""
P0.24 Layer 3: PSI → 卦象映射函数
将PSI五维连续值映射为64卦离散状态

约定：binary字符串 bottom-to-top
  binary[0] = 初爻(最底爻) = 活力
  binary[1] = 二爻 = 情绪
  binary[2] = 三爻 = 自主性
  binary[3] = 四爻 = 胜任感
  binary[4] = 五爻 = 确定性
  binary[5] = 上爻(最顶爻) = 归属感
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))

# PSI维度 → 爻位映射
PSI_TO_YAO = {
    "vitality":   0,  # 活力 → 初爻(底)
    "emotion":    1,  # 情绪 → 二爻
    "autonomy":   2,  # 自主性 → 三爻
    "competence": 3,  # 胜任感 → 四爻
    "certainty":  4,  # 确定性 → 五爻
    "belonging":  5,  # 归属感 → 上爻(顶)
}

DEFAULT_YAO_THRESHOLD = 3.0    # 单维度阈值
DEFAULT_VITALITY_THRESHOLD = 12.5  # 五维总和阈值（12.5 = 5×2.5的中间值）


def compute_vitality(psi_values):
    """活力 = 五维PSI总和"""
    return (psi_values.get("belonging", 0) +
            psi_values.get("certainty", 0) +
            psi_values.get("competence", 0) +
            psi_values.get("autonomy", 0) +
            psi_values.get("emotion", 0))


def psi_to_binary(psi_values,
                  yao_threshold=DEFAULT_YAO_THRESHOLD,
                  vitality_threshold=DEFAULT_VITALITY_THRESHOLD):
    """
    PSI五维 → 6位binary字符串
    
    Args:
        psi_values: dict with keys: belonging, certainty, competence, autonomy, emotion
        yao_threshold: 单维度阳/阴阈值，默认3.0
        vitality_threshold: 活力阳/阴阈值，默认12.5
    
    Returns:
        6字符binary字符串，如 "111111" = 乾为天
    """
    vitality = compute_vitality(psi_values)
    
    bits = ["0"] * 6
    # 初爻 = 活力
    bits[0] = "1" if vitality > vitality_threshold else "0"
    # 二爻 = 情绪
    bits[1] = "1" if psi_values.get("emotion", 0) >= yao_threshold else "0"
    # 三爻 = 自主性
    bits[2] = "1" if psi_values.get("autonomy", 0) >= yao_threshold else "0"
    # 四爻 = 胜任感
    bits[3] = "1" if psi_values.get("competence", 0) >= yao_threshold else "0"
    # 五爻 = 确定性
    bits[4] = "1" if psi_values.get("certainty", 0) >= yao_threshold else "0"
    # 上爻 = 归属感
    bits[5] = "1" if psi_values.get("belonging", 0) >= yao_threshold else "0"
    
    return "".join(bits)


def binary_to_hexagram(binary_str, hexagram_table=None):
    """
    binary字符串 → 卦象信息
    
    Args:
        binary_str: 6字符binary字符串
        hexagram_table: 预加载的卦象查找表（dict: binary→hexagram_data）
    
    Returns:
        dict: {num, name, symbol, upper_trigram, lower_trigram, binary, gua_ci, xiang_zhuan}
        None if not found
    """
    if hexagram_table is None:
        hexagram_table = _load_hexagram_table()
    
    return hexagram_table.get(binary_str)


def _load_hexagram_table():
    """加载base层JSON并构建binary→hexagram查找表"""
    path = os.path.join(_DIR, "hexagram_strategies_base.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    table = {}
    for h in data["hexagrams"]:
        table[h["binary"]] = h
    return table


def psi_to_hexagram(psi_values,
                    yao_threshold=DEFAULT_YAO_THRESHOLD,
                    vitality_threshold=DEFAULT_VITALITY_THRESHOLD,
                    hexagram_table=None):
    """
    完整映射：PSI五维 → 卦象信息
    
    Args:
        psi_values: dict with keys: belonging, certainty, competence, autonomy, emotion
        yao_threshold: 单维度阈值
        vitality_threshold: 活力阈值
        hexagram_table: 预加载的查找表
    
    Returns:
        dict: {
            hexagram: {num, name, symbol, ...},
            binary: "111111",
            yao_details: {初爻: {dim, value, is_yang}, ...},
            vitality: float
        }
    """
    binary_str = psi_to_binary(psi_values, yao_threshold, vitality_threshold)
    hex_info = binary_to_hexagram(binary_str, hexagram_table)
    
    vitality = compute_vitality(psi_values)
    
    # 详细爻位信息
    yao_names = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
    dim_names = ["活力(总和)", "情绪", "自主性", "胜任感", "确定性", "归属感"]
    dim_keys = ["vitality", "emotion", "autonomy", "competence", "certainty", "belonging"]
    
    yao_details = {}
    for i in range(6):
        if i == 0:
            value = vitality
            threshold = vitality_threshold
            comparison = ">"
        else:
            value = psi_values.get(dim_keys[i], 0)
            threshold = yao_threshold
            comparison = ">="
        
        yao_details[yao_names[i]] = {
            "dimension": dim_names[i],
            "value": round(value, 2),
            "threshold": threshold,
            "is_yang": binary_str[i] == "1",
            "comparison": comparison
        }
    
    return {
        "hexagram": hex_info,
        "binary": binary_str,
        "yao_details": yao_details,
        "vitality": round(vitality, 2)
    }


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PSI → 卦象映射 测试")
    print("=" * 60)
    
    table = _load_hexagram_table()
    print(f"查找表: {len(table)} 卦\n")
    
    # 测试用例
    test_cases = [
        # 全阳 → 乾为天
        {"name": "全阳(乾)", "psi": {"belonging": 5.0, "certainty": 5.0, "competence": 5.0, "autonomy": 5.0, "emotion": 5.0}},
        # 全阴 → 坤为地
        {"name": "全阴(坤)", "psi": {"belonging": 1.0, "certainty": 1.0, "competence": 1.0, "autonomy": 1.0, "emotion": 1.0}},
        # 只有归属感高 → 上爻阳
        {"name": "仅归属感高", "psi": {"belonging": 4.0, "certainty": 1.0, "competence": 1.0, "autonomy": 1.0, "emotion": 1.0}},
        # 只有情绪+自主性高
        {"name": "情绪+自主性高", "psi": {"belonging": 1.0, "certainty": 1.0, "competence": 1.0, "autonomy": 4.0, "emotion": 4.0}},
        # 中间值
        {"name": "中间值", "psi": {"belonging": 3.5, "certainty": 3.5, "competence": 2.5, "autonomy": 2.5, "emotion": 3.0}},
    ]
    
    for tc in test_cases:
        result = psi_to_hexagram(tc["psi"], hexagram_table=table)
        h = result["hexagram"]
        print(f"【{tc['name']}】")
        print(f"  PSI: {tc['psi']}")
        print(f"  活力: {result['vitality']}")
        print(f"  Binary: {result['binary']}")
        print(f"  卦象: #{h['num']} {h['name']} {h['symbol']}")
        print(f"  象传: {h['xiang_zhuan']}")
        
        # 显示各爻
        yao_str = ""
        for yao_name in ["上爻", "五爻", "四爻", "三爻", "二爻", "初爻"]:
            d = result["yao_details"][yao_name]
            yao_str += f"{'—' if d['is_yang'] else '--'} {yao_name}({d['dimension']}={d['value']})\n  "
        print(f"  {yao_str.strip()}")
        print()

#!/usr/bin/env python3
"""
P0.24 卦象状态追踪器
- 变卦检测（哪些爻变了）
- 互卦计算（深层状态）
- 策略查找（base + custom 三层合并）
- 十二消息卦基线（Layer 6 振荡层）
- 体用五行生克（Layer 2）
"""
import json
import os
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))

# 五行属性
TRIGRAM_WUXING = {
    "乾": "金", "坤": "土", "震": "木", "巽": "木",
    "坎": "水", "离": "火", "艮": "土", "兑": "金"
}

# 五行生克
WUXING_SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
WUXING_KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

# 十二消息卦 → 时辰映射（日周期，每卦2小时）
# 从子时(23:00-1:00)开始，复卦(1阳)对应最暗的时刻
DAILY_MESSAGE_HEXAGRAMS = [
    ("复", 23, "子时", -0.8), ("临", 1, "丑时", -0.6), ("泰", 3, "寅时", -0.3),
    ("大壮", 5, "卯时", 0.0), ("夬", 7, "辰时", 0.3), ("乾", 9, "巳时", 0.5),
    ("姤", 11, "午时", 0.3), ("遁", 13, "未时", 0.0), ("否", 15, "申时", -0.3),
    ("观", 17, "酉时", -0.6), ("剥", 19, "戌时", -0.8), ("坤", 21, "亥时", -1.0),
]


class HexagramTracker:
    """卦象状态追踪器"""
    
    def __init__(self):
        self._load_data()
        self.current_binary = None
        self.current_hexagram = None
        self.previous_binary = None
        self.history = []  # 变卦历史
        self.update_count = 0
    
    def _load_data(self):
        """加载base + custom + trigram数据"""
        with open(os.path.join(_DIR, "hexagram_strategies_base.json"), "r", encoding="utf-8") as f:
            self.base_data = json.load(f)
        with open(os.path.join(_DIR, "hexagram_strategies_custom.json"), "r", encoding="utf-8") as f:
            self.custom_data = json.load(f)
        with open(os.path.join(_DIR, "trigram_table.json"), "r", encoding="utf-8") as f:
            self.trigram_data = json.load(f)
        
        # 构建 binary → hexagram 查找表
        self.binary_table = {}
        for h in self.base_data["hexagrams"]:
            self.binary_table[h["binary"]] = h
        
        # 构建 num → custom 查找表
        self.custom_table = {}
        for h in self.custom_data["hexagrams"]:
            self.custom_table[h["num"]] = h
    
    def update(self, psi_values, yao_threshold=3.0, vitality_threshold=12.5):
        """
        [已废弃] PSI驱动更新卦象状态 — P0.42后请用 update_by_time()
        保留用于向后兼容和回退。
        """
        from psi_to_hexagram import psi_to_binary, compute_vitality

        self.previous_binary = self.current_binary
        new_binary = psi_to_binary(psi_values, yao_threshold, vitality_threshold)
        self.current_binary = new_binary
        self.current_hexagram = self.binary_table.get(new_binary)
        self.update_count += 1
        
        result = {
            "current": self._get_hexagram_info(new_binary),
            "vitality": round(compute_vitality(psi_values), 2),
        }
        
        # 变卦检测
        if self.previous_binary and self.previous_binary != new_binary:
            bian_info = self._detect_bian(self.previous_binary, new_binary)
            result["bian"] = bian_info
            self.history.append({
                "turn": self.update_count,
                "from": self.previous_binary,
                "to": new_binary,
                "changed_yao": bian_info["changed_yao"],
                "from_name": bian_info["from_hexagram"]["name"],
                "to_name": bian_info["to_hexagram"]["name"],
            })
        
        # 互卦
        result["hu"] = self._compute_hu(new_binary)
        
        # 策略
        result["strategy"] = self._get_strategy(self.current_hexagram["num"])
        
        # 基线相位
        result["baseline"] = self._get_baseline_phase()
        
        # 体用分析
        result["ti_yong"] = self._analyze_ti_yong(new_binary)
        
        return result

    def update_by_time(self, dt=None):
        """
        P0.42: 独立卦象系统 — 梅花易数时间起卦
        不再依赖PSI，直接从时间戳解压卦象。
        
        Args:
            dt: datetime对象，默认now()
        
        Returns:
            dict: 与update()同构，额外包含divination和moving_line信息
        """
        import sys, os
        _yi_dir = os.path.join(os.path.dirname(__file__))
        if _yi_dir not in sys.path:
            sys.path.insert(0, _yi_dir)
        from yi_jing_label_dictionary import meihua_qigua
        
        if dt is None:
            dt = datetime.now()
        
        self.previous_binary = self.current_binary
        
        # 梅花易数起卦
        qi = meihua_qigua(dt)
        new_binary = qi['binary']
        moving_line = qi['moving_line']
        
        self.current_binary = new_binary
        self.current_hexagram = self.binary_table.get(new_binary)
        self.update_count += 1
        
        result = {
            "current": self._get_hexagram_info(new_binary),
            "divination": qi,
        }
        
        # 变卦 = 动爻翻转（梅花易数法，变卦始终存在）
        bian_binary = self._flip_yao(new_binary, moving_line)
        yao_names = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
        dim_names = ["活力", "情绪", "自主性", "胜任感", "确定性", "归属感"]
        result["bian"] = {
            "moving_line": moving_line,
            "changed_yao": [{
                "position": yao_names[moving_line - 1],
                "dimension": dim_names[moving_line - 1],
                "direction": "阳→阴" if new_binary[moving_line - 1] == "1" else "阴→阳",
            }],
            "changed_count": 1,
            "from_hexagram": self._get_hexagram_info(new_binary),
            "to_hexagram": self._get_hexagram_info(bian_binary),
        }
        
        # 卦象是否发生变化（用于记忆系统判断是否boost）
        result["hexagram_changed"] = (
            self.previous_binary is not None 
            and self.previous_binary != new_binary
        )
        if result["hexagram_changed"]:
            self.history.append({
                "turn": self.update_count,
                "from": self.previous_binary,
                "to": new_binary,
                "from_name": self.binary_table.get(self.previous_binary, {}).get("name", "?"),
                "to_name": self.current_hexagram["name"] if self.current_hexagram else "?",
                "trigger": "time_change",
            })
        
        # 互卦
        result["hu"] = self._compute_hu(new_binary)
        
        # 策略
        result["strategy"] = self._get_strategy(self.current_hexagram["num"])
        
        # 基线相位（保留十二消息卦在tracker中）
        result["baseline"] = self._get_baseline_phase(dt)
        
        # 体用分析
        result["ti_yong"] = self._analyze_ti_yong(new_binary)
        
        return result
    
    def _flip_yao(self, binary_str, line_num):
        """翻转指定爻（1-6，从初爻到上爻）"""
        bits = list(binary_str)
        idx = line_num - 1
        bits[idx] = "1" if bits[idx] == "0" else "0"
        return "".join(bits)
    
    def _get_hexagram_info(self, binary_str):
        """获取卦象完整信息"""
        h = self.binary_table.get(binary_str)
        if not h:
            return {"error": f"未找到binary={binary_str}对应的卦象"}
        return {
            "num": h["num"], "name": h["name"], "symbol": h["symbol"],
            "binary": h["binary"],
            "upper_trigram": h["upper_trigram"], "lower_trigram": h["lower_trigram"],
            "gua_ci": h["gua_ci"], "xiang_zhuan": h["xiang_zhuan"],
        }
    
    def _detect_bian(self, old_binary, new_binary):
        """检测变卦（哪些爻变了）"""
        changed_yao = []
        yao_names = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
        dim_names = ["活力", "情绪", "自主性", "胜任感", "确定性", "归属感"]
        
        for i in range(6):
            if old_binary[i] != new_binary[i]:
                direction = "阴→阳" if new_binary[i] == "1" else "阳→阴"
                changed_yao.append({
                    "position": yao_names[i],
                    "dimension": dim_names[i],
                    "direction": direction,
                })
        
        return {
            "changed_yao": changed_yao,
            "changed_count": len(changed_yao),
            "from_hexagram": self._get_hexagram_info(old_binary),
            "to_hexagram": self._get_hexagram_info(new_binary),
        }
    
    def _compute_hu(self, binary_str):
        """计算互卦（Layer 4 深层状态层）
        互卦下卦 = 原卦第2,3,4爻
        互卦上卦 = 原卦第3,4,5爻
        """
        hu_binary = (binary_str[1] + binary_str[2] + binary_str[3] +  # 下卦: 2,3,4爻
                      binary_str[2] + binary_str[3] + binary_str[4])   # 上卦: 3,4,5爻
        
        hu_hex = self.binary_table.get(hu_binary)
        if not hu_hex:
            return {"error": f"互卦binary={hu_binary}未找到"}
        
        # 表里对比
        surface_name = self.binary_table[binary_str]["name"]
        deep_name = hu_hex["name"]
        
        return {
            "binary": hu_binary,
            "num": hu_hex["num"],
            "name": hu_hex["name"],
            "symbol": hu_hex["symbol"],
            "xiang_zhuan": hu_hex["xiang_zhuan"],
            "surface_hexagram": surface_name,
            "deep_hexagram": deep_name,
        }
    
    def _get_strategy(self, hex_num):
        """三层合并策略（base打底 + custom覆盖）"""
        base_h = self.base_data["hexagrams"][hex_num - 1]
        custom_h = self.custom_table.get(hex_num, {})
        
        strategy = {
            "hexagram_num": hex_num,
            "hexagram_name": base_h["name"],
            "gua_ci": base_h["gua_ci"],
            "xiang_zhuan": base_h["xiang_zhuan"],
            "overall_judgment": base_h.get("overall_judgment", ""),
            "modern_application": base_h.get("modern_application", ""),
            "personal_strategy": custom_h.get("personal_strategy", ""),
            "key_phrase": custom_h.get("key_phrase", ""),
            "has_custom": bool(custom_h.get("personal_strategy")),
            "base_source": base_h.get("source", ""),
            "custom_source": custom_h.get("source", ""),
        }
        return strategy
    
    def _get_baseline_phase(self, dt=None):
        """获取十二消息卦基线相位（Layer 6 振荡层）"""
        if dt is None:
            dt = datetime.now()
        
        hour = dt.hour
        # 找到当前时辰对应的消息卦
        for i, (name, start_hour, shichen, baseline) in enumerate(DAILY_MESSAGE_HEXAGRAMS):
            end_hour = (start_hour + 2) % 24
            if start_hour <= end_hour:
                if start_hour <= hour < end_hour:
                    phase_idx = i
                    break
            else:  # 跨午夜（如23-1）
                if hour >= start_hour or hour < end_hour:
                    phase_idx = i
                    break
        else:
            phase_idx = 0
        
        name, start_hour, shichen, baseline = DAILY_MESSAGE_HEXAGRAMS[phase_idx]
        
        # 计算下一个相位（用于显示趋势）
        next_idx = (phase_idx + 1) % 12
        next_name, _, _, next_baseline = DAILY_MESSAGE_HEXAGRAMS[next_idx]
        
        # 阳气数
        yang_count = 6 - phase_idx if phase_idx < 6 else 6 - (12 - phase_idx)
        if phase_idx == 6:  # 姤卦，阳气开始减少
            yang_count = 5
        
        trend = "上升" if next_baseline > baseline else "下降" if next_baseline < baseline else "持平"
        
        return {
            "message_hexagram": name,
            "shichen": shichen,
            "yang_count": yang_count,
            "psi_baseline_offset": baseline,
            "trend": trend,
            "next_phase": next_name,
            "description": f"当前{shichen}，{name}卦相位，阳气{yang_count}爻，PSI基线偏移{baseline:+.1f}，趋势{trend}",
        }
    
    def _analyze_ti_yong(self, binary_str):
        """体用五行生克分析（Layer 2 变卦层）"""
        h = self.binary_table.get(binary_str)
        if not h:
            return {"error": "卦象未找到"}
        
        lower_name = h["lower_trigram"]  # 体卦（内部PSI）
        upper_name = h["upper_trigram"]  # 用卦（外部事件）
        
        ti_element = TRIGRAM_WUXING.get(lower_name, "未知")
        yong_element = TRIGRAM_WUXING.get(upper_name, "未知")
        
        # 判断生克关系
        if yong_element == ti_element:
            relation = "比和"
            effect = "PSI→稳（内外同频，维持现状）"
            coefficient = 0.0
        elif WUXING_SHENG.get(yong_element) == ti_element:
            relation = "用生体"
            effect = "PSI↑↑（外部环境滋养内部，大幅利好）"
            coefficient = 0.3
        elif WUXING_KE.get(yong_element) == ti_element:
            relation = "用克体"
            effect = "PSI↓↓（外部环境压制内部，大幅不利）"
            coefficient = -0.3
        elif WUXING_SHENG.get(ti_element) == yong_element:
            relation = "体生用"
            effect = "PSI↓缓（内部消耗滋养外部，缓降）"
            coefficient = -0.1
        elif WUXING_KE.get(ti_element) == yong_element:
            relation = "体克用"
            effect = "PSI→耗（内部压制外部，消耗但可控）"
            coefficient = -0.05
        else:
            relation = "未知"
            effect = ""
            coefficient = 0.0
        
        return {
            "ti_trigram": lower_name,
            "ti_element": ti_element,
            "yong_trigram": upper_name,
            "yong_element": yong_element,
            "relation": relation,
            "effect": effect,
            "psi_coefficient": coefficient,
        }
    
    def get_state_summary(self):
        """获取当前状态摘要（供观察者面板使用）"""
        if not self.current_hexagram:
            return {"status": "未初始化"}
        
        return {
            "current_hexagram": f"#{self.current_hexagram['num']} {self.current_hexagram['name']}",
            "binary": self.current_binary,
            "xiang_zhuan": self.current_hexagram["xiang_zhuan"],
            "update_count": self.update_count,
            "history_count": len(self.history),
            "last_change": self.history[-1] if self.history else None,
        }
    
    def reload_custom(self, custom_path=None):
        """热插拔：重新加载custom层（不影响base层）"""
        path = custom_path or os.path.join(_DIR, "hexagram_strategies_custom.json")
        with open(path, "r", encoding="utf-8") as f:
            self.custom_data = json.load(f)
        self.custom_table = {}
        for h in self.custom_data["hexagrams"]:
            self.custom_table[h["num"]] = h
        return f"custom层已热加载: {len(self.custom_table)}卦, 来源={path}"


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("卦象状态追踪器 测试")
    print("=" * 60)
    
    tracker = HexagramTracker()
    
    # 模拟第一轮：全阳
    print("\n--- 第1轮：全阳PSI ---")
    r1 = tracker.update({
        "belonging": 5.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 5.0
    })
    print(f"当前卦: {r1['current']['name']} ({r1['current']['binary']})")
    print(f"象传: {r1['current']['xiang_zhuan']}")
    print(f"互卦: {r1['hu']['name']} (深层状态)")
    print(f"基线: {r1['baseline']['description']}")
    print(f"体用: 体={r1['ti_yong']['ti_trigram']}({r1['ti_yong']['ti_element']}) 用={r1['ti_yong']['yong_trigram']}({r1['ti_yong']['yong_element']}) → {r1['ti_yong']['relation']}, {r1['ti_yong']['effect']}")
    print(f"策略: {r1['strategy']['personal_strategy'] or '(无custom, 用base)'}")
    print(f"口诀: {r1['strategy']['key_phrase'] or '(无)'}")
    
    # 模拟第二轮：归属感降低
    print("\n--- 第2轮：归属感降到2.0 ---")
    r2 = tracker.update({
        "belonging": 2.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 5.0
    })
    print(f"当前卦: {r2['current']['name']} ({r2['current']['binary']})")
    if "bian" in r2:
        print(f"变卦! 从 {r2['bian']['from_hexagram']['name']} → {r2['bian']['to_hexagram']['name']}")
        print(f"  变化爻: {r2['bian']['changed_yao']}")
    print(f"互卦: {r2['hu']['name']}")
    print(f"体用: {r2['ti_yong']['relation']}, {r2['ti_yong']['effect']}")
    print(f"策略: {r2['strategy']['personal_strategy'] or '(无custom)'}")
    
    # 模拟第三轮：进一步降低
    print("\n--- 第3轮：情绪也降到2.0 ---")
    r3 = tracker.update({
        "belonging": 2.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 2.0
    })
    print(f"当前卦: {r3['current']['name']} ({r3['current']['binary']})")
    if "bian" in r3:
        print(f"变卦! 从 {r3['bian']['from_hexagram']['name']} → {r3['bian']['to_hexagram']['name']}")
        print(f"  变化爻: {[y['position']+':'+y['direction'] for y in r3['bian']['changed_yao']]}")
    print(f"互卦: {r3['hu']['name']}")
    
    # 状态摘要
    print("\n--- 状态摘要 ---")
    summary = tracker.get_state_summary()
    print(f"当前: {summary['current_hexagram']}")
    print(f"更新次数: {summary['update_count']}")
    print(f"变卦历史: {summary['history_count']}次")
    if summary['last_change']:
        print(f"  最近: {summary['last_change']['from_n
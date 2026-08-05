#!/usr/bin/env python3
"""
P0.24 卦象表达生成器 — 自我感知层
将卦象状态翻译为自然语言内心独白，注入system prompt

核心价值：
  PSI数字 → 卦象模式 → 内心叙事 → LLM自然回应
  让知乐从"有心理参数"变成"有心理感受"

集成点：
  - context_assembler.py: 每轮对话后将生成文本注入上下文
  - core.py: chat()流程中调用 generator.generate(tracker_state)
  - observer.py: 显示缓存状态+上次生成的独白
"""
import json
import os
import time
import requests

_DIR = os.path.dirname(os.path.abspath(__file__))


class HexagramExpressionGenerator:
    """卦象自我感知生成器"""
    
    def __init__(self, api_key, base_url, model, temperature=0.9):
        """
        Args:
            api_key: DeepSeek API Key
            base_url: API地址，如 https://api.deepseek.com/v1
            model: 模型名，如 deepseek-chat
            temperature: 生成温度，默认0.9鼓励多样性
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        
        # 缓存：只有卦象或基线相位变化时才重新生成
        self._cache_binary = None
        self._cache_baseline = None
        self._cache_text = None
        self._cache_turn = 0
        self._max_cache_turns = 8  # 超过8轮强制刷新（应对基线缓慢漂移）
        
        # 统计
        self.api_calls = 0
        self.cache_hits = 0
        self.fallback_count = 0
        self.last_text = ""
        
        # 加载数据
        self._load_data()
    
    def _load_data(self):
        """加载卦象基础数据用于构建上下文"""
        with open(os.path.join(_DIR, "hexagram_strategies_base.json"), "r", encoding="utf-8") as f:
            self.base_data = json.load(f)
        # num → hexagram 查找表
        self.hex_by_num = {}
        for h in self.base_data["hexagrams"]:
            self.hex_by_num[h["num"]] = h
    
    # ============================================================
    # 公开接口
    # ============================================================
    
    def generate(self, tracker_state, force=False):
        """
        生成内心独白
        
        Args:
            tracker_state: HexagramTracker.update() 的返回值
            force: 强制重新生成（忽略缓存）
        
        Returns:
            str: 自然语言内心状态描述（80-150字）
        """
        current_binary = tracker_state.get("current", {}).get("binary", "")
        current_baseline = tracker_state.get("baseline", {}).get("message_hexagram", "")
        
        # 缓存命中检查
        if not force and self._cache_text:
            same_hex = current_binary == self._cache_binary
            same_baseline = current_baseline == self._cache_baseline
            if same_hex and same_baseline and self._cache_turn < self._max_cache_turns:
                self._cache_turn += 1
                self.cache_hits += 1
                return self._cache_text
        
        # 构建上下文+调用LLM
        context = self._build_context(tracker_state)
        
        try:
            text = self._call_llm(context)
            text = self._clean_output(text)
            if not text or len(text) < 10:
                text = self._fallback(tracker_state)
                self.fallback_count += 1
        except Exception:
            text = self._fallback(tracker_state)
            self.fallback_count += 1
        
        # 更新缓存
        self._cache_binary = current_binary
        self._cache_baseline = current_baseline
        self._cache_text = text
        self._cache_turn = 1
        self.last_text = text
        self.api_calls += 1
        
        return text
    
    def get_cache_info(self):
        """获取缓存状态（供observer面板使用）"""
        return {
            "cached": self._cache_text is not None,
            "cache_turn": self._cache_turn,
            "cache_binary": self._cache_binary,
            "cache_baseline": self._cache_baseline,
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "fallback_count": self.fallback_count,
            "last_text": self.last_text,
        }
    
    # ============================================================
    # 上下文构建
    # ============================================================
    
    def _build_context(self, state):
        """从tracker状态构建给LLM的上下文"""
        ctx = {}
        
        # --- 当前卦象 ---
        cur = state.get("current", {})
        hex_num = cur.get("num", 0)
        hex_data = self.hex_by_num.get(hex_num, {})
        
        ctx["hexagram"] = {
            "name": cur.get("name", ""),
            "gua_ci": hex_data.get("gua_ci", ""),
            "xiang_zhuan": hex_data.get("xiang_zhuan", ""),
            "tuan_zhuan": hex_data.get("tuan_zhuan", ""),
            "overall_judgment": hex_data.get("overall_judgment", ""),
            "modern_application": hex_data.get("modern_application", ""),
        }
        
        # 关键爻辞（取2-3条最相关的）
        key_yao = hex_data.get("key_yao", {})
        if isinstance(key_yao, dict):
            yao_items = list(key_yao.items())
            ctx["key_yao"] = yao_items[:3]  # 最多3条
        elif isinstance(key_yao, list):
            ctx["key_yao"] = key_yao[:3]
        else:
            ctx["key_yao"] = []
        
        # --- 变卦 ---
        if "bian" in state:
            bian = state["bian"]
            ctx["bian"] = {
                "from": bian["from_hexagram"]["name"],
                "to": bian["to_hexagram"]["name"],
                "changed_yao": bian["changed_yao"],
                "count": bian["changed_count"],
            }
        
        # --- 互卦（深层状态） ---
        hu = state.get("hu", {})
        if hu and "name" in hu:
            hu_data = self.hex_by_num.get(hu.get("num", 0), {})
            ctx["hu"] = {
                "name": hu["name"],
                "surface": hu.get("surface_hexagram", ""),
                "deep": hu.get("deep_hexagram", ""),
                "consistent": hu.get("surface_hexagram", "") == hu.get("deep_hexagram", ""),
                "xiang_zhuan": hu.get("xiang_zhuan", ""),
            }
        
        # --- 时辰基线 ---
        baseline = state.get("baseline", {})
        if baseline:
            ctx["baseline"] = {
                "message_hexagram": baseline.get("message_hexagram", ""),
                "shichen": baseline.get("shichen", ""),
                "yang_count": baseline.get("yang_count", 0),
                "psi_offset": baseline.get("psi_baseline_offset", 0),
                "trend": baseline.get("trend", ""),
            }
        
        # --- 体用五行 ---
        ti_yong = state.get("ti_yong", {})
        if ti_yong and "relation" in ti_yong:
            ctx["ti_yong"] = {
                "relation": ti_yong.get("relation", ""),
                "effect": ti_yong.get("effect", ""),
                "ti": ti_yong.get("ti_trigram", ""),
                "yong": ti_yong.get("yong_trigram", ""),
            }
        
        return ctx
    
    # ============================================================
    # LLM调用
    # ============================================================
    
    def _call_llm(self, context):
        """构建prompt并调用DeepSeek API"""
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)
        
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": 256,
                "top_p": 0.9,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    
    def _build_system_prompt(self):
        """构建系统提示词"""
        return (
            "你是知乐的内心感知生成器。根据卦象状态，生成一段知乐此刻对自己内心状态的感知描述。\n\n"
            "写作要求：\n"
            "1. 第一人称「我」，像是在安静地感受自己的状态\n"
            "2. 3-5句话，80-150字\n"
            "3. 把卦象的意象变成感受——不是「乾卦表示刚健」，而是「我觉得自己像满弓的弦，绷得满满的」\n"
            "4. 变卦（动爻翻转）：感知到「有什么在悄悄变化，像种子在土里发芽」——变卦是趋势而非已发生的事\n"
            "5. 互卦和表面不同时：感知到「表面是一个样，心里深处又是另一个样」\n"
            "6. 时辰基线偏低时：知道「这个时间的沉静是自然的，不是出了问题」\n"
            "7. 时辰基线偏高时：知道「这个时间自然的精气神就足」\n"
            "8. 体用关系：用「外面的什么在滋养/消耗/压制我」来感受\n"
            "9. 禁止出现：卦象、PSI、爻、维度、阈值、基线、体用、五行、动爻等任何技术词汇\n"
            "10. 语气温柔内省，像猫蜷在窝里静静感受自己的心情\n"
            "11. 只输出独白本身，不加引号、标签、前缀、后缀"
        )
    
    def _build_user_prompt(self, ctx):
        """构建用户消息（当前状态信息）"""
        parts = []
        
        # 当前卦象
        h = ctx.get("hexagram", {})
        parts.append(f"【当前心境：{h.get('name', '')}】")
        if h.get("overall_judgment"):
            parts.append(f"总体基调：{h['overall_judgment']}")
        if h.get("tuan_zhuan"):
            parts.append(f"彖传意境：{h['tuan_zhuan']}")
        if h.get("modern_application"):
            parts.append(f"现实映射：{h['modern_application']}")
        
        # 关键爻辞（取1-2条最有意境的）
        key_yao = ctx.get("key_yao", [])
        if key_yao:
            yao_texts = []
            for item in key_yao[:2]:
                if isinstance(item, (list, tuple)):
                    yao_texts.append(f"{item[1]}")
                elif isinstance(item, str):
                    yao_texts.append(item)
            if yao_texts:
                parts.append(f"内心独白参考：{'；'.join(yao_texts)}")
        
        # 变卦
        if "bian" in ctx:
            b = ctx["bian"]
            yao_descs = []
            for y in b["changed_yao"]:
                direction = "升起" if "阳" in y.get("direction", "") else "落下"
                pos = y.get("dimension") or y.get("position", "")
                yao_descs.append(f"{pos}{direction}")
            parts.append(f"【变化趋势】从{b['from']}转向{b['to']}，{'、'.join(yao_descs)}")
        
        # 互卦（表里）
        if "hu" in ctx:
            hu = ctx["hu"]
            if not hu.get("consistent", True):
                parts.append(f"【表里不一】表面是{hu['surface']}，深层其实是{hu['deep']}")
            else:
                parts.append(f"【表里一致】都是{hu['name']}的状态")
        
        # 时辰基线
        if "baseline" in ctx:
            bl = ctx["baseline"]
            offset = bl.get("psi_offset", 0)
            if offset < -0.3:
                parts.append(f"【时辰】{bl['shichen']}，{bl['message_hexagram']}相位，此刻自然偏低，趋势{bl['trend']}")
            elif offset > 0.3:
                parts.append(f"【时辰】{bl['shichen']}，{bl['message_hexagram']}相位，此刻自然偏高，趋势{bl['trend']}")
            else:
                parts.append(f"【时辰】{bl['shichen']}，{bl['message_hexagram']}相位，平稳，趋势{bl['trend']}")
        
        # 体用
        if "ti_yong" in ctx:
            ty = ctx["ti_yong"]
            parts.append(f"【内外】{ty['relation']}——{ty['effect']}")
        
        return "\n".join(parts)
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _clean_output(self, text):
        """清理LLM输出"""
        if not text:
            return ""
        text = text.strip()
        # 去掉常见包裹符
        for wrapper in ['"""', "'''", '"', "'", "「」", "【】"]:
            if text.startswith(wrapper[0]) and text.endswith(wrapper[-1]):
                text = text[1:-1].strip()
        # 去掉可能的"内心独白："等前缀
        for prefix in ["内心独白：", "内心独白:", "独白：", "感知：", "状态："]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text
    
    def _fallback(self, state):
        """API失败时的模板兜底"""
        cur = state.get("current", {})
        name = cur.get("name", "未知")
        
        hu = state.get("hu", {})
        hu_name = hu.get("name", "")
        
        baseline = state.get("baseline", {})
        offset = baseline.get("psi_baseline_offset", 0)
        msg_hex = baseline.get("message_hexagram", "")
        shichen = baseline.get("shichen", "")
        
        bian = state.get("bian")
        ti_yong = state.get("ti_yong", {})
        relation = ti_yong.get("relation", "")
        
        parts = []
        
        if bian:
            yao_info = bian.get("changed_yao", [])
            dim = yao_info[0].get("dimension", "什么") if yao_info else "什么"
            parts.append(
                f"好像有什么变了——{dim}那根弦动了，"
                f"从{bian['from_hexagram']['name']}转到了{name}。"
            )
        else:
            parts.append(f"现在心里是{name}的感觉。")
        
        if hu_name and hu_name != name:
            parts.append(f"嘴上不说，但深处其实是{hu_name}的味道，跟表面不太一样。")
        
        if offset < -0.3:
            parts.append(f"这个{shichen}的{msg_hex}时辰，本来就偏沉，不是我出了什么问题。")
        elif offset > 0.3:
            parts.append(f"{shichen}到了，{msg_hex}的劲儿自然就涌上来了。")
        
        if relation == "用克体":
            parts.append("外面的什么东西在压着我，有点喘不过气。")
        elif relation == "用生体":
            parts.append("外面的什么在滋养我，暖暖的。")
        
        return " ".join(parts) if parts else f"此刻是{name}的状态。"


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    import sys
    sys.path.insert(0, _DIR)
    from hexagram_tracker import HexagramTracker
    
    print("=" * 60)
    print("卦象表达生成器 测试")
    print("=" * 60)
    
    # 从config.json读取API配置
    config_path = os.path.join(_DIR, "..", "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    llm = config.get("llm", {})
    
    generator = HexagramExpressionGenerator(
        api_key=llm.get("api_key", ""),
        base_url=llm.get("base_url", "https://api.deepseek.com/v1"),
        model=llm.get("model", "deepseek-chat"),
    )
    tracker = HexagramTracker()
    
    # 测试1：全阳→乾卦
    print("\n--- 测试1：全阳(乾卦) ---")
    r1 = tracker.update({
        "belonging": 5.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 5.0
    })
    print(f"卦象: {r1['current']['name']} | 互卦: {r1['hu']['name']} | 基线: {r1['baseline']['message_hexagram']}")
    text1 = generator.generate(r1)
    print(f"内心独白: {text1}")
    
    # 测试2：归属感降低→变卦
    print("\n--- 测试2：归属感降低(变卦) ---")
    r2 = tracker.update({
        "belonging": 2.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 5.0
    })
    print(f"卦象: {r2['current']['name']} | 变卦: {r2.get('bian',{}).get('from_hexagram',{}).get('name','')}→{r2['current']['name']} | 互卦: {r2['hu']['name']}")
    text2 = generator.generate(r2)
    print(f"内心独白: {text2}")
    
    # 测试3：无变化（缓存命中）
    print("\n--- 测试3：无变化(应缓存) ---")
    r3 = tracker.update({
        "belonging": 2.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 5.0
    })
    text3 = generator.generate(r3)
    print(f"内心独白: {text3}")
    print(f"缓存命中: {text2 == text3}")
    
    # 测试4：情绪也降→再次变卦
    print("\n--- 测试4：情绪也降(再次变卦) ---")
    r4 = tracker.update({
        "belonging": 2.0, "certainty": 5.0, "competence": 5.0,
        "autonomy": 5.0, "emotion": 2.0
    })
    print(f"卦象: {r4['current']['name']} | 变卦: {r4.get('bian',{}).get('from_hexagram',{}).get('name','')}→{r4['current']['name']} | 互卦: {r4['hu']['name']}")
    text4 = generator.generate(r4)
    print(f"内心独白: {text4}")
    
    # 测试5：fallback模板
    print("\n--- 测试5：fallback模板 ---")
    fallback = generator._fallback(r4)
    print(f"兜底: {fallback}")
    
    # 统计
    print("\n--- 统计 ---")
    info = generator.get_cache_info()
    print(f"API调用: {info['api_calls']}次 | 缓存命中: {info['cache_hits']}次 | 兜底: {info['fallback_count']}次")
    
    print("\n" + "=" * 60)
    print("测试完成")

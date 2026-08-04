#!/usr/bin/env python3
"""
内容标签弹药库 (Ammo Classifier) — P0.43

对对话内容中的概念做三层抽象归类（五行/卦象/取象），
检测天时五行与内容五行的共振关系，为三管叠加系统提供内容侧弹药。

公共API:
  - AmmoClassifier(llm_config, cache_path)
  - .classify_concept(concept)            -> dict  (单概念三层归类)
  - .classify_text(text)                   -> dict  (全文概念归类)
  - .get_content_tags(text)                -> list  (内容标签列表)
  - .detect_resonance(time_wuxing, content_wuxing) -> dict
  - .get_ammo_stats()                      -> dict  (弹药库统计)
  - .preseed_common_concepts()             -> dict  (预置20个常见概念)
"""

import json
import os
import re
import urllib.request
from datetime import datetime, date

# ─── 五行关系 ──────────────────────────────────────────────

WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
WUXING_SET = {"金", "木", "水", "火", "土"}

# ─── 停用词 ────────────────────────────────────────────────

_STOPWORDS = frozenset([
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没",
    "看", "好", "自己", "这", "那", "它", "他", "她", "们", "把", "被", "让",
    "从", "到", "向", "为", "以", "于", "对", "跟", "给", "但", "而", "或",
    "如果", "因为", "所以", "虽然", "但是", "然后", "不过", "其实", "今天",
    "明天", "昨天", "现在", "时候", "什么", "怎么", "为什么", "可以", "这个",
    "那个", "这些", "那些", "一些", "一下", "一样", "还是", "已经", "正在",
    "应该", "可能", "觉得", "知道", "以为", "发现", "感觉", "想到", "聊了",
    "聊聊", "说了", "谈到", "提到", "关于", "进行", "开始", "结束", "需要",
    "想要", "觉得", "的话", "的话", "就是", "这种", "那种", "东西", "事情",
    "地方", "时候", "时间", "问题", "方面", "感觉", "内容", "一点", "一下",
])

# ─── 预置概念种子 ──────────────────────────────────────────

PRESEED_CONCEPTS = {
    "投资": {"wuxing": ["金", "水"], "wuxing_weights": {"金": 0.6, "水": 0.4},
             "hexagram": ["兑", "坎"], "imagery": ["兑.羊", "坎.豕"], "confidence": 0.9},
    "股票": {"wuxing": ["金", "火"], "wuxing_weights": {"金": 0.5, "火": 0.5},
             "hexagram": ["兑", "离"], "imagery": ["兑.羊", "离.雉"], "confidence": 0.85},
    "创作": {"wuxing": ["木", "火"], "wuxing_weights": {"木": 0.6, "火": 0.4},
             "hexagram": ["震", "离"], "imagery": ["震.龙", "离.雉"], "confidence": 0.9},
    "写作": {"wuxing": ["木"], "wuxing_weights": {"木": 1.0},
             "hexagram": ["巽"], "imagery": ["巽.鸡"], "confidence": 0.9},
    "值班": {"wuxing": ["土"], "wuxing_weights": {"土": 1.0},
             "hexagram": ["艮"], "imagery": ["艮.狗"], "confidence": 0.85},
    "工作": {"wuxing": ["金", "土"], "wuxing_weights": {"金": 0.5, "土": 0.5},
             "hexagram": ["乾", "坤"], "imagery": ["乾.马", "坤.牛"], "confidence": 0.9},
    "学习": {"wuxing": ["水"], "wuxing_weights": {"水": 1.0},
             "hexagram": ["坎"], "imagery": ["坎.豕"], "confidence": 0.9},
    "考试": {"wuxing": ["金", "火"], "wuxing_weights": {"金": 0.4, "火": 0.6},
             "hexagram": ["兑", "离"], "imagery": ["兑.羊", "离.雉"], "confidence": 0.85},
    "游戏": {"wuxing": ["火", "木"], "wuxing_weights": {"火": 0.6, "木": 0.4},
             "hexagram": ["离", "震"], "imagery": ["离.雉", "震.龙"], "confidence": 0.85},
    "音乐": {"wuxing": ["水", "木"], "wuxing_weights": {"水": 0.5, "木": 0.5},
             "hexagram": ["坎", "巽"], "imagery": ["坎.豕", "巽.鸡"], "confidence": 0.9},
    "运动": {"wuxing": ["木", "火"], "wuxing_weights": {"木": 0.5, "火": 0.5},
             "hexagram": ["震", "离"], "imagery": ["震.龙", "离.雉"], "confidence": 0.9},
    "旅行": {"wuxing": ["水", "木"], "wuxing_weights": {"水": 0.5, "木": 0.5},
             "hexagram": ["坎", "巽"], "imagery": ["坎.豕", "巽.鸡"], "confidence": 0.85},
    "美食": {"wuxing": ["火", "土"], "wuxing_weights": {"火": 0.5, "土": 0.5},
             "hexagram": ["离", "坤"], "imagery": ["离.雉", "坤.牛"], "confidence": 0.9},
    "睡眠": {"wuxing": ["水", "土"], "wuxing_weights": {"水": 0.5, "土": 0.5},
             "hexagram": ["坎", "坤"], "imagery": ["坎.豕", "坤.牛"], "confidence": 0.9},
    "健康": {"wuxing": ["木", "土"], "wuxing_weights": {"木": 0.5, "土": 0.5},
             "hexagram": ["震", "坤"], "imagery": ["震.龙", "坤.牛"], "confidence": 0.9},
    "恋爱": {"wuxing": ["火", "水"], "wuxing_weights": {"火": 0.6, "水": 0.4},
             "hexagram": ["离", "坎"], "imagery": ["离.雉", "坎.豕"], "confidence": 0.85},
    "家庭": {"wuxing": ["土"], "wuxing_weights": {"土": 1.0},
             "hexagram": ["坤"], "imagery": ["坤.牛"], "confidence": 0.9},
    "编程": {"wuxing": ["金", "火"], "wuxing_weights": {"金": 0.5, "火": 0.5},
             "hexagram": ["乾", "离"], "imagery": ["乾.马", "离.雉"], "confidence": 0.85},
    "阅读": {"wuxing": ["木", "水"], "wuxing_weights": {"木": 0.5, "水": 0.5},
             "hexagram": ["巽", "坎"], "imagery": ["巽.鸡", "坎.豕"], "confidence": 0.9},
    "思考": {"wuxing": ["水"], "wuxing_weights": {"水": 1.0},
             "hexagram": ["坎", "乾"], "imagery": ["坎.豕", "乾.马"], "confidence": 0.9},
}


# ─── DeepSeek API 调用 ─────────────────────────────────────

def _call_deepseek_api(api_key: str, base_url: str, model: str,
                       system_prompt: str, user_prompt: str,
                       max_tokens: int = 800) -> str:
    """用 urllib.request 调用 DeepSeek API，返回纯文本响应。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    return body["choices"][0]["message"]["content"]


# ─── LLM 归类 Prompt ──────────────────────────────────────

_SYSTEM_PROMPT = """你是一个精通中国传统术数的分类专家。你的任务是对中文词语/概念进行三层抽象归类。

三层归类规则:
1. 五行属性(金/木/水/火/土，可多选): 判断该概念最核心的五行属性，附带权重(0-1，总和为1)
2. 关联卦象(八卦: 乾/坤/震/巽/坎/离/艮/兑，可多选): 判断该概念最关联的卦象
3. 关联取象(说卦传取象，如马/君/龙/鸡/牛/豕/雉/狗/羊等): 判断该概念对应的取象，格式为"卦名.取象"

八卦取象对照:
- 乾: 天/君/父/马/金
- 坤: 地/母/牛/布
- 震: 雷/龙/长男
- 巽: 风/木/鸡/长女
- 坎: 水/豕/中男
- 离: 火/雉/中女
- 艮: 山/狗/少男
- 兑: 泽/羊/少女

你必须返回合法JSON，格式如下:
{
  "wuxing": ["金", "水"],
  "wuxing_weights": {"金": 0.6, "水": 0.4},
  "hexagram": ["兑", "坎"],
  "imagery": ["兑.羊", "坎.豕"]
}"""

_USER_PROMPT_TEMPLATE = "请对以下中文概念进行三层归类: \"{concept}\""


# ─── 基础中文分词 ──────────────────────────────────────────

# 分词前先按标点切分
_SPLIT_CHARS = re.compile(r"[，。！？、；：""''（）【】\s,\.!?;:\"'()\[\]\/\\@#\$%\^&\*\-_=\+<>]")
# 常见虚词/连接词，用于切分长中文段（用正则交替匹配）
_FUNCTION_WORDS = re.compile(
    r"今天|明天|昨天|现在|时候|可以|应该|可能|觉得|知道|发现|感觉|想到"
    r"|的话|就是|这种|那种|东西|事情|地方|时间|问题|方面|内容"
    r"|聊了|聊聊|说了|谈到|提到|关于|进行|开始|结束|需要|想要"
    r"|的|了|着|过|和|与|及|或|把|被|让|从|到|向|为|以|于|对"
    r"|跟|给|但|而|就|也|都|还|又|再|才|只|便|即|已|正|在"
    r"|会|能|可|应|要|想|需|觉|知|说|聊|谈|提|关|进|开|结"
    r"|这|那|它|他|她|们|我|你|不|没|看|好|一"
)

def _basic_tokenize(text: str) -> list:
    """
    基础中文分词（不依赖jieba）:
    1. 按标点和虚词切分为短段
    2. 对每段用2-3字滑窗提取候选词
    3. 过滤停用词，去除被长词包含的短词
    """
    # 先按标点和空格切分
    parts = _SPLIT_CHARS.split(text)
    # 再按常见虚词切分
    segments = []
    for part in parts:
        sub_parts = _FUNCTION_WORDS.split(part)
        segments.extend(sub_parts)

    candidates = set()
    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 2:
            continue
        if len(seg) == 2:
            # 2字段：整段作为候选
            if seg not in _STOPWORDS:
                candidates.add(seg)
        elif len(seg) == 3:
            # 3字段：整段 + 2-gram
            if seg not in _STOPWORDS:
                candidates.add(seg)
            for i in range(2):
                word = seg[i:i + 2]
                if word not in _STOPWORDS:
                    candidates.add(word)
        else:
            # 4+字段：只取2-gram（多数中文词为2字）
            for i in range(len(seg) - 1):
                word = seg[i:i + 2]
                if word not in _STOPWORDS:
                    candidates.add(word)

    # 去除被更长候选包含的短词
    filtered = []
    for w in sorted(candidates, key=len, reverse=True):
        if any(w in longer and w != longer for longer in filtered):
            continue
        filtered.append(w)

    return filtered


# ─── 主类 ──────────────────────────────────────────────────

class AmmoClassifier:
    """
    内容标签弹药库分类器。

    参数:
        llm_config: dict，包含 base_url / api_key / model
        cache_path: str，弹药库JSON缓存路径
    """

    def __init__(self, llm_config: dict, cache_path: str = "data/ammo_library.json"):
        self.llm_config = llm_config or {}
        self.api_key = llm_config.get("api_key", "")
        self.base_url = llm_config.get("base_url", "https://api.deepseek.com/v1")
        self.model = llm_config.get("model", "deepseek-chat")
        self.cache_path = cache_path
        self._cache = self._load_cache()

    # ─── 缓存管理 ───

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_cache(self):
        cache_dir = os.path.dirname(self.cache_path)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def _make_entry(self, concept: str, classification: dict,
                    source: str = "llm_analysis", confidence: float = 0.8) -> dict:
        today = date.today().isoformat()
        return {
            "wuxing": classification.get("wuxing", []),
            "wuxing_weights": classification.get("wuxing_weights", {}),
            "hexagram": classification.get("hexagram", []),
            "imagery": classification.get("imagery", []),
            "classified_at": today,
            "source": source,
            "confidence": confidence,
        }

    # ─── 公共方法 ───

    def classify_concept(self, concept: str) -> dict:
        """
        对单个概念做三层抽象归类。
        先查缓存，缓存未命中则调 DeepSeek API 归类，结果写入缓存。
        """
        if concept in self._cache:
            return self._cache[concept]

        # 调用 LLM
        if not self.api_key:
            # 无API key，返回空归类
            entry = self._make_entry(concept, {}, source="fallback", confidence=0.0)
        else:
            try:
                user_prompt = _USER_PROMPT_TEMPLATE.format(concept=concept)
                raw = _call_deepseek_api(
                    self.api_key, self.base_url, self.model,
                    _SYSTEM_PROMPT, user_prompt,
                )
                classification = json.loads(raw)
                entry = self._make_entry(concept, classification, source="llm_analysis", confidence=0.8)
            except Exception as e:
                entry = self._make_entry(concept, {}, source="error", confidence=0.0)
                entry["error"] = str(e)

        self._cache[concept] = entry
        self._save_cache()
        return entry

    def classify_text(self, text: str) -> dict:
        """
        从对话文本中提取关键概念，对每个新概念调用 classify_concept，
        返回所有概念的三层归类。
        """
        concepts = _basic_tokenize(text)
        result = {}
        for concept in concepts:
            result[concept] = self.classify_concept(concept)
        return {
            "text": text,
            "concept_count": len(result),
            "concepts": result,
        }

    def get_content_tags(self, text: str) -> list:
        """
        返回内容标签列表，每个标签含:
        {concept, wuxing[], hexagram[], imagery[], weight}
        """
        concepts = _basic_tokenize(text)
        tags = []
        for concept in concepts:
            entry = self.classify_concept(concept)
            tags.append({
                "concept": concept,
                "wuxing": entry.get("wuxing", []),
                "hexagram": entry.get("hexagram", []),
                "imagery": entry.get("imagery", []),
                "weight": entry.get("wuxing_weights", {}),
            })
        return tags

    def detect_resonance(self, time_wuxing, content_wuxing) -> dict:
        """
        检测天时五行和内容五行的共振关系。

        参数:
            time_wuxing: str 或 list[str]，天时五行
            content_wuxing: str 或 list[str]，内容五行

        返回:
            {relation: "共振/相生/相克/无关", weight_multiplier: float, detail: str}
        """
        # 归一化为列表
        if isinstance(time_wuxing, str):
            time_list = [time_wuxing]
        else:
            time_list = list(time_wuxing) if time_wuxing else []

        if isinstance(content_wuxing, str):
            content_list = [content_wuxing]
        else:
            content_list = list(content_wuxing) if content_wuxing else []

        # 过滤无效值
        time_list = [w for w in time_list if w in WUXING_SET]
        content_list = [w for w in content_list if w in WUXING_SET]

        if not time_list or not content_list:
            return {"relation": "无关", "weight_multiplier": 1.0, "detail": "五行数据不足"}

        # 取天时主五行（第一个）
        t_wx = time_list[0]

        # 关系优先级: 共振 > 相克 > 相生 > 无关（任何实际关系都优先于无关）
        _PRIORITY = {"共振": 4, "相克": 3, "相生": 2, "无关": 1}

        best_relation = "无关"
        best_multiplier = 1.0
        best_detail = ""

        for c_wx in content_list:
            if t_wx == c_wx:
                rel, mult = "共振", 1.5
                detail = f"天时{t_wx}与内容{c_wx}同五行"
            elif WUXING_SHENG.get(t_wx) == c_wx:
                rel, mult = "相生", 1.3
                detail = f"天时{t_wx}生内容{c_wx}（顺势）"
            elif WUXING_SHENG.get(c_wx) == t_wx:
                rel, mult = "相生", 1.3
                detail = f"内容{c_wx}生天时{t_wx}（顺势）"
            elif WUXING_KE.get(t_wx) == c_wx:
                rel, mult = "相克", 0.7
                detail = f"天时{t_wx}克内容{c_wx}（冲突）"
            elif WUXING_KE.get(c_wx) == t_wx:
                rel, mult = "相克", 0.7
                detail = f"内容{c_wx}克天时{t_wx}（冲突）"
            else:
                rel, mult = "无关", 1.0
                detail = f"天时{t_wx}与内容{c_wx}无直接关系"

            # 按优先级取最强关系（共振>相克>相生>无关）
            if _PRIORITY[rel] > _PRIORITY[best_relation]:
                best_relation = rel
                best_multiplier = mult
                best_detail = detail

        return {
            "relation": best_relation,
            "weight_multiplier": best_multiplier,
            "detail": best_detail,
        }

    def get_ammo_stats(self) -> dict:
        """返回弹药库统计（已缓存概念数、五行分布）。"""
        total = len(self._cache)
        wuxing_dist = {}
        source_dist = {}
        for concept, entry in self._cache.items():
            for wx in entry.get("wuxing", []):
                wuxing_dist[wx] = wuxing_dist.get(wx, 0) + 1
            src = entry.get("source", "unknown")
            source_dist[src] = source_dist.get(src, 0) + 1

        return {
            "total_concepts": total,
            "wuxing_distribution": wuxing_dist,
            "source_distribution": source_dist,
            "cache_path": self.cache_path,
        }

    def preseed_common_concepts(self) -> dict:
        """
        预置20个常见概念，每个手动填好三层归类，写入缓存。
        已存在的概念不会被覆盖。
        """
        today = date.today().isoformat()
        added = []
        skipped = []
        for concept, data in PRESEED_CONCEPTS.items():
            if concept in self._cache:
                skipped.append(concept)
                continue
            entry = {
                "wuxing": data["wuxing"],
                "wuxing_weights": data["wuxing_weights"],
                "hexagram": data["hexagram"],
                "imagery": data["imagery"],
                "classified_at": today,
                "source": "preseed",
                "confidence": data["confidence"],
            }
            self._cache[concept] = entry
            added.append(concept)

        self._save_cache()
        return {
            "added": added,
            "skipped": skipped,
            "total_after": len(self._cache),
        }


# ─── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="内容标签弹药库")
    parser.add_argument("--text", type=str, default="", help="要分类的文本")
    parser.add_argument("--concept", type=str, default="", help="要分类的单个概念")
    parser.add_argument("--preseed", action="store_true", help="预置常见概念")
    parser.add_argument("--stats", action="store_true", help="查看弹药库统计")
    parser.add_argument("--resonance", nargs=2, metavar=("TIME_WX", "CONTENT_WX"),
                        help="检测共振，如: --resonance 水 金")
    parser.add_argument("--cache", type=str, default="data/ammo_library.json", help="缓存路径")
    args = parser.parse_args()

    # 从环境或默认值获取LLM配置
    llm_cfg = {
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": "deepseek-chat",
    }
    classifier = AmmoClassifier(llm_cfg, cache_path=args.cache)

    if args.preseed:
        print(json.dumps(classifier.preseed_common_concepts(), ensure_ascii=False, indent=2))
    elif args.stats:
        print(json.dumps(classifier.get_ammo_stats(), ensure_ascii=False, indent=2))
    elif args.resonance:
        result = classifier.detect_resonance(args.resonance[0], args.resonance[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.concept:
        result = classifier.classify_concept(args.concept)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.text:
        result = classifier.classify_text(args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()

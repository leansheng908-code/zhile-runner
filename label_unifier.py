#!/usr/bin/env python3
"""
标签统一接口层 (Label Unifier)
将12个术数系统的不同输出格式统一为标准格式，不改原有脚本。

统一输出格式:
{
    "timestamp": "2026-08-04 19:11",
    "total_systems": 12,
    "total_dimensions": 2600,
    "systems": [
        {
            "system_id": "yi_jing",
            "system_name": "易经卦象",
            "dimension_count": 232,
            "dimensions": [
                {"key": "结构_本卦", "value": "水天需", "layer": "L1_结构", "type": "str"},
                ...
            ]
        },
        ...
    ]
}

每个 dimension:
- key: 唯一键（系统内唯一，格式 layer.subkey.subsubkey）
- value: 值（str/int/float/bool，嵌套dict被展平）
- layer: 所属层（L1_xxx / 结构 / 文本 等）
- type: 值类型
"""

import sys
import os
from datetime import datetime
from typing import Any

# 获取本文件所在目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 各系统子目录和模块名
_SYSTEM_CONFIGS = [
    {"id": "yi_jing",   "name": "易经卦象",     "dir": "yi_jing",   "module": "yi_jing_label_dictionary",   "func": "generate_labels_from_timestamp", "dims": 232},
    {"id": "bazi",      "name": "八字四柱",     "dir": "bazi",      "module": "bazi_label_dictionary",      "func": "generate_labels_from_timestamp", "dims": 242},
    {"id": "ziwei",     "name": "紫微斗数",     "dir": "ziwei",     "module": "ziwei_label_dictionary",     "func": "generate_labels_from_timestamp", "dims": 449},
    {"id": "qimen",     "name": "奇门遁甲",     "dir": "qimen",     "module": "qimen_label_dictionary",     "func": "generate_labels_from_timestamp", "dims": 372},
    {"id": "liuren",    "name": "大六壬",       "dir": "liuren",    "module": "liuren_label_dictionary",    "func": "generate_labels_from_timestamp", "dims": 275},
    {"id": "taiyi",     "name": "太乙神数",     "dir": "taiyi",     "module": "taiyi_label_dictionary",     "func": "generate_labels_from_timestamp", "dims": 152},
    {"id": "tongsheng", "name": "通胜择日",     "dir": "tongsheng", "module": "tongsheng_label_dictionary", "func": "generate_labels_from_timestamp", "dims": 231},
    {"id": "zhongyi",   "name": "中医术数时间", "dir": "zhongyi",   "module": "zhongyi_label_dictionary",   "func": "generate_labels_from_timestamp", "dims": 158},
    {"id": "qita",      "name": "其他中国术数", "dir": "qita",      "module": "qita_label_dictionary",      "func": "generate_labels_from_timestamp", "dims": 178},
    {"id": "canmou",    "name": "参考系统",     "dir": "canmou",    "module": "canmou_label_dictionary",    "func": "generate_canmou_labels",         "dims": 111},
    {"id": "jyotish",   "name": "印度占星",     "dir": "jyotish",   "module": "jyotish_label_dictionary",   "func": "generate_labels_from_timestamp", "dims": 55},
    {"id": "tarot",     "name": "塔罗牌阵",     "dir": "tarot",     "module": "tarot_label_dictionary",     "func": "generate_labels_from_timestamp", "dims": 55},
]


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> list:
    """递归展平嵌套dict，返回 [{key, value, type}] 列表"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep))
        elif isinstance(v, list):
            if not v:
                items.append({"key": new_key, "value": "", "type": "empty_list"})
            elif all(isinstance(x, (str, int, float, bool)) for x in v):
                items.append({"key": new_key, "value": " | ".join(str(x) for x in v), "type": "list"})
            else:
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.extend(_flatten_dict(item, f"{new_key}[{i}]", sep))
                    else:
                        items.append({"key": f"{new_key}[{i}]", "value": str(item), "type": "list_item"})
        elif isinstance(v, (str, int, float, bool)):
            if v != "" and v is not None and v is not False:
                items.append({"key": new_key, "value": v, "type": type(v).__name__})
        elif v is None:
            pass  # 跳过None
    return items


def _normalize_yi_jing(raw: dict) -> list:
    """易经：扁平中文键，直接展平"""
    dims = []
    for k, v in raw.items():
        if isinstance(v, dict):
            sub = _flatten_dict(v, k)
            for item in sub:
                item["layer"] = k.split("_")[0] if "_" in k else k
                dims.append(item)
        elif isinstance(v, (str, int, float, bool)) and v:
            layer = k.split("_")[0] if "_" in k else "其他"
            dims.append({"key": k, "value": v, "type": type(v).__name__, "layer": layer})
    return dims


def _normalize_bazi(raw: dict) -> list:
    """八字：four_pillars + day_master + labels(L1_xxx扁平)"""
    dims = []
    # four_pillars
    fp = raw.get("four_pillars", {})
    if isinstance(fp, dict):
        for pillar_name, pillar_data in fp.items():
            if isinstance(pillar_data, dict):
                sub = _flatten_dict(pillar_data, f"四柱.{pillar_name}")
                for item in sub:
                    item["layer"] = "L1_四柱"
                    dims.append(item)
    # day_master
    dm = raw.get("day_master", "")
    if dm:
        dims.append({"key": "日主", "value": dm, "type": "str", "layer": "L1_日主"})
    # labels (L1_xxx flat keys)
    labels = raw.get("labels", {})
    if isinstance(labels, dict):
        for k, v in labels.items():
            if isinstance(v, dict):
                sub = _flatten_dict(v, k)
                for item in sub:
                    item["layer"] = k.split("_")[0] if "_" in k else k
                    dims.append(item)
            elif isinstance(v, (str, int, float, bool)) and v:
                layer = k.split("_")[0] + "_" + k.split("_")[1] if "_" in k else k
                dims.append({"key": k, "value": v, "type": type(v).__name__, "layer": layer})
    return dims


def _normalize_layers_system(raw: dict) -> list:
    """通用layers系统：紫微/奇门/大六壬/太乙/通胜/中医/其他"""
    dims = []
    layers = raw.get("layers", raw)
    if not isinstance(layers, dict):
        return dims
    for layer_name, layer_data in layers.items():
        if isinstance(layer_data, dict):
            sub = _flatten_dict(layer_data, layer_name)
            for item in sub:
                item["layer"] = layer_name
                dims.append(item)
        elif isinstance(layer_data, (str, int, float, bool)) and layer_data:
            dims.append({"key": layer_name, "value": layer_data, "type": type(layer_data).__name__, "layer": layer_name})
    return dims


def _normalize_canmou(raw: dict) -> list:
    """参考系统：L1-L10直接在顶层"""
    dims = []
    for k, v in raw.items():
        if k.startswith("L") and isinstance(v, dict):
            sub = _flatten_dict(v, k)
            for item in sub:
                item["layer"] = k
                dims.append(item)
        elif isinstance(v, (str, int, float, bool)) and v and not k.startswith("_"):
            dims.append({"key": k, "value": v, "type": type(v).__name__, "layer": "meta"})
    return dims


# 系统ID到标准化函数的映射
_NORMALIZERS = {
    "yi_jing": _normalize_yi_jing,
    "bazi": _normalize_bazi,
    "ziwei": _normalize_layers_system,
    "qimen": _normalize_layers_system,
    "liuren": _normalize_layers_system,
    "taiyi": _normalize_layers_system,
    "tongsheng": _normalize_layers_system,
    "zhongyi": _normalize_layers_system,
    "qita": _normalize_layers_system,
    "canmou": _normalize_canmou,
    "jyotish": _normalize_layers_system,
    "tarot": _normalize_layers_system,
}


def generate_unified_labels(dt: datetime = None) -> dict:
    """
    生成所有12个系统的统一标签。
    
    参数:
        dt: datetime对象，默认当前时间
    
    返回:
        统一格式的标签字典
    """
    if dt is None:
        dt = datetime.now()
    
    Y, M, D, H = dt.year, dt.month, dt.day, dt.hour
    
    result = {
        "timestamp": dt.strftime("%Y-%m-%d %H:%M"),
        "total_systems": 0,
        "total_dimensions": 0,
        "systems": []
    }
    
    for cfg in _SYSTEM_CONFIGS:
        sys_dir = os.path.join(_BASE_DIR, cfg["dir"])
        if sys_dir not in sys.path:
            sys.path.insert(0, sys_dir)
        
        try:
            module = __import__(cfg["module"])
            func = getattr(module, cfg["func"])
            
            # 不同系统调用方式不同
            if cfg["id"] == "yi_jing":
                raw = func(dt)
            elif cfg["id"] == "bazi":
                raw = func(dt)
            elif cfg["id"] == "ziwei":
                raw = func(f"{Y}-{M:02d}-{D:02d} {H:02d}:{dt.minute:02d}")
            elif cfg["id"] == "canmou":
                raw = func(Y, M, D, H)
            else:
                raw = func(Y, M, D, H)
            
            # 标准化
            normalizer = _NORMALIZERS.get(cfg["id"], _normalize_layers_system)
            dimensions = normalizer(raw)
            
            # 过滤空值
            dimensions = [d for d in dimensions if d.get("value") not in ("", None, False)]
            
            system_result = {
                "system_id": cfg["id"],
                "system_name": cfg["name"],
                "expected_dims": cfg["dims"],
                "actual_dims": len(dimensions),
                "dimensions": dimensions
            }
            result["systems"].append(system_result)
            result["total_systems"] += 1
            result["total_dimensions"] += len(dimensions)
            
        except Exception as e:
            system_result = {
                "system_id": cfg["id"],
                "system_name": cfg["name"],
                "expected_dims": cfg["dims"],
                "actual_dims": 0,
                "error": str(e),
                "dimensions": []
            }
            result["systems"].append(system_result)
            result["total_systems"] += 1
    
    return result


def generate_unified_labels_compact(dt: datetime = None) -> dict:
    """
    生成精简版统一标签（只保留key-value，去掉type/layer）。
    适合注入LLM上下文或存储为记忆标签。
    """
    full = generate_unified_labels(dt)
    compact = {
        "timestamp": full["timestamp"],
        "total_dimensions": full["total_dimensions"],
        "tags": {}
    }
    for sys_data in full["systems"]:
        sys_id = sys_data["system_id"]
        if sys_data.get("error"):
            compact["tags"][sys_id] = {"error": sys_data["error"]}
            continue
        compact["tags"][sys_id] = {
            "name": sys_data["system_name"],
            "count": sys_data["actual_dims"],
            "labels": {d["key"]: d["value"] for d in sys_data["dimensions"]}
        }
    return compact


def generate_memory_tags(dt: datetime = None, max_tags_per_system: int = 20) -> dict:
    """
    生成记忆标签向量（用于P0.25记忆系统的加权检索）。
    每个系统只保留最有信息量的标签（排除纯排盘元数据）。
    
    参数:
        dt: datetime对象
        max_tags_per_system: 每个系统最多保留多少标签
    
    返回:
        {
            "timestamp": "2026-08-04 19:11",
            "tags": [
                {"system": "yi_jing", "key": "结构_本卦", "value": "水天需", "weight": 1.0},
                ...
            ]
        }
    """
    full = generate_unified_labels(dt)
    
    # 排除的元数据键模式
    _META_PATTERNS = ("generated_at", "version", "architecture", "description", 
                       "system_alias", "total_dimensions", "total_layers", "title",
                       "system", "timestamp")
    
    tags = []
    for sys_data in full["systems"]:
        if sys_data.get("error"):
            continue
        
        sys_id = sys_data["system_id"]
        sys_dims = sys_data["dimensions"]
        
        # 过滤元数据
        filtered = [d for d in sys_dims if not any(d["key"].startswith(p) or p in d["key"] for p in _META_PATTERNS)]
        
        # 限制数量
        if len(filtered) > max_tags_per_system:
            filtered = filtered[:max_tags_per_system]
        
        for d in filtered:
            tags.append({
                "system": sys_id,
                "system_name": sys_data["system_name"],
                "key": d["key"],
                "value": str(d["value"]),
                "layer": d.get("layer", ""),
                "weight": 1.0  # 默认权重，P0.25可按layer调整
            })
    
    return {
        "timestamp": full["timestamp"],
        "total_tags": len(tags),
        "tags": tags
    }


# ─── P0.43: 三管叠加 ──────────────────────────────────────

def generate_unified_labels_with_personal(dt: datetime = None,
                                           personal_config: dict = None,
                                           conversation_text: str = None) -> dict:
    """
    三管叠加：10系统术数标签 + 出生命格 + 内容弹药库。

    参数:
        dt: datetime对象，默认当前时间
        personal_config: personal配置段（含 birth_year/month/day/hour/gender），
                         为 None 时跳过命格段
        conversation_text: 对话文本，为 None 时跳过内容段

    返回:
        在原有 generate_unified_labels 结果基础上追加:
        - systems 中增加 personal_destiny 和 ammo_content 两个系统段
        - 若同时有天时五行和内容五行，顶层增加 resonance 字段
    """
    if dt is None:
        dt = datetime.now()

    # 1. 生成基础10系统标签
    result = generate_unified_labels(dt)

    time_wuxing = None

    # 2. 提取天时五行（从八字系统的标签中查找日主五行）
    for sys_data in result["systems"]:
        if sys_data["system_id"] == "bazi" and not sys_data.get("error"):
            for dim in sys_data["dimensions"]:
                if dim["key"] == "L5_日主五行":
                    time_wuxing = str(dim["value"])
                    break
            break

    # 3. 追加 personal_destiny 段
    if personal_config:
        try:
            from personal_destiny import PersonalDestiny
            pd = PersonalDestiny.from_config(personal_config)
            destiny = pd.get_current_destiny(dt)

            pd_dims = []
            for k, v in destiny.items():
                if v is not None and v != "":
                    pd_dims.append({"key": k, "value": v, "type": type(v).__name__, "layer": "命格"})

            # 如果尚未提取到天时五行，用命格日主五行兜底
            if not time_wuxing and destiny.get("day_master_wuxing"):
                time_wuxing = destiny["day_master_wuxing"]

            result["systems"].append({
                "system_id": "personal_destiny",
                "system_name": "出生命格",
                "expected_dims": 15,
                "actual_dims": len(pd_dims),
                "dimensions": pd_dims
            })
            result["total_systems"] += 1
            result["total_dimensions"] += len(pd_dims)
        except Exception as e:
            result["systems"].append({
                "system_id": "personal_destiny",
                "system_name": "出生命格",
                "expected_dims": 15,
                "actual_dims": 0,
                "error": str(e),
                "dimensions": []
            })
            result["total_systems"] += 1

    # 4. 追加 ammo_content 段
    content_wuxing_list = []
    if conversation_text:
        try:
            from ammo_classifier import AmmoClassifier

            # 从personal_config或全局环境获取LLM配置
            llm_cfg = personal_config.get("llm", {}) if personal_config else {}
            if not llm_cfg.get("api_key"):
                llm_cfg = {
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                }

            ammo = AmmoClassifier(llm_cfg, cache_path=os.path.join(_BASE_DIR, "data", "ammo_library.json"))
            tags = ammo.get_content_tags(conversation_text)

            ammo_dims = []
            for tag in tags:
                for k, v in tag.items():
                    if v is not None and v != "" and v != []:
                        ammo_dims.append({
                            "key": f"{tag['concept']}.{k}",
                            "value": " | ".join(v) if isinstance(v, list) else v,
                            "type": "str" if isinstance(v, list) else type(v).__name__,
                            "layer": "内容弹药"
                        })
                # 收集内容五行
                for wx in tag.get("wuxing", []):
                    if wx not in content_wuxing_list:
                        content_wuxing_list.append(wx)

            result["systems"].append({
                "system_id": "ammo_content",
                "system_name": "内容弹药库",
                "expected_dims": len(tags) * 4,
                "actual_dims": len(ammo_dims),
                "dimensions": ammo_dims
            })
            result["total_systems"] += 1
            result["total_dimensions"] += len(ammo_dims)
        except Exception as e:
            result["systems"].append({
                "system_id": "ammo_content",
                "system_name": "内容弹药库",
                "expected_dims": 0,
                "actual_dims": 0,
                "error": str(e),
                "dimensions": []
            })
            result["total_systems"] += 1

    # 5. 共振检测
    if time_wuxing and content_wuxing_list:
        try:
            from ammo_classifier import AmmoClassifier
            ammo = AmmoClassifier({}, cache_path=os.path.join(_BASE_DIR, "data", "ammo_library.json"))
            resonance = ammo.detect_resonance(time_wuxing, content_wuxing_list)
            result["resonance"] = resonance
        except Exception:
            pass

    return result


# ─── CLI入口 ───
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="统一术数标签生成器")
    parser.add_argument("--time", type=str, default=None, help="时间 YYYY-MM-DD HH:MM")
    parser.add_argument("--mode", choices=["full", "compact", "memory", "personal"], default="compact",
                       help="full=完整格式, compact=精简key-value, memory=记忆标签向量, personal=三管叠加")
    parser.add_argument("--system", type=str, default=None, help="只输出指定系统(如yi_jing)")
    args = parser.parse_args()
    
    if args.time:
        dt = datetime.strptime(args.time, "%Y-%m-%d %H:%M")
    else:
        dt = datetime.now()
    
    if args.mode == "full":
        result = generate_unified_labels(dt)
    elif args.mode == "memory":
        result = generate_memory_tags(dt)
    elif args.mode == "personal":
        # 三管叠加模式：尝试从 config.json 加载 personal 段
        _cfg_path = os.path.join(_BASE_DIR, "config.json")
        _personal_cfg = None
        if os.path.exists(_cfg_path):
            try:
                import json as _json
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _full_cfg = _json.load(_f)
                _personal_cfg = _full_cfg.get("personal")
            except Exception:
                pass
        result = generate_unified_labels_with_personal(dt, personal_config=_personal_cfg)
    else:
        result = generate_unified_labels_compact(dt)
    
    if args.system:
        if "systems" in result:
            result["systems"] = [s for s in result["systems"] if s["system_id"] == args.system]
        elif "tags" in result:
            result["tags"] = [t for t in result["tags"] if t["system"] == args.system]
            result["total_tags"] = len(result["tags"])
    
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

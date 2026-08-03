#!/usr/bin/env python3
"""
P0.26 Phase 1 — 插件模板填充器

设计理念：运行器不从零写代码，而是按预设模板填充。
覆盖大部分日常需求——加规则、加模板、加简单工具。
依赖：P0.4插件系统 + P0.7插件路由器 + P0.19技能自学习框架

工作流程：
  1. observe() — 观察到需要新能力（用户请求或自成长扫描）
  2. select_template() — 从模板库选择匹配模板
  3. fill_template() — LLM生成填充内容
  4. validate() — 语法检查+安全检查
  5. install() — 写入plugins/目录+注册manifest
  6. test() — 加载测试

模板类型：
  - route_rule    — 认知路由规则（填正则+回复模板）
  - reply_template — 模板回复（填触发条件+回复内容）
  - simple_tool   — 简单工具调用（填API URL+参数映射）
  - context_inject — 上下文注入（填注入内容+触发条件）
"""

import os
import json
import re
import ast
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TemplateFiller:
    """插件模板填充器 — P0.26 Phase 1"""

    # 模板目录
    TEMPLATES_DIR = "plugin_templates"

    # 模板类型描述（供LLM选择）
    TEMPLATE_TYPES = {
        "route_rule": "认知路由规则 — 匹配用户消息模式，返回预设回复或触发动作",
        "reply_template": "模板回复 — 按触发条件生成格式化回复",
        "simple_tool": "简单工具 — 调用外部API并格式化返回结果",
        "context_inject": "上下文注入 — 在特定条件下向system prompt注入额外信息",
    }

    def __init__(self, config: dict = None, core=None):
        self.config = config or {}
        self.core = core
        self.enabled = self.config.get("enabled", True)
        self.templates_dir = self.config.get("templates_dir", self.TEMPLATES_DIR)
        self.plugins_dir = self.config.get("plugins_dir", "plugins")

        # 模板缓存
        self._templates: Dict[str, str] = {}
        self._load_templates()

        # 创建历史
        self._history: List[dict] = []
        self._history_file = os.path.join(self.plugins_dir, "template_history.json")
        self._load_history()

    # ─── 模板加载 ──────────────────────────────

    def _load_templates(self):
        """加载所有模板文件"""
        templates_path = Path(self.templates_dir)
        if not templates_path.exists():
            return

        for f in templates_path.glob("*.py.template"):
            name = f.stem.replace(".py", "")  # route_rule.py.template -> route_rule
            with open(f, "r", encoding="utf-8") as fh:
                self._templates[name] = fh.read()

    def list_templates(self) -> Dict[str, str]:
        """列出可用模板"""
        return {name: self.TEMPLATE_TYPES.get(name, "未知类型")
                for name in self._templates.keys()}

    # ─── 核心流程 ──────────────────────────────

    def select_template(self, requirement: str) -> Optional[str]:
        """
        根据需求描述选择最合适的模板类型
        零token关键词匹配，不调用LLM
        """
        req_lower = requirement.lower()

        # 关键词→模板映射
        keyword_map = {
            "route_rule": ["路由", "匹配", "规则", "关键词", "正则", "route", "pattern", "match"],
            "reply_template": ["回复", "模板", "回答", "reply", "template", "response"],
            "simple_tool": ["工具", "查询", "api", "接口", "tool", "query", "search", "weather", "天气"],
            "context_inject": ["注入", "上下文", "context", "inject", "补充信息"],
        }

        scores = {}
        for template_type, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in req_lower)
            if score > 0:
                scores[template_type] = score

        if not scores:
            # 默认使用reply_template
            return "reply_template" if "reply_template" in self._templates else None

        return max(scores, key=scores.get)

    def fill_template(self, template_type: str, requirement: str,
                      llm_caller=None) -> Optional[dict]:
        """
        使用LLM填充模板

        Args:
            template_type: 模板类型
            requirement: 需求描述
            llm_caller: LLM调用函数 (str) -> str

        Returns:
            {
                "code": 生成的代码,
                "template_type": 模板类型,
                "requirement": 原始需求,
                "variables": 填充的变量,
            }
        """
        if template_type not in self._templates:
            return None

        template = self._templates[template_type]

        # 提取模板中的待填充变量（{{variable}}格式）
        variables = re.findall(r'\{\{(\w+)\}\}', template)

        if not variables:
            # 无变量模板，直接使用
            return {
                "code": template,
                "template_type": template_type,
                "requirement": requirement,
                "variables": {},
            }

        # 用LLM生成填充内容
        if llm_caller is None:
            if self.core and hasattr(self.core, 'llm'):
                llm_caller = self.core.llm.chat
            else:
                return None

        fill_prompt = self._build_fill_prompt(template_type, requirement, variables)
        filled_content = llm_caller(fill_prompt)

        # 解析LLM输出为变量映射
        var_values = self._parse_fill_response(filled_content, variables)

        # 填充模板
        filled_code = template
        for var_name, var_value in var_values.items():
            filled_code = filled_code.replace(f"{{{{{var_name}}}}}", var_value)

        return {
            "code": filled_code,
            "template_type": template_type,
            "requirement": requirement,
            "variables": var_values,
        }

    def validate(self, code: str) -> Tuple[bool, List[str]]:
        """
        验证生成的代码
        返回 (是否通过, 错误列表)
        """
        errors = []

        # 1. 语法检查
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"语法错误: {e}")
            return False, errors

        # 2. 安全检查 — 危险模式
        danger_patterns = [
            (r'os\.system\s*\(', "禁止使用os.system"),
            (r'subprocess\.', "禁止使用subprocess"),
            (r'__import__\s*\(', "禁止使用__import__"),
            (r'eval\s*\(', "禁止使用eval"),
            (r'exec\s*\(', "禁止使用exec"),
            (r'open\s*\([^)]*[wW]', "检查文件写入操作"),
        ]

        for pattern, reason in danger_patterns:
            if re.search(pattern, code):
                errors.append(f"安全检查: {reason}")

        # 3. 未填充变量检查
        unfilled = re.findall(r'\{\{(\w+)\}\}', code)
        if unfilled:
            errors.append(f"未填充变量: {unfilled}")

        # 4. 必须继承PluginBase
        if "PluginBase" not in code and "class Plugin" not in code:
            errors.append("必须继承PluginBase或定义Plugin类")

        return len(errors) == 0, errors

    def install(self, code: str, plugin_name: str,
                template_type: str = None) -> Tuple[bool, str]:
        """
        安装插件到plugins/目录并注册manifest

        Returns:
            (是否成功, 消息)
        """
        # 确保目录存在
        os.makedirs(self.plugins_dir, exist_ok=True)

        # 写入插件文件
        file_path = os.path.join(self.plugins_dir, f"{plugin_name}.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 注册到manifest.json
        manifest_path = os.path.join(self.plugins_dir, "manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            manifest = {"plugins": []}

        # 检查是否已存在
        existing = [p for p in manifest.get("plugins", [])
                    if p.get("module") == plugin_name]
        if existing:
            # 更新已有条目
            existing[0]["enabled"] = True
            existing[0]["updated"] = time.strftime("%Y-%m-%d %H:%M")
        else:
            manifest.setdefault("plugins", []).append({
                "module": plugin_name,
                "class": "Plugin",
                "enabled": True,
                "name": plugin_name,
                "added": time.strftime("%Y-%m-%d %H:%M"),
                "source": f"template:{template_type}" if template_type else "manual",
            })

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 记录历史
        self._history.append({
            "name": plugin_name,
            "template": template_type,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "file": file_path,
        })
        self._save_history()

        return True, f"插件 {plugin_name} 已安装到 {file_path}"

    def run_pipeline(self, requirement: str, plugin_name: str = None,
                     llm_caller=None) -> dict:
        """
        完整流水线：选择模板→填充→验证→安装

        Returns:
            {
                "success": bool,
                "plugin_name": str,
                "template_type": str,
                "errors": list,
                "message": str,
            }
        """
        result = {
            "success": False,
            "plugin_name": plugin_name or f"auto_{int(time.time())}",
            "template_type": None,
            "errors": [],
            "message": "",
        }

        # 1. 选择模板
        template_type = self.select_template(requirement)
        if not template_type:
            result["errors"] = ["无匹配模板"]
            result["message"] = "无法匹配合适的模板类型"
            return result

        result["template_type"] = template_type

        # 2. 填充模板
        filled = self.fill_template(template_type, requirement, llm_caller)
        if not filled:
            result["errors"] = ["模板填充失败"]
            result["message"] = f"模板 {template_type} 填充失败"
            return result

        # 3. 验证
        ok, errors = self.validate(filled["code"])
        if not ok:
            result["errors"] = errors
            result["message"] = f"验证失败: {'; '.join(errors)}"
            return result

        # 4. 安装
        ok, msg = self.install(filled["code"], result["plugin_name"], template_type)
        if not ok:
            result["errors"] = [msg]
            result["message"] = msg
            return result

        result["success"] = True
        result["message"] = msg
        return result

    # ─── 辅助方法 ──────────────────────────────

    def _build_fill_prompt(self, template_type: str, requirement: str,
                           variables: list) -> str:
        """构建LLM填充提示"""
        var_desc = {
            "PLUGIN_NAME": "插件的英文名（下划线命名，如 weather_query）",
            "PLUGIN_DESC": "插件描述（中文一句话）",
            "TRIGGER_PATTERN": "触发正则表达式",
            "REPLY_TEMPLATE": "回复模板（可含{变量}占位符）",
            "API_URL": "API请求URL",
            "PARAM_MAP": "参数映射JSON",
            "RESULT_FORMAT": "结果格式化模板",
            "INJECT_CONTENT": "注入内容",
            "INJECT_CONDITION": "注入触发条件",
        }

        var_list = "\n".join(
            f"- {v}: {var_desc.get(v, '填充内容')}"
            for v in variables
        )

        return f"""你是知乐运行器的插件生成器。根据需求填充模板变量。

需求：{requirement}
模板类型：{template_type}
需要填充的变量：
{var_list}

请按以下格式输出，每个变量一行：
变量名=值

只输出变量，不要输出其他内容。代码相关变量用Python语法。"""

    def _parse_fill_response(self, response: str, variables: list) -> dict:
        """解析LLM填充响应为变量映射"""
        values = {}
        for line in response.strip().split("\n"):
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key in variables:
                    values[key] = val

        # 确保所有变量都有值
        for v in variables:
            if v not in values:
                values[v] = f'"{v}_default"'

        return values

    def _load_history(self):
        """加载创建历史"""
        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                self._history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._history = []

    def _save_history(self):
        """保存创建历史"""
        try:
            os.makedirs(self.plugins_dir, exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history[-100:], f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "enabled": self.enabled,
            "available_templates": list(self._templates.keys()),
            "total_created": len(self._history),
            "recent_creations": self._history[-5:] if self._history else [],
        }

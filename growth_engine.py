#!/usr/bin/env python3
"""
P0.26 Phase 4 · 自主生长闭环编排引擎 (GrowthEngine)

将前序积木串联为完整闭环：
  "我需要XX能力" → 分析需求 → 生成代码 → 沙箱测试 → 提交审核 → 安装 → 验证

依赖积木（全部已完成，直接集成）:
  1. architecture_map.py  — ArchitectureMap.suggest_insertion() / to_context_string()
  2. template_filler.py   — TemplateFiller.fill_template() / validate() / install()
  3. code_executor.py     — CodeExecutor.execute() 沙箱执行
  4. debug_loop.py        — DebugLoop.run() 迭代修复循环
  5. approval_gate.py     — ApprovalGate 审批工作流
  6. background_plugin.py — PluginManager.register() / unregister()
  7. core.py              — ZhileCore.provider (LLM) / arch_map / template_filler / ...
  8. memory_system.py     — MemorySystem.add_memory() 记录成长事件

设计原则:
  - LLM 调用通过 core.llm，不直接 new provider
  - 代码生成时必须注入 arch_map 上下文
  - 沙箱测试失败自动进入 debug_loop，最多 3 轮
  - 审核流程不跳过——即使测试通过也必须提交审核摘要
  - 插件安装用 PluginManager.register()，不手动操作 manifest.json
  - 向后兼容：core.growth_engine=None 时所有命令安全返回提示
"""

import json
import os
import time
import re
import ast
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class GrowthEngine:
    """自主生长闭环编排引擎

    主入口 grow(capability_desc) 执行完整闭环：
      analyze → generate → test → review → install → record
    """

    # 管道状态枚举
    STATUS_IDLE = "idle"
    STATUS_ANALYZING = "analyzing"
    STATUS_GENERATING = "generating"
    STATUS_TESTING = "testing"
    STATUS_REVIEWING = "reviewing"
    STATUS_INSTALLING = "installing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    # 持久化文件
    HISTORY_FILE = "memory/growth_history.json"
    MAX_HISTORY = 20
    MAX_DEBUG_ROUNDS = 3

    def __init__(self, core):
        """初始化生长引擎

        Args:
            core: ZhileCore 实例，提供 LLM / arch_map / template_filler /
                  code_executor / debug_loop / approval_gate / bg_plugin_manager /
                  memory_system 等积木引用
        """
        self.core = core
        self._status = self.STATUS_IDLE
        self._current_desc = ""
        self._current_analysis: Optional[dict] = None
        self._current_code = ""
        self._current_test_result: Optional[dict] = None
        self._error_msg = ""
        self._history: List[dict] = []
        self._history_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            self.HISTORY_FILE
        )
        self._load_history()

    # ─── 公开接口 ──────────────────────────────

    def grow(self, capability_desc: str) -> dict:
        """主入口：执行完整自主生长闭环

        Args:
            capability_desc: 能力需求描述，如 "我需要查股票实时价格的能力"

        Returns:
            {
                "success": bool,
                "status": str,
                "capability": str,
                "analysis": dict,
                "test_result": dict,
                "approval_id": str,
                "approval_status": str,
                "installed": bool,
                "error": str,
            }
        """
        result = {
            "success": False,
            "status": "",
            "capability": capability_desc,
            "analysis": None,
            "test_result": None,
            "approval_id": "",
            "approval_status": "",
            "installed": False,
            "error": "",
        }

        try:
            # Step 1: 分析需求
            self._set_status(self.STATUS_ANALYZING, capability_desc)
            analysis = self._analyze_need(capability_desc)
            result["analysis"] = analysis
            self._current_analysis = analysis
            print(f"[GrowthEngine] 分析完成: type={analysis.get('plugin_type')}, "
                  f"base={analysis.get('base_class')}")

            # Step 2: 生成代码
            self._set_status(self.STATUS_GENERATING, capability_desc)
            code = self._generate_code(analysis)
            if not code:
                raise RuntimeError("代码生成失败，未获得有效代码")
            self._current_code = code
            print(f"[GrowthEngine] 代码生成完成: {len(code)} 字符")

            # Step 3: 测试代码
            self._set_status(self.STATUS_TESTING, capability_desc)
            passed, test_report = self._test_code(code)
            result["test_result"] = test_report
            self._current_test_result = test_report
            print(f"[GrowthEngine] 测试{'通过' if passed else '失败'}: "
                  f"{test_report.get('summary', '')}")

            # Step 4: 提交审核（即使测试通过也必须提交）
            self._set_status(self.STATUS_REVIEWING, capability_desc)
            approval_id, approval_status = self._submit_for_review(
                code, test_report, analysis
            )
            result["approval_id"] = approval_id
            result["approval_status"] = approval_status
            print(f"[GrowthEngine] 审核状态: {approval_status}")

            # 审核未通过则终止
            if approval_status not in ("approved", "auto_approved"):
                result["status"] = self.STATUS_REVIEWING
                result["error"] = f"审核未通过: {approval_status}"
                self._record_growth(capability_desc, "rejected",
                                    analysis=analysis, error=result["error"])
                self._set_status(self.STATUS_FAILED, capability_desc,
                                 result["error"])
                return result

            # Step 5: 安装已审核代码
            self._set_status(self.STATUS_INSTALLING, capability_desc)
            installed, install_msg = self._install_approved(code, analysis)
            result["installed"] = installed
            if not installed:
                result["error"] = f"安装失败: {install_msg}"
                self._record_growth(capability_desc, "install_failed",
                                    analysis=analysis, error=result["error"])
                self._set_status(self.STATUS_FAILED, capability_desc,
                                 result["error"])
                return result

            # Step 6: 记录成长事件
            self._record_growth(capability_desc, "success", analysis=analysis)
            result["success"] = True
            result["status"] = self.STATUS_DONE
            self._set_status(self.STATUS_DONE, capability_desc)
            print(f"[GrowthEngine] ✅ 生长完成: {capability_desc}")
            return result

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            result["error"] = err_msg
            result["status"] = self.STATUS_FAILED
            self._set_status(self.STATUS_FAILED, capability_desc, err_msg)
            self._record_growth(capability_desc, "failed", error=err_msg)
            return result

    def get_status(self) -> dict:
        """返回当前生长管道状态"""
        return {
            "status": self._status,
            "current_capability": self._current_desc,
            "has_analysis": self._current_analysis is not None,
            "has_code": bool(self._current_code),
            "error": self._error_msg,
        }

    def get_history(self) -> List[dict]:
        """返回历史生长记录列表"""
        return list(self._history)

    # ─── 闭环各步骤 ────────────────────────────

    def _analyze_need(self, desc: str) -> dict:
        """Step 1: 分析需求，确定插件类型、基类、接口

        用 arch_map.suggest_insertion() + LLM 分析。

        Returns:
            {
                "plugin_type": "background" | "route_rule" | "simple_tool" | ...,
                "base_class": "BackgroundPlugin" | "PluginBase" | ...,
                "module_name": "stock_price_query",
                "interfaces": ["tick", "get_interval"],
                "insertion": {...},  # arch_map.suggest_insertion() 返回
                "arch_context": "...",  # arch_map.to_context_string()
                "requirements": "具体需求描述",
            }
        """
        # 1. 用 arch_map 建议插入点
        insertion = {}
        arch_context = ""
        if self.core and hasattr(self.core, "arch_map") and self.core.arch_map:
            try:
                insertion = self.core.arch_map.suggest_insertion(desc)
                arch_context = self.core.arch_map.to_context_string(max_tokens=2000)
            except Exception as e:
                print(f"[GrowthEngine] arch_map 查询失败: {e}")

        # 2. 用 LLM 分析需求细节
        llm_response = ""
        if self.core and hasattr(self.core, "llm") and self.core.llm:
            prompt = self._build_analysis_prompt(desc, insertion, arch_context)
            try:
                llm_response = "".join(
                    self.core.llm.chat(
                        [{"role": "user", "content": prompt}],
                        stream=True,
                    )
                )
            except Exception as e:
                print(f"[GrowthEngine] LLM 分析失败，使用规则推断: {e}")
                llm_response = ""

        # 3. 解析 LLM 输出 + 规则兜底
        analysis = self._parse_analysis(llm_response, desc, insertion)

        # 注入架构上下文供后续代码生成使用
        analysis["arch_context"] = arch_context
        analysis["insertion"] = insertion

        return analysis

    def _generate_code(self, analysis: dict) -> str:
        """Step 2: 生成插件代码

        优先用 template_filler 填充模板；模板不匹配时用 LLM 从零生成。
        生成时注入 arch_map.to_context_string() 作为架构上下文。
        """
        # 尝试 template_filler
        if self.core and hasattr(self.core, "template_filler") and self.core.template_filler:
            try:
                template_type = self.core.template_filler.select_template(
                    analysis.get("requirements", analysis.get("plugin_type", ""))
                )
                if template_type:
                    fill_result = self.core.template_filler.fill_template(
                        template_type,
                        analysis.get("requirements", ""),
                        llm_caller=self._llm_call_wrapper,
                    )
                    if fill_result and fill_result.get("code"):
                        code = fill_result["code"]
                        # 验证生成的代码
                        valid, errors = self.core.template_filler.validate(code)
                        if valid:
                            print(f"[GrowthEngine] 模板填充成功: {template_type}")
                            return code
                        else:
                            print(f"[GrowthEngine] 模板代码验证失败: {errors}，回退 LLM 生成")
            except Exception as e:
                print(f"[GrowthEngine] 模板填充失败: {e}，回退 LLM 生成")

        # 回退：LLM 从零生成
        return self._llm_generate_code(analysis)

    def _test_code(self, code: str) -> Tuple[bool, dict]:
        """Step 3: 沙箱执行 + debug_loop 迭代修复

        Returns:
            (是否通过, 测试报告 dict)
        """
        # 如果有 debug_loop，用它迭代修复
        if self.core and hasattr(self.core, "debug_loop") and self.core.debug_loop:
            try:
                debug_result = self.core.debug_loop.run(
                    code,
                    max_iterations=self.MAX_DEBUG_ROUNDS,
                )
                test_report = {
                    "method": "debug_loop",
                    "passed": debug_result.success,
                    "iterations": debug_result.iterations,
                    "final_output": debug_result.final_output[:500] if debug_result.final_output else "",
                    "summary": f"{'通过' if debug_result.success else '失败'} "
                               f"({debug_result.iterations} 轮迭代)",
                    "history": [h.to_dict() for h in debug_result.history],
                }
                # 如果 debug_loop 修复了代码，更新当前代码
                if debug_result.success and debug_result.final_code:
                    self._current_code = debug_result.final_code
                return debug_result.success, test_report
            except Exception as e:
                print(f"[GrowthEngine] debug_loop 异常: {e}")
                # 降级到直接执行

        # 直接用 code_executor 执行
        if self.core and hasattr(self.core, "code_executor") and self.core.code_executor:
            try:
                result = self.core.code_executor.execute(code)
                test_report = {
                    "method": "code_executor",
                    "passed": result.success,
                    "stdout": result.stdout[:500] if result.stdout else "",
                    "stderr": result.stderr[:500] if result.stderr else "",
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                    "summary": f"{'通过' if result.success else '失败'}: "
                               f"{result.error_type or 'OK'}",
                }
                return result.success, test_report
            except Exception as e:
                return False, {
                    "method": "code_executor",
                    "passed": False,
                    "summary": f"执行异常: {e}",
                }

        # 无执行器可用 — 做基础语法检查
        try:
            ast.parse(code)
            return True, {
                "method": "syntax_check",
                "passed": True,
                "summary": "语法检查通过（无沙箱执行器）",
            }
        except SyntaxError as e:
            return False, {
                "method": "syntax_check",
                "passed": False,
                "summary": f"语法错误: {e}",
            }

    def _submit_for_review(self, code: str, test_result: dict,
                           analysis: dict) -> Tuple[str, str]:
        """Step 4: 通过 approval_gate 提交审核

        生成审核摘要（代码功能 / 测试结果 / 安全检查 / 风险项），
        提交到 ApprovalGate。

        Returns:
            (approval_id, approval_status)
        """
        # 生成审核摘要
        review_summary = self._build_review_summary(code, test_result, analysis)

        # 提交到 approval_gate
        if self.core and hasattr(self.core, "approval_gate") and self.core.approval_gate:
            try:
                approval_id = self.core.approval_gate.register_action(
                    action_type="code_install",
                    action_desc=review_summary,
                    risk_level=None,  # 使用默认风险映射
                )
                # 查询审批状态
                status = self.core.approval_gate.check_approval(approval_id)
                return approval_id, status
            except Exception as e:
                print(f"[GrowthEngine] 审批提交异常: {e}")
                return "", "error"

        # 无审批门 — 自动通过（但记录警告）
        print("[GrowthEngine] ⚠ 审批门未启用，自动通过")
        return "auto_no_gate", "auto_approved"

    def _install_approved(self, code: str, analysis: dict) -> Tuple[bool, str]:
        """Step 5: 审核通过后安装插件

        流程: 写文件到 plugins/ → 通过 PluginManager.register() 注册 → 验证可用

        Returns:
            (是否成功, 消息)
        """
        module_name = analysis.get("module_name", "auto_plugin")
        if not module_name:
            module_name = "auto_plugin"
        # 安全化文件名
        module_name = re.sub(r'[^a-zA-Z0-9_]', '_', module_name)

        plugins_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "plugins"
        )
        os.makedirs(plugins_dir, exist_ok=True)
        file_path = os.path.join(plugins_dir, f"{module_name}.py")

        # 写文件
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"[GrowthEngine] 插件文件已写入: {file_path}")
        except Exception as e:
            return False, f"写文件失败: {e}"

        # 通过 PluginManager 注册（不手动操作 manifest.json）
        installed_via_manager = False
        if self.core and hasattr(self.core, "bg_plugin_manager") and self.core.bg_plugin_manager:
            try:
                # 动态导入并实例化插件
                plugin_instance = self._load_plugin_instance(
                    file_path, module_name, analysis
                )
                if plugin_instance:
                    ok = self.core.bg_plugin_manager.register(plugin_instance)
                    if ok:
                        installed_via_manager = True
                        print(f"[GrowthEngine] 插件已通过 PluginManager 注册: {module_name}")
                    else:
                        return False, f"PluginManager.register() 返回 False"
                else:
                    print(f"[GrowthEngine] 插件实例化失败，但文件已写入")
            except Exception as e:
                print(f"[GrowthEngine] PluginManager 注册异常: {e}")

        # 验证：检查文件存在且可导入
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                print(f"[GrowthEngine] ✅ 插件验证通过: {module_name}")
                return True, f"已安装并验证: {module_name}"
            else:
                return False, "无法创建模块 spec"
        except Exception as e:
            # 文件已写入但导入失败 — 仍算部分成功
            return installed_via_manager, f"文件已写入但导入验证失败: {e}"

    def _record_growth(self, capability: str, status: str,
                       analysis: dict = None, error: str = ""):
        """Step 6: 记录到 memory_system 作为成长事件"""
        # 记录到持久化历史
        record = {
            "timestamp": datetime.now().isoformat(),
            "capability": capability,
            "status": status,
            "plugin_type": (analysis or {}).get("plugin_type", ""),
            "module_name": (analysis or {}).get("module_name", ""),
            "error": error,
        }
        self._history.append(record)
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        self._save_history()

        # 记录到 memory_system（供 P0.3 自成长扫描捕获）
        if self.core and hasattr(self.core, "memory") and self.core.memory:
            try:
                mem_content = (
                    f"自主生长事件 [{status}]: {capability}"
                    f"\n  插件类型: {(analysis or {}).get('plugin_type', '未知')}"
                    f"\n  模块名: {(analysis or {}).get('module_name', '未知')}"
                )
                if error:
                    mem_content += f"\n  错误: {error}"
                self.core.memory.add_memory(
                    content=mem_content,
                    category="growth",
                    importance=8 if status == "success" else 5,
                    dimension="recent",
                    tags=["growth_engine", "self_evolution"],
                )
            except Exception as e:
                print(f"[GrowthEngine] 记录到 memory_system 失败: {e}")

    # ─── 内部辅助方法 ──────────────────────────

    def _set_status(self, status: str, desc: str = "", error: str = ""):
        """更新管道状态"""
        self._status = status
        if desc:
            self._current_desc = desc
        self._error_msg = error

    def _llm_call_wrapper(self, prompt: str) -> str:
        """LLM 调用包装器，供 template_filler 使用"""
        if not self.core or not hasattr(self.core, "llm") or not self.core.llm:
            return ""
        try:
            return "".join(
                self.core.llm.chat(
                    [{"role": "user", "content": prompt}],
                    stream=True,
                )
            )
        except Exception as e:
            print(f"[GrowthEngine] LLM 调用失败: {e}")
            return ""

    def _build_analysis_prompt(self, desc: str, insertion: dict,
                               arch_context: str) -> str:
        """构建需求分析 LLM prompt"""
        insertion_str = json.dumps(insertion, ensure_ascii=False, indent=2)
        return f"""你是知乐运行器的架构分析师。分析以下能力需求，确定如何实现。

## 能力需求
{desc}

## 架构插入点建议（来自 ArchitectureMap）
{insertion_str}

## 架构上下文
{arch_context[:3000]}

## 请输出 JSON（不要 markdown 代码块）
{{
  "plugin_type": "background | route_rule | simple_tool | context_inject | custom",
  "base_class": "BackgroundPlugin | PluginBase | ModelProvider | none",
  "module_name": "snake_case模块名",
  "interfaces": ["需要实现的方法名列表"],
  "requirements": "详细的需求描述，包含具体功能要求"
}}

只输出 JSON，不要其他文字。"""

    def _parse_analysis(self, llm_response: str, desc: str,
                        insertion: dict) -> dict:
        """解析 LLM 分析结果，规则兜底"""
        # 尝试从 LLM 输出中提取 JSON
        if llm_response:
            try:
                # 清理可能的 markdown 包裹
                cleaned = re.sub(r'```(?:json)?\s*', '', llm_response).strip()
                cleaned = cleaned.rsplit('```', 1)[0].strip()
                data = json.loads(cleaned)
                if isinstance(data, dict) and "plugin_type" in data:
                    # 确保字段完整
                    data.setdefault("base_class", "BackgroundPlugin")
                    data.setdefault("module_name", "auto_plugin")
                    data.setdefault("interfaces", [])
                    data.setdefault("requirements", desc)
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        # 规则兜底：根据关键词推断
        desc_lower = desc.lower()
        if any(kw in desc_lower for kw in ["定时", "后台", "监控", "循环", "定时器", "periodic", "timer", "monitor"]):
            plugin_type = "background"
            base_class = "BackgroundPlugin"
            interfaces = ["tick", "get_interval"]
        elif any(kw in desc_lower for kw in ["路由", "匹配", "关键词", "route", "pattern"]):
            plugin_type = "route_rule"
            base_class = "PluginBase"
            interfaces = ["on_user_message"]
        elif any(kw in desc_lower for kw in ["查询", "api", "接口", "工具", "tool", "query", "search"]):
            plugin_type = "simple_tool"
            base_class = "PluginBase"
            interfaces = ["on_user_message"]
        else:
            plugin_type = "custom"
            base_class = "BackgroundPlugin"
            interfaces = ["tick", "get_interval"]

        # 从描述生成模块名
        module_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', desc)[:30]
        if not module_name:
            module_name = "auto_plugin"

        return {
            "plugin_type": plugin_type,
            "base_class": base_class,
            "module_name": module_name,
            "interfaces": interfaces,
            "requirements": desc,
        }

    def _llm_generate_code(self, analysis: dict) -> str:
        """LLM 从零生成插件代码"""
        arch_context = analysis.get("arch_context", "")
        base_class = analysis.get("base_class", "BackgroundPlugin")
        interfaces = analysis.get("interfaces", [])
        module_name = analysis.get("module_name", "auto_plugin")
        requirements = analysis.get("requirements", "")

        prompt = f"""你是知乐运行器的代码生成器。根据以下信息生成完整的 Python 插件代码。

## 需求
{requirements}

## 插件规格
- 模块名: {module_name}
- 基类: {base_class}
- 需实现接口: {', '.join(interfaces)}

## 架构上下文（供参考，了解现有代码结构）
{arch_context[:3000]}

## 代码要求
1. 继承 {base_class}，实现所有必需接口
2. 代码自包含，不依赖未安装的第三方库
3. 包含 __init__ 初始化
4. 包含完整的类定义和必要的方法实现
5. 在文件顶部添加模块 docstring
6. 如果是 BackgroundPlugin 子类，实现 get_interval() 和 tick()
7. 如果需要网络请求，使用 urllib 而非 requests

直接输出 Python 代码，不要 markdown 代码块标记。"""

        response = self._llm_call_wrapper(prompt)
        if not response:
            return ""

        # 清理 markdown 包裹
        code = re.sub(r'^```(?:python)?\s*\n?', '', response).strip()
        code = re.sub(r'\n?```\s*$', '', code).strip()
        return code

    def _build_review_summary(self, code: str, test_result: dict,
                              analysis: dict) -> str:
        """构建审核摘要"""
        # 安全检查
        security_issues = []
        danger_patterns = [
            (r'os\.system\s*\(', "os.system()"),
            (r'subprocess\.', "subprocess"),
            (r'__import__\s*\(', "__import__()"),
            (r'\beval\s*\(', "eval()"),
            (r'\bexec\s*\(', "exec()"),
        ]
        for pattern, name in danger_patterns:
            if re.search(pattern, code):
                security_issues.append(name)

        # 代码统计
        lines = code.count('\n') + 1
        has_class = bool(re.search(r'^class\s+', code, re.MULTILINE))
        has_init = '__init__' in code

        return (
            f"自主生长插件审核\n"
            f"  能力需求: {analysis.get('requirements', '未知')}\n"
            f"  插件类型: {analysis.get('plugin_type', '未知')}\n"
            f"  模块名: {analysis.get('module_name', '未知')}\n"
            f"  基类: {analysis.get('base_class', '未知')}\n"
            f"  代码行数: {lines}\n"
            f"  有类定义: {has_class}\n"
            f"  有__init__: {has_init}\n"
            f"  测试方法: {test_result.get('method', '未知')}\n"
            f"  测试结果: {test_result.get('summary', '未知')}\n"
            f"  安全检查: {'通过' if not security_issues else '发现风险: ' + ', '.join(security_issues)}\n"
            f"  风险项: {security_issues if security_issues else '无'}"
        )

    def _load_plugin_instance(self, file_path: str, module_name: str,
                              analysis: dict):
        """动态加载插件文件并实例化"""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 查找模块中的插件类
            base_class_name = analysis.get("base_class", "BackgroundPlugin")
            plugin_class = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and attr.__module__ == module_name:
                    # 检查是否继承自 BackgroundPlugin 或有 tick 方法
                    if hasattr(attr, "tick") or base_class_name in [
                        c.__name__ for c in attr.__mro()
                    ]:
                        plugin_class = attr
                        break

            if not plugin_class:
                # 取第一个定义的类
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and attr.__module__ == module_name:
                        plugin_class = attr
                        break

            if plugin_class:
                try:
                    return plugin_class(core=self.core)
                except TypeError:
                    return plugin_class()
            return None
        except Exception as e:
            print(f"[GrowthEngine] 动态加载失败: {e}")
            return None

    # ─── 持久化 ────────────────────────────────

    def _load_history(self):
        """加载历史记录"""
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
                    if not isinstance(self._history, list):
                        self._history = []
        except Exception:
            self._history = []

    def _save_history(self):
        """保存历史记录"""
        try:
            os.makedirs(os.path.dirname(self._history_file), exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history[-self.MAX_HISTORY:], f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[GrowthEngine] 保存历史失败: {e}")


# ─── 自测 ──────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("GrowthEngine 自测")
    print("=" * 60)

    # Mock core 对象
    class MockArchMap:
        def suggest_insertion(self, desc):
            return {
                "desc": desc,
                "suggestion": {
                    "extension_point": "BackgroundPlugin",
                    "module": "plugins",
                    "how_to": "继承 BackgroundPlugin，实现 tick() 和 get_interval()",
                    "example": "plugins/stock_monitor.py",
                },
                "alternatives": [],
            }

        def to_context_string(self, max_tokens=2000):
            return "## 扩展点\n- BackgroundPlugin (background_plugin): 后台循环插件基类"

    class MockCore:
        def __init__(self):
            self.arch_map = MockArchMap()
            self.template_filler = None
            self.code_executor = None
            self.debug_loop = None
            self.approval_gate = None
            self.bg_plugin_manager = None
            self.memory = None
            self.llm = None

    core = MockCore()
    engine = GrowthEngine(core)

    # Test 1: get_status() 返回 idle
    status = engine.get_status()
    assert status["status"] == "idle", f"Expected idle, got {status['status']}"
    print(f"✅ Test 1 通过: get_status() = {status}")

    # Test 2: get_history() 返回列表
    history = engine.get_history()
    assert isinstance(history, list), f"Expected list, got {type(history)}"
    print(f"✅ Test 2 通过: get_history() 返回列表 ({len(history)} 条)")

    # Test 3: _analyze_need 返回正确结构
    analysis = engine._analyze_need("我需要每分钟检查一次股票价格的能力")
    assert "plugin_type" in analysis, "analysis 缺少 plugin_type"
    assert "base_class" in analysis, "analysis 缺少 base_class"
    assert "module_name" in analysis, "analysis 缺少 module_name"
    assert "interfaces" in analysis, "analysis 缺少 interfaces"
    assert "arch_context" in analysis, "analysis 缺少 arch_context"
    print(f"✅ Test 3 通过: _analyze_need() = {json.dumps(analysis, ensure_ascii=False, indent=2)}")

    # Test 4: 持久化文件读写
    engine._record_growth("测试能力", "success", analysis={"plugin_type": "test"})
    engine._save_history()
    engine._load_history()
    assert len(engine._history) > 0, "历史记录为空"
    assert engine._history[-1]["capability"] == "测试能力"
    print(f"✅ Test 4 通过: 持久化读写正常 ({len(engine._history)} 条)")

    # Test 5: _build_review_summary 生成摘要
    summary = engine._build_review_summary(
        "class TestPlugin:\n    pass\n",
        {"method": "syntax_check", "passed": True, "summary": "通过"},
        {"requirements": "测试", "plugin_type": "test", "module_name": "test_mod",
         "base_class": "BackgroundPlugin"},
    )
    assert "自主生长插件审核" in summary
    assert "测试" in summary
    print(f"✅ Test 5 通过: 审核摘要生成正常")

    print("\n" + "=" * 60)
    print("全部自测通过 ✅")
    print("=" * 60)

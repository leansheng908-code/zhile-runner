#!/usr/bin/env python3
"""
知乐运行器 · 健康检查脚本
用法：python3 healthcheck.py
作用：验证所有文件完整性、关键功能可用，pull后跑一下心里有底
"""

import os
import sys
import json
import importlib
import platform as _platform

# ─── 配置 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IS_WINDOWS = _platform.system() == "Windows"

# 期望的文件清单（文件名: 最小字节数）
EXPECTED_FILES = {
    # 核心文件
    "main.py": 2000,
    "core.py": 15000,
    "dna_loader.py": 2500,
    "llm_provider.py": 3000,
    "context_assembler.py": 4000,
    "config.json": 1000,
    "requirements.txt": 20,
    "README.md": 2000,
    # 平台兼容层
    "platform_compat.py": 1500,
    # 记忆与情感
    "memory_system.py": 12000,
    "psi_engine.py": 8000,
    "growth_scanner.py": 4000,
    # P0.8 实体图
    "entity_graph.py": 12000,
    # P0.15 弧光
    "arc_light.py": 6000,
    # P0.16 活体约束层
    "feedback_loop.py": 12000,
    # P0.17 体细胞
    "somatic_cells.py": 10000,
    # P0.18 事件轨迹
    "event_trajectory.py": 15000,
    # P0.9 观察者
    "observer.py": 8000,
    # P0.5 快照与安全
    "snapshot.py": 8000,
    # CLI
    "cli.py": 20000,
    # WebUI
    "webui/__init__.py": 10,
    "webui/web.py": 5000,
    "webui/web_template.py": 10000,
    "webui/qq.py": 8000,
    # P0.6 回执审计
    "audit_logger.py": 2000,
    # P0.7 插件路由器
    "plugin_router.py": 2000,
    # P0.10 群聊管理
    "group_manager.py": 2000,
    # P0.13 主动话题
    "topic_manager.py": 2000,
    # P0.19 技能自学习
    "skill_evaluator.py": 1000,
    "skill_learner.py": 2000,
    # P0.23 认知路由层
    "cognitive_router.py": 5000,
    # P0.26 自主编程
    "template_filler.py": 2000,
    "code_executor.py": 3000,
    "debug_loop.py": 2000,
    # P0.27 代码发布
    "code_publisher.py": 2000,
    # P0.28 遗忘测试
    "forget_test_scheduler.py": 2000,
    # P0.29 记忆编译
    "memory_compiler.py": 2000,
    # P0.1 DNA v5.0 边界
    "boundary.py": 1500,
    # P0.4 插件系统
    "plugin_base.py": 1000,
    "plugin_manager.py": 2000,
    "self_roadmap.py": 2000,
    # P0.11 长在线思考
    "daemon_thinker.py": 5000,
    "reflection_engine.py": 3000,
    # 插件生命周期管理
    "plugin_installer.py": 8000,
}

# 期望的类/函数（模块名: [类名或函数名列表]）
EXPECTED_SYMBOLS = {
    "main": ["main"],
    "core": ["ZhileCore"],
    "dna_loader": ["DNALoader"],
    "llm_provider": ["LLMProvider"],
    "context_assembler": ["ContextAssembler"],
    "memory_system": ["MemorySystem"],
    "psi_engine": ["PSIEngine"],
    "growth_scanner": ["GrowthScanner"],
    "entity_graph": ["EntityGraph"],
    "arc_light": ["ArcLightSystem"],
    "feedback_loop": ["FeedbackLoop"],
    "somatic_cells": ["SomaticCellSystem"],
    "event_trajectory": ["EventTrajectory"],
    "observer": ["Observer", "RunFrame"],
    "snapshot": ["SnapshotManager", "Snapshot"],
    "cli": ["CLI"],
    "platform_compat": ["IS_WINDOWS", "IS_UNIX", "get_sandbox_env"],
    "audit_logger": ["AuditLogger"],
    "plugin_router": ["PluginRouter"],
    "group_manager": ["GroupManager"],
    "topic_manager": ["TopicManager"],
    "skill_evaluator": ["SkillEvaluator"],
    "skill_learner": ["SkillLearner"],
    "cognitive_router": ["CognitiveRouter"],
    "template_filler": ["TemplateFiller"],
    "code_executor": ["CodeExecutor"],
    "debug_loop": ["DebugLoop"],
    "code_publisher": ["CodePublisher"],
    "forget_test_scheduler": ["ForgetTestScheduler"],
    "memory_compiler": ["MemoryCompiler"],
    "boundary": ["BoundaryGuard"],
    "plugin_base": ["PluginBase"],
    "plugin_manager": ["PluginManager"],
    "self_roadmap": ["SelfRoadmap"],
    "daemon_thinker": ["DaemonThinker"],
    "reflection_engine": ["ReflectionEngine"],
    "webui.web": ["create_app"],
    "webui.qq": ["QQAdapter"],
    # P0.46/P0.56 新增模块
    "background_plugin": ["BackgroundPlugin", "PluginManager"],
    "background_manager": ["BackgroundTaskManager"],
    "context_compressor": ["ContextCompressor"],
    "skill_evolution": ["SkillEvolution"],
    "model_provider": ["ModelProvider", "ProviderFactory", "LLMProviderAdapter"],
    "nl_scheduler": ["NaturalLanguageScheduler", "CronParser"],
    "plugin_installer": ["PluginInstaller"],
    "post_write_lint": ["PostWriteLinter"],
    "session_checkpoint": ["SessionCheckpoint"],
    "free_will": ["FreeWillFoundation"],
    "care_hooks": ["CareHookManager"],
    "web_searcher": ["WebSearcher"],
    "fleeting_moment": ["FleetingMoment"],
    "resonance_engine": ["ResonanceEngine"],
    "ammo_classifier": ["AmmoClassifier"],
    "active_reconstruction": ["ActiveReconstructor"],
    "forget_test_scheduler": ["ForgetTestScheduler"],
}

# ─── 检查结果统计 ───
class Result:
    def __init__(self):
        self.passed = 0
        self.warnings = 0
        self.failed = 0
        self.details = []

    def ok(self, msg):
        self.passed += 1
        self.details.append(("✅", msg))

    def warn(self, msg):
        self.warnings += 1
        self.details.append(("⚠️", msg))

    def fail(self, msg):
        self.failed += 1
        self.details.append(("❌", msg))

    def summary(self):
        total = self.passed + self.warnings + self.failed
        return f"\n{'='*50}\n检查完成：{total}项 | ✅ {self.passed}通过 | ⚠️ {self.warnings}警告 | ❌ {self.failed}失败\n{'='*50}"


def check_files(result):
    """检查文件是否存在且大小正常"""
    print("\n📁 检查文件完整性...")
    for filepath, min_size in EXPECTED_FILES.items():
        full_path = os.path.join(BASE_DIR, filepath)
        if not os.path.exists(full_path):
            result.fail(f"文件缺失：{filepath}")
            continue
        size = os.path.getsize(full_path)
        if size < min_size:
            result.warn(f"文件偏小：{filepath}（{size}B，预期≥{min_size}B）")
        elif size == 0:
            result.fail(f"文件为空：{filepath}")
        else:
            result.ok(f"{filepath}（{size}B）")


def check_imports(result):
    """检查关键模块能否正常import"""
    print("\n🔌 检查模块导入...")
    # 检查第三方依赖
    deps = {"requests": "requests", "flask": "flask", "websockets": "websockets"}
    for pkg, name in deps.items():
        try:
            importlib.import_module(pkg)
            result.ok(f"依赖可用：{name}")
        except ImportError:
            result.warn(f"依赖缺失：{name}（不影响其他模式，但此模式不可用）")

    # 检查运行器自身模块
    sys.path.insert(0, BASE_DIR)
    optional_modules = {"webui.web", "webui.qq"}  # 这些模块依赖可选包
    for module_name, symbols in EXPECTED_SYMBOLS.items():
        try:
            mod = importlib.import_module(module_name)
            for sym in symbols:
                if hasattr(mod, sym):
                    result.ok(f"模块正常：{module_name}.{sym}")
                else:
                    result.fail(f"符号缺失：{module_name}.{sym}（模块能导入但找不到这个类/函数）")
        except ImportError as e:
            if module_name in optional_modules:
                result.warn(f"可选模块跳过：{module_name}（{e}，不影响CLI模式）")
            else:
                result.fail(f"导入失败：{module_name}（{type(e).__name__}: {e}）")
        except Exception as e:
            result.fail(f"导入失败：{module_name}（{type(e).__name__}: {e}）")


def check_config(result):
    """检查config.json格式和关键字段"""
    print("\n⚙️ 检查配置文件...")
    config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        result.fail("config.json 不存在")
        return
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        result.fail(f"config.json 格式错误：{e}")
        return

    # 检查关键字段
    checks = [
        ("llm.api_key", config.get("llm", {}).get("api_key", "")),
        ("llm.model", config.get("llm", {}).get("model", "")),
        ("llm.base_url", config.get("llm", {}).get("base_url", "")),
        ("memory.dir", config.get("memory", {}).get("dir", "")),
    ]
    for name, value in checks:
        if value:
            # api_key 只显示前几位
            display = value[:8] + "..." if "key" in name.lower() else value
            result.ok(f"配置项：{name} = {display}")
        else:
            result.fail(f"配置项缺失：{name}")


def check_dna(result):
    """检查DNA文件是否存在"""
    print("\n🧬 检查DNA文件...")
    dna_path = os.path.join(BASE_DIR, "..")
    dna_files = ["system_prompt.md", "config/model_config.json"]
    optional_files = ["data/USER.md", "data/MEMORY.md", "data/SOUL.md"]

    for f in dna_files:
        full = os.path.join(dna_path, f)
        if os.path.exists(full):
            size = os.path.getsize(full)
            result.ok(f"DNA文件：{f}（{size}B）")
        else:
            result.warn(f"DNA文件缺失：{f}（检查dna_path配置，云端测试可忽略）")

    for f in optional_files:
        full = os.path.join(dna_path, f)
        if os.path.exists(full):
            result.ok(f"DNA数据文件：{f}")
        else:
            result.warn(f"DNA数据文件缺失：{f}（可选，不影响启动）")


def check_memory_dirs(result):
    """检查memory目录结构"""
    print("\n💾 检查记忆目录...")
    mem_dir = os.path.join(BASE_DIR, "memory")
    expected_dirs = ["", "entities", "psi", "growth"]
    for d in expected_dirs:
        path = os.path.join(mem_dir, d) if d else mem_dir
        if os.path.isdir(path):
            files = os.listdir(path)
            result.ok(f"目录存在：memory/{d or ''}（{len(files)}个文件）")
        else:
            result.warn(f"目录不存在：memory/{d}（首次启动会自动创建）")


def check_instantiation(result):
    """尝试实例化核心模块（不连接网络）"""
    print("\n🧪 检查模块实例化...")
    sys.path.insert(0, BASE_DIR)
    try:
        from dna_loader import DNALoader
        loader = DNALoader(os.path.join(BASE_DIR, ".."))
        sp = loader.load_system_prompt()
        if sp and len(sp) > 100:
            result.ok(f"DNA加载成功（system_prompt {len(sp)}字符）")
        else:
            result.warn("DNA加载返回但system_prompt为空（云端无DNA文件，Ubuntu上正常）")
    except Exception as e:
        result.warn(f"DNA加载失败：{type(e).__name__}: {e}（云端无DNA文件，Ubuntu上正常）")

    try:
        from psi_engine import PSIEngine
        psi = PSIEngine(state_dir=os.path.join(BASE_DIR, "memory", "psi"))
        result.ok("PSI引擎实例化成功")
    except Exception as e:
        result.fail(f"PSI引擎实例化失败：{type(e).__name__}: {e}")

    try:
        from somatic_cells import SomaticCellSystem
        scm = SomaticCellSystem(state_dir=os.path.join(BASE_DIR, "memory", "growth"))
        result.ok("体细胞系统实例化成功")
    except Exception as e:
        result.fail(f"体细胞系统实例化失败：{type(e).__name__}: {e}")

    try:
        from feedback_loop import FeedbackLoop
        fl = FeedbackLoop(state_dir=os.path.join(BASE_DIR, "memory", "growth"))
        result.ok("反馈闭环实例化成功")
    except Exception as e:
        result.fail(f"反馈闭环实例化失败：{type(e).__name__}: {e}")

    try:
        from entity_graph import EntityGraph
        eg = EntityGraph(graph_dir=os.path.join(BASE_DIR, "memory", "entities"))
        result.ok("实体图实例化成功")
    except Exception as e:
        result.fail(f"实体图实例化失败：{type(e).__name__}: {e}")

    try:
        from arc_light import ArcLightSystem
        al = ArcLightSystem(memory_dir=os.path.join(BASE_DIR, "memory"))
        result.ok("弧光系统实例化成功")
    except Exception as e:
        result.fail(f"弧光系统实例化失败：{type(e).__name__}: {e}")

    try:
        from event_trajectory import EventTrajectory
        et = EventTrajectory(memory_dir=os.path.join(BASE_DIR, "memory"))
        result.ok("事件轨迹分析器实例化成功")
    except Exception as e:
        result.fail(f"事件轨迹分析器实例化失败：{type(e).__name__}: {e}")

    # 观察者
    try:
        from observer import Observer
        obs = Observer(frames_dir=os.path.join(BASE_DIR, "memory", "frames"))
        result.ok("观察者实例化成功")
    except Exception as e:
        result.fail(f"观察者实例化失败：{type(e).__name__}: {e}")

    # P0.5 快照管理器
    try:
        from snapshot import SnapshotManager
        sm = SnapshotManager(
            memory_dir=os.path.join(BASE_DIR, "memory"),
            dna_path=os.path.join(BASE_DIR, ".."),
        )
        result.ok("快照管理器实例化成功")
    except Exception as e:
        result.fail(f"快照管理器实例化失败：{type(e).__name__}: {e}")

    # 平台兼容层
    try:
        import platform_compat
        info = platform_compat.platform_info()
        result.ok(f"平台兼容层：{info['platform']} / Python {info['python']} / 资源限制={info['supports_resource_limits']}")
    except Exception as e:
        result.fail(f"平台兼容层失败：{type(e).__name__}: {e}")

    # P0.26 代码执行沙箱
    try:
        from code_executor import CodeExecutor
        ce = CodeExecutor(config={"timeout": 5, "memory_limit_mb": 128, "max_output": 5000})
        result.ok("代码执行沙箱实例化成功")
    except Exception as e:
        result.fail(f"代码执行沙箱实例化失败：{type(e).__name__}: {e}")

    # P0.26 迭代调试循环
    try:
        from debug_loop import DebugLoop
        dl = DebugLoop(executor=None, llm_provider=None, config={"max_iterations": 3})
        result.ok("迭代调试循环实例化成功")
    except Exception as e:
        result.fail(f"迭代调试循环实例化失败：{type(e).__name__}: {e}")


def check_platform(result):
    """检查平台适配状态"""
    print("\n🖥️ 检查平台适配...")
    try:
        import platform_compat
        info = platform_compat.platform_info()
        result.ok(f"当前平台：{info['platform']}")
        result.ok(f"推荐模式：{', '.join(info['recommended_modes'])}")
        result.ok(f"资源限制：{'支持' if info['supports_resource_limits'] else '不支持（Windows跳过ulimit）'}")
    except Exception as e:
        result.fail(f"平台检查失败：{type(e).__name__}: {e}")


def main():
    print("=" * 50)
    print("🔍 知乐运行器 · 健康检查")
    print(f"   路径：{BASE_DIR}")
    print(f"   平台：{_platform.system()} {_platform.release()}")
    print("=" * 50)

    result = Result()

    check_files(result)
    check_imports(result)
    check_config(result)
    check_dna(result)
    check_memory_dirs(result)
    check_instantiation(result)
    check_platform(result)

    # 输出详情
    print("\n" + "─" * 50)
    for icon, msg in result.details:
        print(f"  {icon} {msg}")

    print(result.summary())

    if result.failed > 0:
        print("\n🔴 有失败项，建议修复后再启动运行器。")
        sys.exit(1)
    elif result.warnings > 0:
        print("\n🟡 有警告项，运行器可以启动但建议关注。")
        sys.exit(0)
    else:
        print("\n🟢 全部通过，放心启动！")
        sys.exit(0)


if __name__ == "__main__":
    main()

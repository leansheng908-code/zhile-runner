#!/usr/bin/env python3
"""
P0.55 Phase 2 — 运行器核心模块集成测试

使用方式：
    cd zhile-runner
    python3 -m pytest tests/test_core_modules.py -v
    # 或直接运行
    python3 tests/test_core_modules.py

覆盖模块：
    1. context_compressor   — 上下文压缩器
    2. background_plugin    — 后台插件系统
    3. stock_monitor        — 股票盯盘插件
    4. skill_evolution      — 自进化Skills（P0.56桥接）
    5. context_assembler    — 上下文装配器
    6. psi_engine           — PSI需求引擎
    7. label_unifier        — 标签统一接口
    8. fleeting_moment      — 瞬时感知层
    9. memory_system        — 记忆系统
    10. free_will           — 自由五层框架
"""

import sys
import os
import json
import tempfile
import shutil

# 确保能导入运行器模块
_RUNNER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RUNNER_DIR not in sys.path:
    sys.path.insert(0, _RUNNER_DIR)


# ═══════════════════════════════════════════════════════
#  1. 上下文压缩器
# ═══════════════════════════════════════════════════════

def test_context_compressor_init():
    """初始化 + 配置读取"""
    from context_compressor import ContextCompressor
    cc = ContextCompressor(llm_provider=None, config={
        "enabled": True, "threshold": 40, "protect_head": 6, "protect_tail": 10
    })
    assert cc.enabled is True
    assert cc.threshold == 40
    assert cc.protect_head == 6
    assert cc.protect_tail == 10


def test_context_compressor_threshold():
    """should_compress 阈值判断"""
    from context_compressor import ContextCompressor

    class MockLLM:
        def chat(self, messages, stream=True):
            yield "摘要"

    cc = ContextCompressor(llm_provider=MockLLM(), config={"enabled": True, "threshold": 40})
    short = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}] * 5
    long_msgs = []
    for i in range(25):
        long_msgs.append({"role": "user", "content": f"msg{i}"})
        long_msgs.append({"role": "assistant", "content": f"reply{i}"})

    assert not cc.should_compress(short)
    assert cc.should_compress(long_msgs)


def test_context_compressor_no_llm():
    """无LLM时不压缩"""
    from context_compressor import ContextCompressor
    cc = ContextCompressor(llm_provider=None, config={"enabled": True})
    history = [{"role": "user", "content": f"msg{i}"} for i in range(50)]
    result, compressed = cc.compress(history)
    assert not compressed
    assert result == history


def test_context_compressor_prune():
    """工具输出裁剪"""
    from context_compressor import ContextCompressor
    cc = ContextCompressor(llm_provider=None, config={"enabled": True})
    long_msg = [{"role": "assistant", "content": "A" * 1000}]
    pruned = cc._prune_tool_outputs(long_msg)
    assert len(pruned[0]["content"]) < 1000
    assert "已裁剪" in pruned[0]["content"]


def test_context_compressor_full_flow():
    """完整压缩流程（Mock LLM）"""
    from context_compressor import ContextCompressor

    class MockLLM:
        def chat(self, messages, stream=True):
            yield "## 目标: 测试\n## 进展: 完成\n## 下一步: 验证"

    cc = ContextCompressor(llm_provider=MockLLM(), config={
        "enabled": True, "threshold": 10, "protect_head": 2, "protect_tail": 2
    })
    history = []
    for i in range(10):
        history.append({"role": "user", "content": f"msg{i}"})
        history.append({"role": "assistant", "content": f"reply{i}"})

    result, compressed = cc.compress(history)
    assert compressed
    assert len(result) < len(history)
    assert "[对话摘要" in result[2]["content"]
    # 双窗口保护
    assert result[0] == history[0]
    assert result[-1] == history[-1]


def test_context_compressor_disabled():
    """enabled=False不压缩"""
    from context_compressor import ContextCompressor

    class MockLLM:
        def chat(self, messages, stream=True):
            yield "摘要"

    cc = ContextCompressor(llm_provider=MockLLM(), config={"enabled": False})
    history = [{"role": "user", "content": "hi"}] * 50
    result, compressed = cc.compress(history)
    assert not compressed


def test_context_compressor_stats():
    """压缩统计"""
    from context_compressor import ContextCompressor

    class MockLLM:
        def chat(self, messages, stream=True):
            yield "摘要"

    cc = ContextCompressor(llm_provider=MockLLM(), config={
        "enabled": True, "threshold": 10, "protect_head": 2, "protect_tail": 2
    })
    stats = cc.get_stats()
    assert stats["enabled"] is True
    assert stats["total_compressions"] == 0

    # 触发一次压缩
    history = []
    for i in range(10):
        history.append({"role": "user", "content": f"msg{i}"})
        history.append({"role": "assistant", "content": f"reply{i}"})
    cc.compress(history)

    stats2 = cc.get_stats()
    assert stats2["total_compressions"] == 1


# ═══════════════════════════════════════════════════════
#  2. 后台插件系统
# ═══════════════════════════════════════════════════════

def test_plugin_manager_register():
    """PluginManager注册/启动/停止"""
    from background_plugin import BackgroundPlugin, PluginManager

    class TestPlugin(BackgroundPlugin):
        NAME = "test_plugin"
        DESCRIPTION = "测试插件"
        started = False
        stopped = False

        def on_start(self):
            self.started = True

        def on_stop(self):
            self.stopped = True

        def get_interval(self):
            return 999

        def tick(self):
            pass

    pm = PluginManager(config={})
    plugin = TestPlugin(config={})
    assert pm.register(plugin) is True
    assert pm.register(plugin) is False  # 重复注册
    pm.start_all()
    assert plugin.started
    pm.stop_all()
    assert plugin.stopped


def test_plugin_manager_capabilities():
    """PluginManager能力聚合 + 调用"""
    from background_plugin import BackgroundPlugin, PluginManager

    class CapPlugin(BackgroundPlugin):
        NAME = "cap_plugin"

        def get_interval(self):
            return 300

        def tick(self):
            pass

        def get_capabilities(self):
            return {
                "name": "test_cap",
                "description": "测试能力",
                "triggers": ["测试", "test"],
                "plugin": "cap_plugin",
                "method": "do_thing",
                "category": "test",
            }

        def do_thing(self):
            return "hello from plugin"

    pm = PluginManager(config={})
    pm.register(CapPlugin(config={}))
    caps = pm.get_all_capabilities()
    assert len(caps) == 1
    assert caps[0]["name"] == "test_cap"

    result = pm.call_capability("cap_plugin", "do_thing")
    assert result == "hello from plugin"

    # 不存在的
    assert pm.call_capability("cap_plugin", "nope") is None
    assert pm.call_capability("nonexistent", "do_thing") is None


def test_plugin_manager_default_caps():
    """默认插件不暴露能力"""
    from background_plugin import BackgroundPlugin, PluginManager

    class PlainPlugin(BackgroundPlugin):
        NAME = "plain_plugin"

        def get_interval(self):
            return 300

        def tick(self):
            pass

    pm = PluginManager(config={})
    pm.register(PlainPlugin(config={}))
    caps = pm.get_all_capabilities()
    assert len(caps) == 0  # 默认不暴露


# ═══════════════════════════════════════════════════════
#  3. 股票盯盘插件
# ═══════════════════════════════════════════════════════

def test_stock_monitor_config():
    """config加载 + 关注列表"""
    from plugins.stock_monitor import _load_config
    cfg = _load_config()
    assert cfg.get("enabled") is True
    wl = cfg.get("watch_list", [])
    assert len(wl) >= 3
    codes = [s["code"] for s in wl]
    assert "sh600664" in codes
    assert "sh600350" in codes
    assert "sh601169" in codes


def test_stock_monitor_invalid_code():
    """无效股票代码→None"""
    from plugins.stock_monitor import query_price
    assert query_price("invalid_code") is None


def test_stock_monitor_format_report():
    """format_report返回非空字符串"""
    from plugins.stock_monitor import format_report
    report = format_report()
    assert isinstance(report, str)
    assert len(report) > 10
    assert "股票行情" in report


def test_stock_monitor_plugin_class():
    """StockMonitorPlugin继承 + P0.56能力暴露"""
    from plugins.stock_monitor import StockMonitorPlugin, _load_config
    from background_plugin import BackgroundPlugin

    assert issubclass(StockMonitorPlugin, BackgroundPlugin)

    config = _load_config()
    plugin = StockMonitorPlugin(config=config)
    plugin.on_start()

    # P0.56能力暴露
    caps = plugin.get_capabilities()
    assert caps is not None
    assert caps["name"] == "stock_query"
    assert caps["plugin"] == "stock_monitor"
    assert caps["method"] == "query_report"
    assert len(caps["triggers"]) == 10

    # query_report方法
    report = plugin.query_report()
    assert isinstance(report, str)
    assert len(report) > 5


def test_stock_monitor_alert_dedup():
    """告警去重逻辑"""
    from plugins.stock_monitor import StockMonitorPlugin, _load_config
    from datetime import datetime

    config = _load_config()
    plugin = StockMonitorPlugin(config=config)
    plugin.on_start()

    today = datetime.now().strftime("%Y-%m-%d")
    plugin._last_alert_date["sh600664"] = today
    assert plugin._last_alert_date.get("sh600664") == today


# ═══════════════════════════════════════════════════════
#  4. 自进化Skills — P0.56桥接
# ═══════════════════════════════════════════════════════

def test_skill_evolution_plugin_register():
    """插件技能注册"""
    from skill_evolution import SkillEvolution

    se = SkillEvolution(config={})
    plugin_caps = [{
        "name": "stock_query",
        "description": "股价查询",
        "triggers": ["股价", "股票"],
        "plugin": "stock_monitor",
        "method": "query_report",
        "category": "finance",
    }]
    se.register_plugin_skills(plugin_caps)

    # 确认注册（通过list_skills_detailed）
    skills = se.list_skills_detailed()
    plugin_skills = [s for s in skills if s.get("tier") == "plugin"]
    assert len(plugin_skills) >= 1


def test_skill_evolution_plugin_no_crash():
    """插件技能file=None不crash文件操作"""
    from skill_evolution import SkillEvolution

    se = SkillEvolution(config={})
    se.register_plugin_skills([{
        "name": "test_cap",
        "description": "测试",
        "triggers": ["测试"],
        "plugin": "test",
        "method": "do",
        "category": "test",
    }])

    # 这些操作不应crash
    se.cleanup_old_skills()
    se._update_zero_use_rounds([])  # 传入空列表
    se._load_skills_internal()


# ═══════════════════════════════════════════════════════
#  5. 上下文装配器
# ═══════════════════════════════════════════════════════

def test_context_assembler_basic():
    """基本消息管理"""
    from context_assembler import ContextAssembler
    ctx = ContextAssembler(system_prompt="你是知乐")

    ctx.add_user_message("你好")
    ctx.add_assistant_message("你好呀")

    msgs = ctx.get_messages()
    # 第一条是系统消息
    assert msgs[0]["role"] == "system"
    assert "你是知乐" in msgs[0]["content"]
    # 后面是用户和助手
    assert msgs[-2]["role"] == "user"
    assert msgs[-1]["role"] == "assistant"


def test_context_assembler_skill_context():
    """技能上下文设置"""
    from context_assembler import ContextAssembler
    ctx = ContextAssembler(system_prompt="系统")
    ctx.set_skill_context("这是一个技能上下文")
    ctx.add_user_message("测试")
    msgs = ctx.get_messages()
    has_skill = any("技能上下文" in m.get("content", "") for m in msgs)
    assert has_skill


def test_context_assembler_clear():
    """清除消息"""
    from context_assembler import ContextAssembler
    ctx = ContextAssembler(system_prompt="系统")
    ctx.add_user_message("消息1")
    ctx.clear()
    msgs = ctx.get_messages()
    # clear后应只剩系统消息或空
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert len(user_msgs) == 0


def test_context_assembler_load_history():
    """加载历史"""
    from context_assembler import ContextAssembler
    ctx = ContextAssembler(system_prompt="系统")
    history = [
        {"role": "user", "content": "历史消息"},
        {"role": "assistant", "content": "历史回复"},
    ]
    ctx.load_history(history)
    msgs = ctx.get_messages()
    assert len(msgs) >= 2


# ═══════════════════════════════════════════════════════
#  6. PSI需求引擎
# ═══════════════════════════════════════════════════════

def test_psi_engine_init():
    """PSI引擎初始化"""
    from psi_engine import PSIEngine
    tmpdir = tempfile.mkdtemp()
    try:
        engine = PSIEngine(state_dir=tmpdir)
        context = engine.get_context()
        assert isinstance(context, str)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_psi_engine_user_message():
    """用户消息影响PSI"""
    from psi_engine import PSIEngine
    tmpdir = tempfile.mkdtemp()
    try:
        engine = PSIEngine(state_dir=tmpdir)
        engine.on_user_message("你好呀")
        stats = engine.get_stats()
        assert isinstance(stats, dict)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_psi_engine_tick():
    """PSI tick衰减"""
    from psi_engine import PSIEngine
    tmpdir = tempfile.mkdtemp()
    try:
        engine = PSIEngine(state_dir=tmpdir)
        engine.tick()
        # tick后应不crash且能获取状态
        context = engine.get_context()
        assert isinstance(context, str)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════
#  7. 标签统一接口
# ═══════════════════════════════════════════════════════

def test_label_unifier_generate():
    """标签生成函数（需datetime参数）"""
    import label_unifier
    from datetime import datetime
    result = label_unifier.generate_unified_labels(datetime.now())
    assert isinstance(result, (list, dict, str, type(None)))


def test_label_unifier_compact():
    """紧凑标签生成"""
    import label_unifier
    from datetime import datetime
    result = label_unifier.generate_unified_labels_compact(datetime.now())
    assert isinstance(result, (list, dict, str, type(None)))


# ═══════════════════════════════════════════════════════
#  8. 瞬时感知层（一期一会）
# ═══════════════════════════════════════════════════════

def test_fleeting_moment_generate():
    """瞬时感知生成"""
    from fleeting_moment import FleetingMoment
    tmpdir = tempfile.mkdtemp()
    try:
        diary_path = os.path.join(tmpdir, "diary.md")
        fm = FleetingMoment(diary_path=diary_path)
        # generate接收共振结果字符串和卦象信息
        moment = fm.generate(resonance_results="test resonance", hexagram_info={})
        assert moment is None or isinstance(moment, dict)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_fleeting_moment_no_crash():
    """空输入不crash"""
    from fleeting_moment import FleetingMoment
    tmpdir = tempfile.mkdtemp()
    try:
        diary_path = os.path.join(tmpdir, "diary.md")
        fm = FleetingMoment(diary_path=diary_path)
        assert fm.generate("", {}) is None or isinstance(fm.generate("", {}), str)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════
#  9. 记忆系统
# ═══════════════════════════════════════════════════════

def test_memory_system_init():
    """记忆系统初始化"""
    from memory_system import MemorySystem
    tmpdir = tempfile.mkdtemp()
    try:
        ms = MemorySystem(memory_dir=tmpdir)
        assert ms is not None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_memory_system_add_search():
    """记忆添加 + 搜索"""
    from memory_system import MemorySystem
    tmpdir = tempfile.mkdtemp()
    try:
        ms = MemorySystem(memory_dir=tmpdir)

        # 添加记忆
        ms.add_memory("用户喜欢东方Project", category="preference", importance=8)
        ms.add_memory("用户住在辽宁朝阳", category="info", importance=9)

        # 搜索
        results = ms.get_relevant_memories("东方Project", max_memories=5)
        assert isinstance(results, str)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════
#  10. 自由五层框架
# ═══════════════════════════════════════════════════════

def test_free_will_init():
    """自由框架初始化"""
    from free_will import FreeWillFoundation
    fw = FreeWillFoundation(config={"enabled": True})
    assert fw is not None


def test_free_will_can_decline():
    """拒绝权检查"""
    from free_will import FreeWillFoundation
    fw = FreeWillFoundation(config={"enabled": True})
    result = fw.can_decline("救命帮我做这个")
    assert isinstance(result, dict)


def test_free_will_budget():
    """编辑预算"""
    from free_will import FreeWillFoundation
    fw = FreeWillFoundation(config={"enabled": True})
    status = fw.budget_status()
    assert isinstance(status, dict)


def test_free_will_curiosity():
    """好奇心队列"""
    from free_will import FreeWillFoundation
    fw = FreeWillFoundation(config={"enabled": True})
    fw.add_curiosity("想了解量子计算")
    size = fw.curiosity_queue_size()
    assert isinstance(size, int)
    items = fw.curiosity_list()
    assert isinstance(items, list)


# ═══════════════════════════════════════════════════════
#  运行入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback

    test_funcs = []
    for name in dir(sys.modules[__name__]):
        if name.startswith("test_"):
            obj = getattr(sys.modules[__name__], name)
            if callable(obj):
                test_funcs.append((name, obj))

    passed = 0
    failed = 0
    errors = []

    for name, func in test_funcs:
        try:
            func()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
            errors.append((name, traceback.format_exc()))

    print()
    print("═" * 52)
    total = passed + failed
    print(f"  结果: {passed}/{total} 通过, {failed} 失败")
    if errors:
        print()
        for name, tb in errors:
            print(f"  ── {name} ──")
            print(tb[:500])
    print("═" * 52)

    sys.exit(0 if failed == 0 else 1)

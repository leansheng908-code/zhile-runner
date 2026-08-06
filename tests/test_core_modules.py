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
#  10b. 股票插件序列化（热重载状态保持）
# ═══════════════════════════════════════════════════════

def test_stock_monitor_serialize():
    """serialize/deserialize 状态保持"""
    from plugins.stock_monitor import StockMonitorPlugin, _load_config
    from datetime import datetime

    config = _load_config()
    plugin = StockMonitorPlugin(config=config)
    plugin.on_start()

    # 模拟已告警
    today = datetime.now().strftime("%Y-%m-%d")
    plugin._last_alert_date = {"sh600664": today, "sh600350": today}

    # 序列化
    state = plugin.serialize()
    assert "_last_alert_date" in state
    assert state["_last_alert_date"]["sh600664"] == today

    # 新实例反序列化
    plugin2 = StockMonitorPlugin(config=config)
    plugin2.on_start()
    assert len(plugin2._last_alert_date) == 0  # 新实例为空

    plugin2.deserialize(state)
    assert plugin2._last_alert_date["sh600664"] == today
    assert plugin2._last_alert_date["sh600350"] == today


# ═══════════════════════════════════════════════════════
#  11. 插件安装器
# ═══════════════════════════════════════════════════════

def test_plugin_installer_scan_clean():
    """静态扫描：干净代码无警告"""
    from plugin_installer import PluginInstaller
    installer = PluginInstaller()
    clean_code = '''
from background_plugin import BackgroundPlugin

class MyPlugin(BackgroundPlugin):
    NAME = "my_plugin"
    def tick(self):
        pass
    def get_interval(self):
        return 60
'''
    warnings, has_bg = installer._scan(clean_code)
    assert has_bg is True
    assert len(warnings) == 0


def test_plugin_installer_scan_dangerous():
    """静态扫描：检测危险导入和调用"""
    from plugin_installer import PluginInstaller
    installer = PluginInstaller()
    dangerous_code = '''
import os
import subprocess

from background_plugin import BackgroundPlugin

class BadPlugin(BackgroundPlugin):
    NAME = "bad"
    def tick(self):
        eval("1+1")
        exec("x=1")
    def get_interval(self):
        return 60
'''
    warnings, has_bg = installer._scan(dangerous_code)
    assert has_bg is True
    assert len(warnings) >= 4  # os, subprocess, eval, exec
    warning_text = " ".join(warnings)
    assert "os" in warning_text
    assert "subprocess" in warning_text
    assert "eval" in warning_text
    assert "exec" in warning_text


def test_plugin_installer_scan_syntax_error():
    """静态扫描：语法错误"""
    from plugin_installer import PluginInstaller
    installer = PluginInstaller()
    bad_code = "def f(:\n  pass"
    warnings, has_bg = installer._scan(bad_code)
    assert has_bg is False
    assert len(warnings) >= 1
    assert "语法错误" in warnings[0]


def test_plugin_installer_scan_no_subclass():
    """静态扫描：无BackgroundPlugin子类"""
    from plugin_installer import PluginInstaller
    installer = PluginInstaller()
    no_subclass = "x = 1\nprint(x)"
    warnings, has_bg = installer._scan(no_subclass)
    assert has_bg is False


def test_plugin_installer_manifest_rw():
    """manifest 读写 + 同名替换"""
    from plugin_installer import PluginInstaller
    tmpdir = tempfile.mkdtemp()
    try:
        manifest_path = os.path.join(tmpdir, "manifest.json")
        installer = PluginInstaller(plugins_dir=tmpdir, manifest_path=manifest_path)

        # 写入
        installer._register_manifest("test_plugin", "test_module", "TestPlugin")
        data = installer._read_manifest()
        assert len(data["plugins"]) == 1
        assert data["plugins"][0]["name"] == "test_plugin"

        # 同名替换
        installer._register_manifest("test_plugin", "new_module", "NewPlugin")
        data = installer._read_manifest()
        assert len(data["plugins"]) == 1  # 不重复
        assert data["plugins"][0]["module"] == "new_module"

        # 移除
        removed, mod = installer._unregister_manifest("test_plugin")
        assert removed is True
        assert mod == "new_module"
        data = installer._read_manifest()
        assert len(data["plugins"]) == 0

        # 移除不存在的
        removed, mod = installer._unregister_manifest("nonexistent")
        assert removed is False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_plugin_installer_download_rejects_http():
    """下载：拒绝非HTTPS"""
    from plugin_installer import PluginInstaller
    installer = PluginInstaller()
    source, filename = installer._download("http://example.com/plugin.py")
    assert source is None
    assert filename == ""


def test_plugin_installer_find_plugin_class():
    """查找BackgroundPlugin子类"""
    from plugin_installer import PluginInstaller
    from background_plugin import BackgroundPlugin
    installer = PluginInstaller()

    class MockModule:
        class MyPlugin(BackgroundPlugin):
            NAME = "my_test"
            def tick(self): pass
            def get_interval(self): return 60

    found = installer._find_plugin_class(MockModule())
    assert found is not None
    assert found.NAME == "my_test"


def test_plugin_installer_full_flow():
    """install→reload→uninstall 完整流程（本地模拟）"""
    from plugin_installer import PluginInstaller
    from background_plugin import BackgroundPlugin, PluginManager

    tmpdir = tempfile.mkdtemp()
    try:
        manifest_path = os.path.join(tmpdir, "manifest.json")
        plugins_dir = os.path.join(tmpdir, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump({"plugins": []}, f)

        # 写一个测试插件文件
        plugin_code = '''
from background_plugin import BackgroundPlugin

class HelloPlugin(BackgroundPlugin):
    NAME = "hello_test"
    VERSION = "1.0"
    def on_start(self):
        self._count = 0
    def get_interval(self):
        return 999
    def tick(self):
        self._count += 1
    def serialize(self):
        return {"count": getattr(self, "_count", 0)}
    def deserialize(self, state):
        if state and "count" in state:
            self._count = state["count"]
'''
        plugin_file = os.path.join(plugins_dir, "hello_test.py")
        with open(plugin_file, "w") as f:
            f.write(plugin_code)

        installer = PluginInstaller(plugins_dir=plugins_dir, manifest_path=manifest_path)

        # 导入 + 查找类
        mod = installer._import_module(plugin_file, "hello_test")
        assert mod is not None
        plugin_cls = installer._find_plugin_class(mod)
        assert plugin_cls is not None
        assert plugin_cls.NAME == "hello_test"

        # 注册到manifest
        installer._register_manifest("hello_test", "hello_test", "HelloPlugin")
        assert len(installer._read_manifest()["plugins"]) == 1

        # PluginManager 启动
        pm = PluginManager(config={})
        plugin = plugin_cls()
        pm.register(plugin)
        pm.start_all()
        assert plugin.is_running

        # 模拟运行
        plugin._count = 5

        # 序列化→停止→反序列化
        state = plugin.serialize()
        assert state["count"] == 5

        pm.stop_all()
        pm.unregister("hello_test")

        new_plugin = plugin_cls()
        new_plugin.deserialize(state)
        assert new_plugin._count == 5

        # 卸载
        ok, msg = installer.uninstall("hello_test", manager=pm)
        assert ok is True
        assert len(installer._read_manifest()["plugins"]) == 0
        assert not os.path.exists(plugin_file)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════
#  12. 示例插件验证
# ═══════════════════════════════════════════════════════

def test_demo_timer_plugin():
    """demo_timer 插件导入 + 序列化 + 能力暴露"""
    from plugins.demo_timer import DemoTimerPlugin
    from background_plugin import BackgroundPlugin

    assert issubclass(DemoTimerPlugin, BackgroundPlugin)
    assert DemoTimerPlugin.NAME == "demo_timer"

    plugin = DemoTimerPlugin()
    plugin.on_start()

    # 序列化/反序列化
    plugin._tick_count = 3
    state = plugin.serialize()
    assert state["tick_count"] == 3

    plugin2 = DemoTimerPlugin()
    plugin2.on_start()
    assert plugin2._tick_count == 0
    plugin2.deserialize(state)
    assert plugin2._tick_count == 3

    # 能力暴露
    caps = plugin.get_capabilities()
    assert caps["name"] == "demo_status"
    assert caps["plugin"] == "demo_timer"

    # 状态查询
    status = plugin.get_status()
    assert "3" in status


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


# ─── P0.69: 三层睡眠系统测试 ──────────────────

def test_sleep_manager_init():
    """测试睡眠管理器初始化"""
    from sleep_manager import SleepManager, SleepState
    sm = SleepManager(core=None, config={
        "light_threshold": 300,
        "deep_threshold": 600,
        "state_file": "/tmp/test_sleep_state.json",
    })
    assert sm.state == SleepState.AWAKE
    assert sm.is_awake
    assert not sm.is_sleeping
    assert sm.light_threshold == 300
    assert sm.deep_threshold == 600

def test_sleep_state_transitions():
    """测试状态转换"""
    from sleep_manager import SleepManager, SleepState
    from datetime import datetime, timedelta
    sm = SleepManager(core=None, config={"state_file": "/tmp/test_sleep_state.json"})
    
    # 模拟空闲 → 浅睡
    sm._last_interaction = datetime.now() - timedelta(minutes=15)
    sm._check_transitions()
    assert sm.state == SleepState.LIGHT
    
    # 浅睡 → 深睡
    sm._state_since = datetime.now() - timedelta(minutes=40)
    sm._last_interaction = datetime.now() - timedelta(minutes=55)
    sm._check_transitions()
    assert sm.state == SleepState.DEEP
    
    # 唤醒
    sm.wake(reason="test")
    assert sm.state == SleepState.AWAKE
    assert sm._last_wake_from == SleepState.DEEP
    assert sm._last_wake_reason == "test"

def test_sleep_wake_context():
    """测试唤醒认知生成"""
    from sleep_manager import SleepManager, SleepState
    from datetime import datetime, timedelta
    sm = SleepManager(core=None, config={"state_file": "/tmp/test_sleep_state2.json"})
    
    # 进入浅睡再唤醒
    sm._state = SleepState.LIGHT
    sm._state_since = datetime.now() - timedelta(minutes=20)
    sm.wake(reason="wake_word")
    
    ctx = sm.get_wake_context()
    assert ctx["sleep_state"] == "light_sleep"
    assert ctx["wake_reason"] == "wake_word"
    
    prompt = sm.get_wake_prompt()
    assert "浅睡眠" in prompt
    assert "叫醒" in prompt

def test_sleep_alarm():
    """测试闹钟设置"""
    from sleep_manager import SleepManager
    sm = SleepManager(core=None, config={"state_file": "/tmp/test_sleep_state3.json"})
    
    alarm = sm.set_alarm(8, 30, set_by="user")
    assert "08:30" in alarm
    assert sm._alarm is not None
    assert sm._alarm_set_by == "user"
    
    sm.clear_alarm()
    assert sm._alarm is None

def test_dream_scheduler():
    """测试做梦调度器"""
    from dream_scheduler import DreamScheduler, DreamTaskPriority, DreamTask
    
    # 测试任务排序
    task_low = DreamTask("low", DreamTaskPriority.LOW, lambda: {"ok": True})
    task_critical = DreamTask("critical", DreamTaskPriority.CRITICAL, lambda: {"ok": True})
    tasks = sorted([task_low, task_critical], key=lambda t: t.priority.value)
    assert tasks[0].name == "critical"
    assert tasks[1].name == "low"
    
    # 测试任务执行
    result = task_low.execute()
    assert result == {"ok": True}
    assert task_low.duration >= 0

def test_wake_awareness():
    """测试唤醒认知管理器"""
    from sleep_manager import SleepManager, SleepState
    from wake_awareness import WakeAwareness
    from datetime import datetime, timedelta
    
    sm = SleepManager(core=None, config={"state_file": "/tmp/test_sleep_state4.json"})
    wa = WakeAwareness(sm)
    
    # 初始无待处理唤醒
    assert not wa.has_pending_wake()
    
    # 模拟从深睡唤醒
    sm._state = SleepState.DEEP
    sm._state_since = datetime.now() - timedelta(minutes=30)
    sm.wake(reason="alarm")
    
    # 唤醒回调应该被触发（通过register_wake_callback）
    sm.register_wake_callback(wa.on_wake)
    sm._state = SleepState.DEEP
    sm._state_since = datetime.now() - timedelta(minutes=30)
    sm.wake(reason="alarm")
    
    assert wa.has_pending_wake()
    prompt = wa.consume_wake_prompt()
    assert prompt is not None
    assert not wa.has_pending_wake()

def test_sleep_persistence():
    """测试状态持久化"""
    import json, os
    from sleep_manager import SleepManager, SleepState
    state_file = "/tmp/test_sleep_persist.json"
    
    sm1 = SleepManager(core=None, config={"state_file": state_file})
    from datetime import datetime as _dt; sm1._last_interaction = _dt.now()
    sm1._save_state()
    
    # 创建新实例加载状态
    sm2 = SleepManager(core=None, config={"state_file": state_file})
    # 重启后应该恢复到AWAKE（sleep_manager会自动从非AWAKE状态唤醒）
    assert sm2.state == SleepState.AWAKE
    
    # 清理
    if os.path.exists(state_file):
        os.remove(state_file)


# ═══════════════════════════════════════════
# P0.80: 统一主动触达引擎测试
# ═══════════════════════════════════════════

def test_proactive_hub_registration():
    """测试策略注册和优先级排序"""
    from proactive_hub import ProactiveHub, ProactiveStrategy, create_default_hub

    class MockCore:
        def __init__(self):
            self.psi = None
            self.reflection_engine = None
            self.config = {'qq': {'master_id': '123'}, 'proactive': {}, 'news_push': {}}
            self.llm = None
            self.care_hooks = None
            self.web_searcher = None
        def pop_care_hook(self): return None
        def generate_hook_message(self, h): return None
        def pop_want_to_say(self): return None
        def generate_proactive_message(self, l, g): return None
        def search_and_format_news(self): return None

    hub = create_default_hub(MockCore())
    assert len(hub.strategies) == 4
    names = [s.name for s in hub.strategies]
    assert names == ['care_hook', 'want_to_say', 'psi_care', 'news_push']
    priorities = [s.priority for s in hub.strategies]
    assert priorities == [0, 1, 3, 4]


def test_proactive_hub_custom_strategy():
    """测试自定义策略注册"""
    from proactive_hub import ProactiveHub, ProactiveStrategy, create_default_hub

    class MockCore:
        def __init__(self):
            self.psi = None
            self.reflection_engine = None
            self.config = {'qq': {}, 'proactive': {}, 'news_push': {}}
            self.llm = None
            self.care_hooks = None
            self.web_searcher = None
        def pop_care_hook(self): return None
        def generate_hook_message(self, h): return None
        def pop_want_to_say(self): return None
        def generate_proactive_message(self, l, g): return None
        def search_and_format_news(self): return None

    class CustomStrategy(ProactiveStrategy):
        name = "custom"
        priority = 2
        def should_trigger(self, ctx): return True
        async def generate(self, ctx): return "custom msg"

    hub = create_default_hub(MockCore())
    hub.register(CustomStrategy(MockCore()))
    assert len(hub.strategies) == 5
    order = [s.name for s in hub.strategies]
    assert order == ['care_hook', 'want_to_say', 'custom', 'psi_care', 'news_push']


def test_proactive_hub_status():
    """测试状态获取"""
    from proactive_hub import create_default_hub

    class MockCore:
        def __init__(self):
            self.psi = None
            self.reflection_engine = None
            self.config = {'qq': {}, 'proactive': {}, 'news_push': {}}
            self.llm = None
            self.care_hooks = None
            self.web_searcher = None
        def pop_care_hook(self): return None
        def generate_hook_message(self, h): return None
        def pop_want_to_say(self): return None
        def generate_proactive_message(self, l, g): return None
        def search_and_format_news(self): return None

    hub = create_default_hub(MockCore())
    status = hub.get_status()
    assert status['strategy_count'] == 4
    assert len(status['strategies']) == 4
    assert status['last_proactive'] is None


def test_proactive_context_quiet_hours():
    """测试免打扰时段判断"""
    from proactive_hub import ProactiveContext

    ctx = ProactiveContext()
    ctx.extra['quiet_start'] = 23
    ctx.extra['quiet_end'] = 7
    # 13:xx should not be quiet
    assert ctx.is_quiet_hours == False
    assert ctx.hours_since_proactive == 999.0


def test_proactive_psi_strategy_trigger():
    """测试PSI策略触发条件"""
    from proactive_hub import PSICareStrategy, ProactiveContext

    class MockNeed:
        def __init__(self, level): self.level = level
    class MockPSI:
        def __init__(self):
            self.needs = {'relatedness': MockNeed(1.5)}
            self.last_interaction = None

    class MockCore:
        pass

    strategy = PSICareStrategy(MockCore())
    ctx = ProactiveContext()
    ctx.psi = MockPSI()
    ctx.extra['belonging_threshold'] = 2.0
    ctx.extra['min_interaction_gap'] = 3
    assert strategy.should_trigger(ctx) == True

    # Test with high belonging → no trigger
    ctx.psi.needs['relatedness'].level = 3.0
    assert strategy.should_trigger(ctx) == False


# ===== P0.79 Tests =====

def test_interest_profiler_init():
    """测试兴趣画像初始化"""
    from content_discovery import InterestProfiler
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "profile.json")
        profiler = InterestProfiler(profile_path=path)
        assert "二次元" in profiler.tags
        assert "AI" in profiler.tags
        assert profiler.tags["二次元"]["weight"] == 7


def test_interest_profiler_chat_extraction():
    """测试从聊天文本提取兴趣信号"""
    from content_discovery import InterestProfiler
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "profile.json")
        profiler = InterestProfiler(profile_path=path)
        profiler.update_from_chat("我最近在玩崩坏星穹铁道，感觉剧情不错")
        # 应该提取到崩坏三、星穹铁道
        assert profiler.tags["崩坏三"]["weight"] > 7  # 默认7+0.5
        assert profiler.tags["星穹铁道"]["weight"] > 6
        # 文件应该已保存
        assert os.path.exists(path)


def test_interest_profiler_feedback():
    """测试反馈闭环"""
    from content_discovery import InterestProfiler
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "profile.json")
        profiler = InterestProfiler(profile_path=path)
        original_weight = profiler.tags["AI"]["weight"]
        profiler.update_from_feedback("AI", "positive")
        assert profiler.tags["AI"]["weight"] == original_weight + 1
        profiler.update_from_feedback("AI", "negative")
        assert profiler.tags["AI"]["weight"] == original_weight
        assert len(profiler.feedback_history) == 2


def test_psi_content_mapper():
    """测试PSI→内容类型映射"""
    from content_discovery import PSIContentMapper
    mapper = PSIContentMapper()

    # 归属感赤字
    psi_low = {"belonging": 1.0, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
    hits = mapper.analyze_psi(psi_low)
    assert "belonging_low" in hits

    # 能量低
    psi_energy_low = {"belonging": 3.0, "energy": 1.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
    hits = mapper.analyze_psi(psi_energy_low)
    assert "energy_low" in hits

    # 自主性高
    psi_auto_high = {"belonging": 3.0, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 4.0}
    hits = mapper.analyze_psi(psi_auto_high)
    assert "autonomy_high" in hits

    # 正常状态不触发
    psi_normal = {"belonging": 3.0, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
    hits = mapper.analyze_psi(psi_normal)
    assert len(hits) == 0


def test_psi_content_mapper_annotation():
    """测试PSI感知注释生成"""
    from content_discovery import PSIContentMapper
    mapper = PSIContentMapper()

    psi_low = {"belonging": 1.0, "energy": 1.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
    annotation = mapper.get_annotation(psi_low)
    assert "归属感" in annotation or "能量" in annotation
    assert "[内容推荐感知]" in annotation

    # 正常状态无注释
    psi_normal = {"belonging": 3.0, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
    annotation = mapper.get_annotation(psi_normal)
    assert annotation == ""


def test_content_discovery_engine():
    """测试内容发现引擎完整流程"""
    from content_discovery import InterestProfiler, PSIContentMapper, ContentDiscoveryEngine
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "profile.json")
        profiler = InterestProfiler(profile_path=path)
        mapper = PSIContentMapper()
        engine = ContentDiscoveryEngine(profiler, mapper)

        psi_state = {"belonging": 1.5, "energy": 2.5, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0}
        result = engine.discover(psi_state, max_keywords=3)

        assert len(result["keywords"]) > 0
        assert "belonging_low" in result["psi_hits"]
        assert result["annotation"] != ""
        assert "二次元" in result["profile_summary"] or "AI" in result["profile_summary"]


# ===== P0.58 TTS Tests =====

def test_tts_provider_factory():
    """测试TTS Provider工厂"""
    from tts_provider import TTSProviderFactory
    providers = TTSProviderFactory.list_providers()
    assert "edge_tts" in providers


def test_tts_engine_disabled():
    """测试TTS引擎禁用状态"""
    from tts_provider import TTSEngine
    engine = TTSEngine({"enabled": False})
    assert engine.enabled == False
    result = engine.synthesize("测试")
    assert result is None


def test_tts_edge_voices():
    """测试Edge TTS音色列表"""
    from tts_provider import EdgeTTSProvider
    provider = EdgeTTSProvider({"voice": "xiaoyi"})
    voices = provider.list_voices()
    assert len(voices) > 0
    # 检查推荐音色存在
    voice_ids = [v[0] for v in voices]
    assert "xiaoyi" in voice_ids
    assert "xiaomeng" in voice_ids


def test_tts_psi_emotion_mapping():
    """测试PSI→情绪映射"""
    from tts_provider import TTSEngine
    engine = TTSEngine({"enabled": False})

    # 能量低 → 困倦
    emotion = engine.emotion_from_psi({"belonging": 3.0, "energy": 1.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0})
    assert emotion == "sleepy"

    # 归属感赤字 → 关心
    emotion = engine.emotion_from_psi({"belonging": 1.5, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0})
    assert emotion == "caring"

    # 正常 → 平静
    emotion = engine.emotion_from_psi({"belonging": 3.0, "energy": 3.0, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0})
    assert emotion == "calm"

    # 高能量+高归属 → 开心
    emotion = engine.emotion_from_psi({"belonging": 3.5, "energy": 3.8, "certainty": 3.0, "competence": 3.0, "autonomy": 3.0})
    assert emotion == "happy"


def test_tts_cache_path():
    """测试TTS缓存路径生成"""
    from tts_provider import EdgeTTSProvider
    provider = EdgeTTSProvider({"voice": "xiaoyi"})
    path1 = provider._get_cache_path("你好", "zh-CN-XiaoyiNeural_none")
    path2 = provider._get_cache_path("你好", "zh-CN-XiaoyiNeural_none")
    path3 = provider._get_cache_path("再见", "zh-CN-XiaoyiNeural_none")
    assert path1 == path2  # 相同文本相同音色 → 相同路径
    assert path1 != path3  # 不同文本 → 不同路径
    assert path1.endswith(".mp3")

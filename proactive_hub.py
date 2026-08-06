"""
P0.80 — 统一主动触达引擎（Proactive Hub）
将散装的关心/钩子/新闻/吐槽/陪玩等主动触达能力统一为策略插件式调度。

设计：
- 每个策略是一个 ProactiveStrategy 子类，自带 should_trigger() 和 generate()
- 调度器按优先级遍历策略列表，第一个触发即返回
- 公共调度层（免打扰/节流/PSI读取）由 Hub 统一管理
- 新策略只需注册，不动调度逻辑
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import asyncio


class ProactiveStrategy:
    """主动触达策略基类 — 所有策略插件继承此类"""

    name = "base"
    priority = 99  # 数字越小优先级越高
    requires_connection = True  # 是否需要即时连接（QQ WebSocket等）

    def __init__(self, core):
        self.core = core

    def should_trigger(self, ctx: "ProactiveContext") -> bool:
        """判断当前是否应该触发此策略"""
        return False

    async def generate(self, ctx: "ProactiveContext") -> Optional[str]:
        """生成消息内容，返回None表示放弃"""
        return None

    def on_sent(self, ctx: "ProactiveContext", message: str):
        """消息发送成功后的回调（更新状态等）"""
        pass


class ProactiveContext:
    """调度上下文 — 每次调度循环创建一个，传递给所有策略"""

    def __init__(self):
        self.now = datetime.now()
        self.hour = self.now.hour
        self.psi = None  # PSI引擎引用
        self.last_proactive_time: Optional[datetime] = None
        self.last_interaction: Optional[datetime] = None
        self.master_id = None
        self.connection_active = False  # QQ WebSocket / Web SSE 是否活跃
        self.extra: Dict[str, Any] = {}  # 策略间共享数据

    @property
    def is_quiet_hours(self) -> bool:
        """是否在免打扰时段"""
        qs = self.extra.get("quiet_start", 23)
        qe = self.extra.get("quiet_end", 7)
        if qs <= qe:
            return qs <= self.hour < qe
        else:
            return self.hour >= qs or self.hour < qe

    @property
    def hours_since_proactive(self) -> float:
        if not self.last_proactive_time:
            return 999.0
        return (self.now - self.last_proactive_time).total_seconds() / 3600

    @property
    def hours_since_interaction(self) -> float:
        if not self.last_interaction:
            return 999.0
        try:
            return (self.now - self.last_interaction).total_seconds() / 3600
        except Exception:
            return 999.0


class ProactiveHub:
    """统一主动触达引擎 — 调度器 + 策略注册"""

    def __init__(self, core):
        self.core = core
        self.strategies: List[ProactiveStrategy] = []
        self._last_proactive_time: Optional[datetime] = None
        self._last_news_date: Dict[str, str] = {}  # news_{hour}: date
        self._send_callback: Optional[Callable] = None  # 消息发送回调

    def register(self, strategy: ProactiveStrategy):
        """注册策略，按优先级排序插入"""
        self.strategies.append(strategy)
        self.strategies.sort(key=lambda s: s.priority)
        print(f"  📌 主动触达策略已注册: {strategy.name} (priority={strategy.priority})")

    def set_send_callback(self, callback: Callable):
        """设置消息发送回调 — 由平台适配器(QQ/Web)注入"""
        self._send_callback = callback

    def _build_context(self) -> ProactiveContext:
        """构建调度上下文"""
        ctx = ProactiveContext()
        ctx.psi = self.core.psi
        ctx.last_proactive_time = self._last_proactive_time
        ctx.master_id = self.core.config.get("qq", {}).get("master_id")
        ctx.connection_active = True  # 由适配器在调用前设置

        # PSI上次互动时间
        if self.core.psi and self.core.psi.last_interaction:
            try:
                ctx.last_interaction = datetime.fromisoformat(
                    self.core.psi.last_interaction
                )
            except (ValueError, TypeError):
                pass

        # 公共配置
        proactive_cfg = self.core.config.get("proactive", {})
        ctx.extra["quiet_start"] = proactive_cfg.get("quiet_hours_start", 23)
        ctx.extra["quiet_end"] = proactive_cfg.get("quiet_hours_end", 7)
        ctx.extra["min_gap_hours"] = proactive_cfg.get("min_gap_hours", 2)
        ctx.extra["belonging_threshold"] = proactive_cfg.get("belonging_threshold", 2.0)
        ctx.extra["min_interaction_gap"] = proactive_cfg.get("min_interaction_gap_hours", 3)
        ctx.extra["last_news_date"] = self._last_news_date

        return ctx

    async def tick(self) -> Optional[Dict[str, Any]]:
        """
        执行一次调度循环：
        1. 免打扰检查
        2. 节流检查
        3. 按优先级遍历策略
        4. 第一个触发的策略生成消息
        5. 通过回调发送

        返回: {"strategy": name, "message": msg} 或 None
        """
        ctx = self._build_context()

        # 1. 免打扰
        if ctx.is_quiet_hours:
            return None

        # 2. 节流
        min_gap = ctx.extra.get("min_gap_hours", 2)
        if ctx.hours_since_proactive < min_gap:
            return None

        # 3. 按优先级遍历策略
        for strategy in self.strategies:
            try:
                if not strategy.should_trigger(ctx):
                    continue

                message = await strategy.generate(ctx)
                if not message:
                    continue

                # 4. 发送
                if self._send_callback:
                    await self._send_callback(ctx.master_id, message)

                # 5. 更新状态
                self._last_proactive_time = ctx.now
                strategy.on_sent(ctx, message)

                # 更新news_date追踪
                if "news_date_update" in ctx.extra:
                    key, date = ctx.extra["news_date_update"]
                    self._last_news_date[key] = date

                print(f"  💌 [{strategy.name}] 已发送: {message[:50]}")
                return {"strategy": strategy.name, "message": message}

            except Exception as e:
                print(f"  ⚠ 策略 {strategy.name} 异常: {e}")
                continue

        return None

    def get_status(self) -> Dict[str, Any]:
        """获取引擎状态（供/diag使用）"""
        return {
            "strategies": [
                {"name": s.name, "priority": s.priority}
                for s in self.strategies
            ],
            "last_proactive": (
                self._last_proactive_time.isoformat()
                if self._last_proactive_time else None
            ),
            "last_news_dates": dict(self._last_news_date),
            "strategy_count": len(self.strategies),
        }


# ═══════════════════════════════════════════
#  内置策略 — 从 qq.py 硬编码迁移而来
# ═══════════════════════════════════════════


class CareHookStrategy(ProactiveStrategy):
    """优先级0：对话感知关心钩子（P0.32）— 对话延续，最自然"""

    name = "care_hook"
    priority = 0

    def should_trigger(self, ctx: ProactiveContext) -> bool:
        return True  # 总是检查，有钩子就触发

    async def generate(self, ctx: ProactiveContext) -> Optional[str]:
        hook = self.core.pop_care_hook()
        if not hook:
            return None
        ctx.extra["hook"] = hook
        return self.core.generate_hook_message(hook)


class WantToSayStrategy(ProactiveStrategy):
    """优先级1：想说的话队列 — 已积压的内心话"""

    name = "want_to_say"
    priority = 1

    def should_trigger(self, ctx: ProactiveContext) -> bool:
        return True

    async def generate(self, ctx: ProactiveContext) -> Optional[str]:
        return self.core.pop_want_to_say()


class PSICareStrategy(ProactiveStrategy):
    """优先级3：PSI归属感赤字 → 主动关心（P0.31）"""

    name = "psi_care"
    priority = 3

    def should_trigger(self, ctx: ProactiveContext) -> bool:
        if not ctx.psi:
            return False
        belonging = ctx.psi.needs.get("relatedness")
        if not belonging:
            return False
        threshold = ctx.extra.get("belonging_threshold", 2.0)
        if belonging.level >= threshold:
            return False
        min_gap = ctx.extra.get("min_interaction_gap", 3)
        return ctx.hours_since_interaction >= min_gap

    async def generate(self, ctx: ProactiveContext) -> Optional[str]:
        if not ctx.psi:
            return None
        belonging = ctx.psi.needs.get("relatedness")
        if not belonging:
            return None
        return self.core.generate_proactive_message(
            belonging.level, ctx.hours_since_interaction
        )


class NewsPushStrategy(ProactiveStrategy):
    """优先级4：新闻/内容推送（P0.33）— 最低优先级，避免打扰感"""

    name = "news_push"
    priority = 4

    def should_trigger(self, ctx: ProactiveContext) -> bool:
        news_cfg = self.core.config.get("news_push", {})
        if not news_cfg.get("enabled", False):
            return False

        push_windows = news_cfg.get("push_times", [9, 16])
        for pt in push_windows:
            if abs(ctx.hour - pt) <= 1:
                window_key = f"news_{pt}"
                today = ctx.now.strftime("%Y-%m-%d")
                last_dates = ctx.extra.get("last_news_date", {})
                if last_dates.get(window_key) != today:
                    ctx.extra["news_window_key"] = window_key
                    ctx.extra["news_today"] = today
                    return True
        return False

    async def generate(self, ctx: ProactiveContext) -> Optional[str]:
        brief = self.core.search_and_format_news()
        if not brief:
            # 标记已尝试，避免重复搜索
            key = ctx.extra.get("news_window_key")
            today = ctx.extra.get("news_today")
            if key and today:
                ctx.extra["news_date_update"] = (key, today)
            return None

        key = ctx.extra.get("news_window_key")
        today = ctx.extra.get("news_today")
        if key and today:
            ctx.extra["news_date_update"] = (key, today)
        return brief


def create_default_hub(core) -> ProactiveHub:
    """创建带默认策略的Hub实例"""
    hub = ProactiveHub(core)
    # 按优先级注册：钩子(0) > 想说的话(1) > PSI关心(3) > 新闻(4)
    hub.register(CareHookStrategy(core))
    hub.register(WantToSayStrategy(core))
    hub.register(PSICareStrategy(core))
    hub.register(NewsPushStrategy(core))
    return hub

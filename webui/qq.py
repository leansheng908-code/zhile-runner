#!/usr/bin/env python3
"""
知乐QQ适配器 — 通过NapCat反向WS接入QQ

NapCat以反向WebSocket方式连接到本适配器（与AstrBot相同的接入方式）。
需要在NapCat WebUI中配置WS Client指向本适配器地址。

用法:
    python main.py --mode qq
    python main.py --mode qq --port 6199
"""

import asyncio
import json
import random
import re
import time
import websockets
from datetime import datetime

from core import ZhileCore, quality_strip


class QQAdapter:
    """知乐QQ适配器 — OneBot v11反向WS"""

    def __init__(self, core: ZhileCore, host: str = "0.0.0.0",
                 port: int = 6199):
        self.core = core
        self.host = host
        self.port = port
        self.ws_conn = None
        self.self_id = None  # 机器人QQ号
        self._last_proactive_time = None
        self._last_news_date = {}  # P0.33: 记录每天每个时段已推送的新闻 {window_key: "YYYY-MM-DD"}
        self._debounce_tasks = {}  # 消息防抖定时器

    # ─── WS连接 ───────────────────────────────

    async def _on_connect(self, websocket, *args):
        """NapCat WS连接接入"""
        self.ws_conn = websocket
        print(f"  ✓ NapCat已连接")

        # 请求机器人信息
        try:
            await websocket.send(json.dumps({
                "action": "get_login_info",
                "echo": "_login_info"
            }))
        except Exception:
            pass

        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    await self._handle_event(data)
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"  ✗ 出错: {e}")
        except websockets.exceptions.ConnectionClosed:
            print("  ⚠ NapCat断开，等待重连...")
            self.ws_conn = None

    # ─── 事件处理 ─────────────────────────────

    async def _handle_event(self, data: dict):
        """处理OneBot v11事件"""

        # API响应（get_login_info等）
        if data.get("echo") == "_login_info":
            if data.get("retcode") == 0:
                info = data.get("data", {})
                self.self_id = str(info.get("user_id", ""))
                name = info.get("nickname", "")
                print(f"  📋 机器人: {name}({self.self_id})")
            return

        # 只处理消息事件
        if data.get("post_type") != "message":
            return

        # 从事件中获取self_id（备用）
        if data.get("self_id") and not self.self_id:
            self.self_id = str(data["self_id"])
            print(f"  📋 机器人QQ: {self.self_id}")

        msg_type = data.get("message_type")
        raw_msg = data.get("raw_message", "")
        user_id = data.get("user_id", 0)
        group_id = data.get("group_id", 0)

        if not raw_msg.strip():
            return

        # ─── 命令 ───
        if raw_msg.startswith("/"):
            reply = self._handle_command(raw_msg.strip())
            if reply:
                if msg_type == "private":
                    await self._send_private(user_id, reply)
                elif msg_type == "group":
                    await self._send_group(group_id, reply)
            return

        # ─── 私聊（防抖+拆分流式） ───
        if msg_type == "private":
            print(f"  📨 私聊 {user_id}: {raw_msg[:40]}")
            await self._debounce_private(user_id, raw_msg)

        # ─── 群聊（@时回复，防抖+拆分流式） ───
        elif msg_type == "group":
            if not self._check_at_me(data):
                return
            msg = self._strip_at(raw_msg)
            if not msg.strip():
                return
            print(f"  📨 群{group_id} @{user_id}: {msg[:40]}")
            await self._debounce_group(group_id, user_id, msg)

    # ─── @检测 ────────────────────────────────

    def _check_at_me(self, data: dict) -> bool:
        """检查是否@了机器人"""
        if not self.self_id:
            return False
        # 检查message数组
        for seg in data.get("message", []):
            if isinstance(seg, dict) and seg.get("type") == "at":
                if str(seg.get("data", {}).get("qq", "")) == self.self_id:
                    return True
        # 检查CQ码
        return f"[CQ:at,qq={self.self_id}]" in data.get("raw_message", "")

    def _strip_at(self, text: str) -> str:
        """去掉@CQ码，只留文本"""
        return re.sub(r'\[CQ:at,qq=\d+\]', '', text).strip()

    # ─── 消息防抖+拆分流式 ─────────────────────

    async def _debounce_private(self, user_id: int, message: str):
        """私聊防抖：等1.2秒合并连发消息，再处理"""
        sk = f"private_{user_id}"
        self.core.debounce_add(sk, message)
        self.core.check_serious_mode(message)
        old = self._debounce_tasks.pop(sk, None)
        if old and not old.done():
            old.cancel()
        self._debounce_tasks[sk] = asyncio.create_task(
            self._flush_private(sk, user_id))

    async def _debounce_group(self, group_id: int, user_id: int, message: str):
        """群聊防抖"""
        sk = f"group_{group_id}_{user_id}"
        self.core.debounce_add(sk, message)
        self.core.check_serious_mode(message)
        old = self._debounce_tasks.pop(sk, None)
        if old and not old.done():
            old.cancel()
        self._debounce_tasks[sk] = asyncio.create_task(
            self._flush_group(sk, group_id, user_id))

    async def _flush_private(self, sk: str, user_id: int):
        """防抖超时后处理私聊消息"""
        try:
            await asyncio.sleep(self.core._debounce_seconds)
        except asyncio.CancelledError:
            return
        merged = self.core.debounce_flush(sk)
        if not merged:
            return
        reply = self.core.chat_sync(merged)
        parts = self.core.split_message(reply)
        for i, part in enumerate(parts):
            await self._send_private(user_id, part)
            if i < len(parts) - 1:
                await asyncio.sleep(random.uniform(
                    self.core._split_min_delay, self.core._split_max_delay))
        self.core.maybe_auto_scan()

    async def _flush_group(self, sk: str, group_id: int, user_id: int):
        """防抖超时后处理群聊消息"""
        try:
            await asyncio.sleep(self.core._debounce_seconds)
        except asyncio.CancelledError:
            return
        merged = self.core.debounce_flush(sk)
        if not merged:
            return
        reply = self.core.chat_sync(merged)
        parts = self.core.split_message(reply)
        for i, part in enumerate(parts):
            await self._send_group(group_id, part, at_user=user_id)
            if i < len(parts) - 1:
                await asyncio.sleep(random.uniform(
                    self.core._split_min_delay, self.core._split_max_delay))
        self.core.maybe_auto_scan()

    # ─── 命令 ─────────────────────────────────

    def _handle_command(self, cmd: str) -> str:
        c = cmd.lower().strip()
        if c == "/psi":
            psi = self.core.get_psi_stats()
            if not psi.get("needs"):
                return "PSI未启用"
            lines = ["─── 内在状态 ───"]
            for name, status in psi.get("needs", {}).items():
                lines.append(f"{name}: {status}")
            lines.append(f"意识帧: {psi.get('consciousness_frame', 0)}")
            return "\n".join(lines)
        elif c == "/diary":
            content = self.core.auto_diary()
            return f"📝 {content}" if content else "生成失败"
        elif c == "/growth":
            r = self.core.growth_scan()
            if r.get("found"):
                return (f"🌱 {r.get('behavior', '')}\n"
                        f"类型: {r.get('growth_type', '')}")
            return "未发现新行为"
        elif c == "/entities":
            stats = self.core.entity_stats()
            if not stats:
                return "实体图未启用"
            lines = [f"─── 实体图 ───"]
            lines.append(f"实体: {stats['total_entities']} | "
                         f"边: {stats['total_edges']} | "
                         f"均权: {stats['avg_edge_weight']}")
            by_type = stats.get("by_type", {})
            type_str = " | ".join(f"{k}:{v}" for k, v in by_type.items())
            if type_str:
                lines.append(type_str)
            return "\n".join(lines)
        elif c == "/save" or c == "/exit":
            result = self.core.save()
            parts = ["✓ 已保存"]
            if result.get("memories", 0) > 0:
                parts.append(f"✓ 记住了 {result['memories']} 件新的事")
            if result.get("psi"):
                parts.append("✓ 内在状态已保存")
            if c == "/exit":
                parts.append("喵～下次见啦")
            return "\n".join(parts)
        elif c == "/memory":
            stats = self.core.memory_stats()
            if not stats:
                return "记忆系统未启用"
            lines = [f"─── 记忆 ───"]
            lines.append(f"总计: {stats.get('total', 0)}")
            by_dim = stats.get("by_dimension", {})
            for dim, count in by_dim.items():
                lines.append(f"  {dim}: {count}")
            return "\n".join(lines)
        elif c == "/events":
            stats = self.core.event_stats()
            if not stats:
                return "事件轨迹未启用"
            lines = ["─── 事件轨迹 ───"]
            lines.append(f"事件: {stats.get('total_events', 0)} | "
                         f"分叉口: {stats.get('branch_points', 0)}")
            lines.append(f"簇: {stats.get('clusters', 0)} | "
                         f"高置信: {stats.get('high_confidence', 0)}")
            avg = stats.get('avg_confidence', 0)
            lines.append(f"平均置信度: {avg:.2f}")
            return "\n".join(lines)
        elif c == "/cells":
            stats = self.core.somatic_stats()
            if not stats:
                return "体细胞系统未启用"
            lines = ["─── 体细胞 ───"]
            lines.append(f"活跃: {stats.get('active', 0)} | "
                         f"候选: {stats.get('candidate', 0)}")
            lines.append(f"休眠: {stats.get('dormant', 0)} | "
                         f"覆盖: {stats.get('covered', 0)} | "
                         f"丢弃: {stats.get('discarded', 0)}")
            return "\n".join(lines)
        elif c == "/feedback":
            stats = self.core.feedback_stats()
            if not stats:
                return "活体约束层未启用"
            lines = ["─── 活体约束层 ───"]
            weights = stats.get('weights', {})
            changes = stats.get('weight_changes', {})
            for key, val in weights.items():
                ch = changes.get(key, 0)
                arrow = f" ({ch:+.2f})" if ch != 0 else ""
                lines.append(f"  {key}: {val:.2f}{arrow}")
            lines.append(f"总调整: {stats.get('total_adjustments', 0)}次")
            return "\n".join(lines)
        elif c == "/help":
            return ("知乐命令:\n"
                    "/psi - 内在状态\n"
                    "/diary - 知觉日记\n"
                    "/growth - 成长扫描\n"
                    "/entities - 实体图\n"
                    "/memory - 记忆统计\n"
                    "/events - 事件轨迹\n"
                    "/cells - 体细胞\n"
                    "/feedback - 活体约束层\n"
                    "/save - 保存（含记忆提取）\n"
                    "/exit - 保存并道别\n"
                    "/help - 帮助")
        return ""

    # ─── 发消息 ───────────────────────────────

    async def _send_private(self, user_id: int, message: str):
        if not self.ws_conn:
            return
        payload = {
            "action": "send_private_msg",
            "params": {"user_id": user_id, "message": message},
            "echo": str(int(time.time() * 1000)),
        }
        try:
            await self.ws_conn.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            print(f"  ✗ 发送失败: {e}")

    async def _send_group(self, group_id: int, message: str, at_user=None):
        if not self.ws_conn:
            return
        msg = f"[CQ:at,qq={at_user}] {message}" if at_user else message
        payload = {
            "action": "send_group_msg",
            "params": {"group_id": group_id, "message": msg},
            "echo": str(int(time.time() * 1000)),
        }
        try:
            await self.ws_conn.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            print(f"  ✗ 发送失败: {e}")

    # ─── 主动消息（P0.31） ────────────────────

    async def _proactive_loop(self, config: dict):
        """后台主动消息循环 — 定期检查并发送"""
        interval = config.get("check_interval", 1800)
        min_gap = config.get("min_gap_hours", 2)
        quiet_start = config.get("quiet_hours_start", 23)
        quiet_end = config.get("quiet_hours_end", 7)
        belonging_threshold = config.get("belonging_threshold", 2.0)
        min_interaction_gap = config.get("min_interaction_gap_hours", 3)

        while True:
            await asyncio.sleep(interval)
            try:
                await self._check_proactive(
                    min_gap, quiet_start, quiet_end,
                    belonging_threshold, min_interaction_gap,
                )
            except Exception as e:
                print(f"  ⚠ 主动消息异常: {e}")

    async def _check_proactive(
        self, min_gap, quiet_start, quiet_end,
        belonging_threshold, min_interaction_gap,
    ):
        """检查并发送一条主动消息"""
        now = datetime.now()
        hour = now.hour

        # 免打扰时段
        if quiet_start <= quiet_end:
            if quiet_start <= hour < quiet_end:
                return
        else:
            if hour >= quiet_start or hour < quiet_end:
                return

        # 节流：距上次主动消息不足min_gap小时
        if self._last_proactive_time:
            gap_h = (now - self._last_proactive_time).total_seconds() / 3600
            if gap_h < min_gap:
                return

        # 需要NapCat已连接
        if not self.ws_conn:
            return

        master_id = self.core.config.get("qq", {}).get("master_id")
        if not master_id:
            return
        master_id = int(master_id)

        # 优先级0：对话感知关心钩子（P0.32）
        hook = self.core.pop_care_hook()
        if hook:
            message = self.core.generate_hook_message(hook)
            if message:
                await self._send_private(master_id, message)
                self._last_proactive_time = now
                print(f"  🪝 关心钩子已发送 [{hook.get('topic')}]: {message[:40]}")
                return

        # 优先级1：投递"想说的话"队列
        msg = self.core.pop_want_to_say()
        if msg:
            await self._send_private(master_id, msg)
            self._last_proactive_time = now
            print(f"  💌 主动消息已发送: {msg[:40]}")
            return

        # 优先级2：PSI归属感赤字 → 生成主动关心
        if self.core.psi:
            belonging = self.core.psi.needs.get("relatedness")
            if belonging and belonging.level < belonging_threshold:
                last_interaction = self.core.psi.last_interaction
                gap_hours = 0
                if last_interaction:
                    try:
                        last = datetime.fromisoformat(last_interaction)
                        gap_hours = (now - last).total_seconds() / 3600
                    except (ValueError, TypeError):
                        pass

                if gap_hours >= min_interaction_gap:
                    message = self.core.generate_proactive_message(
                        belonging.level, gap_hours
                    )
                    if message:
                        await self._send_private(master_id, message)
                        self._last_proactive_time = now
                        print(f"  💌 主动关心已发送: {message[:40]}")

    # ─── P0.33: 新闻推送 ─────────────────────

    async def _news_loop(self, config: dict):
        """后台新闻推送循环 — 每天定时推送有趣新闻"""
        check_interval = config.get("check_interval", 600)  # 默认10分钟检查一次
        push_windows = config.get("push_times", [9, 16])  # 默认9点和16点
        quiet_start = config.get("quiet_hours_start", 23)
        quiet_end = config.get("quiet_hours_end", 7)

        while True:
            await asyncio.sleep(check_interval)
            try:
                now = datetime.now()
                hour = now.hour

                # 免打扰时段
                if quiet_start <= quiet_end:
                    if quiet_start <= hour < quiet_end:
                        continue
                else:
                    if hour >= quiet_start or hour < quiet_end:
                        continue

                # 检查是否在推送时间窗口内（±1小时）
                in_window = False
                window_key = None
                for pt in push_windows:
                    if abs(hour - pt) <= 1:
                        in_window = True
                        window_key = f"news_{pt}"
                        break

                if not in_window:
                    continue

                # 检查今天这个时段是否已推送
                today = now.strftime("%Y-%m-%d")
                if self._last_news_date.get(window_key) == today:
                    continue

                # 需要NapCat已连接
                if not self.ws_conn:
                    continue

                master_id = self.core.config.get("qq", {}).get("master_id")
                if not master_id:
                    continue
                master_id = int(master_id)

                # 搜索并格式化新闻
                print(f"  📰 开始搜索新闻...")
                brief = self.core.search_and_format_news()
                if brief:
                    await self._send_private(master_id, brief)
                    self._last_news_date[window_key] = today
                    print(f"  📰 新闻已推送: {brief[:50]}")
                else:
                    print(f"  📰 新闻搜索无结果，跳过")
                    self._last_news_date[window_key] = today  # 标记已尝试，避免重复

            except Exception as e:
                print(f"  ⚠ 新闻推送异常: {e}")

    # ─── 启动 ─────────────────────────────────

    def run(self):
        print(f"\n  🐱")
        print(f"  知乐 · QQ运行器 · Phase 4")
        print(f"  DNA {self.core.dna.get_dna_version()} | "
              f"模型 {self.core.llm.model}")
        if self.core.restored_count:
            print(f"  恢复了 {self.core.restored_count} 条历史消息")
        print(f"\n  ➜ 监听: ws://{self.host}:{self.port}")
        print(f"  ➜ NapCat: WS Client → ws://127.0.0.1:{self.port}/ws")
        print(f"  ➜ 请先停掉AstrBot释放端口{self.port}")
        print(f"  ➜ Ctrl+C 退出（自动保存）\n")

        try:
            asyncio.run(self._serve())
        except KeyboardInterrupt:
            pass
        finally:
            self.core.save()
            print("\n  ✓ 会话已保存，喵～")

    async def _serve(self):
        async with websockets.serve(
            self._on_connect, self.host, self.port,
        ):
            print(f"  等待NapCat连接...")
            # P0.37: 后台任务统一由BackgroundTaskManager管理
            self._event_loop = asyncio.get_event_loop()

            def _bg_output(message):
                """后台任务输出回调 — 桥接线程→asyncio"""
                master_id = self.core.config.get("qq", {}).get("master_id")
                if not master_id or not self.ws_conn:
                    return
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._send_private(int(master_id), message),
                        self._event_loop,
                    )
                except Exception as e:
                    print(f"  ⚠ 后台消息桥接失败: {e}")

            self.core.start_background(output_callback=_bg_output)

            proactive_cfg = self.core.config.get("proactive", {})
            news_cfg = self.core.config.get("news_push", {})
            if proactive_cfg.get("enabled", False):
                print(f"  💌 主动消息已启用 (P0.37核心层)")
            if news_cfg.get("enabled", False):
                print(f"  📰 新闻推送已启用 (每日{news_cfg.get('push_times', [9, 16])})")

            await asyncio.Future()  # run forever

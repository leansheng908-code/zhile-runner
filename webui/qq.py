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
import re
import time
import websockets

from core import ZhileCore


class QQAdapter:
    """知乐QQ适配器 — OneBot v11反向WS"""

    def __init__(self, core: ZhileCore, host: str = "0.0.0.0",
                 port: int = 6199):
        self.core = core
        self.host = host
        self.port = port
        self.ws_conn = None
        self.self_id = None  # 机器人QQ号

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

        # ─── 私聊 ───
        if msg_type == "private":
            print(f"  📨 私聊 {user_id}: {raw_msg[:40]}")
            reply = self.core.chat_sync(raw_msg)
            await self._send_private(user_id, reply)
            # P0.3: 自动成长扫描
            self.core.maybe_auto_scan()

        # ─── 群聊（@时回复） ───
        elif msg_type == "group":
            if not self._check_at_me(data):
                return
            msg = self._strip_at(raw_msg)
            if not msg.strip():
                return
            print(f"  📨 群{group_id} @{user_id}: {msg[:40]}")
            reply = self.core.chat_sync(msg)
            await self._send_group(group_id, reply, at_user=user_id)
            # P0.3: 自动成长扫描
            self.core.maybe_auto_scan()

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
            await asyncio.Future()  # run forever

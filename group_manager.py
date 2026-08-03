#!/usr/bin/env python3
"""
知乐群聊多对手关系系统 — P0.10 Phase 1

最小可用版：
  - 群成员识别（谁在说话、@了谁）
  - 主人识别（主人发言优先处理）
  - 基础回复决策（@必回、主人70%回、其他人看情况）
  - 单一关系维度（亲密度0-100）

Phase 2（未来）：四维度关系（信任/亲密/熟悉/尊重）+ 关系衰减
Phase 3（未来）：群氛围感知 + 人际关系网 + 主动参与决策 + 隐私分级
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class GroupMember:
    """群成员"""

    def __init__(self, user_id: str, nickname: str = ""):
        self.user_id = user_id
        self.nickname = nickname
        self.intimacy = 0          # 亲密度 0-100
        self.is_master = False     # 是否是主人
        self.message_count = 0     # 累计消息数
        self.reply_count = 0       # 知乐回复过几次
        self.last_active = ""      # 最后活跃时间
        self.first_seen = datetime.now().isoformat()
        self.notes = ""            # 备注

    def interact(self, replied: bool = False):
        """记录一次互动"""
        self.message_count += 1
        if replied:
            self.reply_count += 1
            # 被回复后亲密度微增
            self.intimacy = min(100, self.intimacy + 1)
        else:
            # 普通消息也微增（但不回复太多的话增长慢）
            self.intimacy = min(100, self.intimacy + 0.2)
        self.last_active = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "intimacy": round(self.intimacy, 1),
            "is_master": self.is_master,
            "message_count": self.message_count,
            "reply_count": self.reply_count,
            "last_active": self.last_active,
            "first_seen": self.first_seen,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GroupMember":
        m = cls(d["user_id"], d.get("nickname", ""))
        m.intimacy = d.get("intimacy", 0)
        m.is_master = d.get("is_master", False)
        m.message_count = d.get("message_count", 0)
        m.reply_count = d.get("reply_count", 0)
        m.last_active = d.get("last_active", "")
        m.first_seen = d.get("first_seen", "")
        m.notes = d.get("notes", "")
        return m


class GroupManager:
    """群聊管理器"""

    # 回复概率配置
    MASTER_REPLY_RATE = 0.7       # 主人消息回复概率
    INTIMACY_THRESHOLD = 30       # 亲密度达到此值才考虑回复
    HIGH_INTIMACY_RATE = 0.4      # 高亲密度（≥50）回复概率
    LOW_INTIMACY_RATE = 0.1       # 低亲密度回复概率
    RANDOM_BUBBLE_RATE = 0.05     # 随机冒泡概率

    def __init__(self, config: dict = None):
        config = config or {}
        self.master_id = config.get("master_id", "")
        self.state_dir = Path(config.get("state_dir", "memory/groups"))
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # 群数据：{group_id: {"members": {user_id: GroupMember}, "name": str}}
        self.groups: Dict[str, dict] = {}
        self._load_all()

    def handle_message(self, group_id: str, user_id: str,
                       nickname: str, message: str,
                       at_me: bool = False) -> dict:
        """
        处理群消息，返回回复决策。

        Args:
            group_id: 群ID
            user_id: 发送者ID
            nickname: 发送者昵称
            message: 消息内容
            at_me: 是否@了知乐

        Returns:
            {should_reply, reason, intimacy, user_info}
        """
        # 确保群和成员存在
        group = self._get_or_create_group(group_id)
        member = self._get_or_create_member(group_id, user_id, nickname)

        # 判断是否是主人
        if user_id == self.master_id:
            member.is_master = True

        # 回复决策
        should_reply = False
        reason = ""

        if at_me:
            should_reply = True
            reason = "被@了"
        elif member.is_master:
            if random.random() < self.MASTER_REPLY_RATE:
                should_reply = True
                reason = "主人消息"
            else:
                reason = "主人消息但本轮不回（真人感）"
        elif member.intimacy >= 50:
            if random.random() < self.HIGH_INTIMACY_RATE:
                should_reply = True
                reason = f"高亲密度({member.intimacy:.0f})"
            else:
                reason = f"高亲密度但概率未中"
        elif member.intimacy >= self.INTIMACY_THRESHOLD:
            if random.random() < self.LOW_INTIMACY_RATE:
                should_reply = True
                reason = f"中等亲密度({member.intimacy:.0f})"
            else:
                reason = f"中等亲密度概率未中"
        else:
            # 低亲密度，极低概率冒泡
            if random.random() < self.RANDOM_BUBBLE_RATE:
                should_reply = True
                reason = "随机冒泡"
            else:
                reason = f"亲密度太低({member.intimacy:.0f})"

        # 记录互动
        member.interact(replied=should_reply)
        self._save_group(group_id)

        return {
            "should_reply": should_reply,
            "reason": reason,
            "intimacy": round(member.intimacy, 1),
            "is_master": member.is_master,
            "message_count": member.message_count,
            "nickname": member.nickname,
        }

    def get_member_info(self, group_id: str, user_id: str) -> Optional[dict]:
        """获取成员信息"""
        group = self.groups.get(group_id)
        if not group:
            return None
        member = group["members"].get(user_id)
        if not member:
            return None
        return member.to_dict()

    def set_intimacy(self, group_id: str, user_id: str, value: float):
        """手动设置亲密度"""
        member = self._get_or_create_member(group_id, user_id)
        member.intimacy = max(0, min(100, value))
        self._save_group(group_id)

    def get_group_members(self, group_id: str) -> List[dict]:
        """获取群成员列表（按亲密度排序）"""
        group = self.groups.get(group_id)
        if not group:
            return []
        members = [m.to_dict() for m in group["members"].values()]
        members.sort(key=lambda x: x["intimacy"], reverse=True)
        return members

    def get_status(self) -> dict:
        total_members = sum(len(g["members"]) for g in self.groups.values())
        return {
            "total_groups": len(self.groups),
            "total_members": total_members,
            "groups": [
                {"group_id": gid, "name": g.get("name", ""),
                 "members": len(g["members"])}
                for gid, g in self.groups.items()
            ],
        }

    # ─── 内部方法 ───────────────────────────────

    def _get_or_create_group(self, group_id: str) -> dict:
        if group_id not in self.groups:
            self.groups[group_id] = {
                "name": "",
                "members": {},
                "created_at": datetime.now().isoformat(),
            }
        return self.groups[group_id]

    def _get_or_create_member(self, group_id: str, user_id: str,
                              nickname: str = "") -> GroupMember:
        group = self._get_or_create_group(group_id)
        if user_id not in group["members"]:
            group["members"][user_id] = GroupMember(user_id, nickname)
        elif nickname and not group["members"][user_id].nickname:
            group["members"][user_id].nickname = nickname
        return group["members"][user_id]

    def _load_all(self):
        """加载所有群数据"""
        for f in self.state_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                group_id = data.get("group_id", f.stem)
                members = {}
                for uid, md in data.get("members", {}).items():
                    members[uid] = GroupMember.from_dict(md)
                self.groups[group_id] = {
                    "name": data.get("name", ""),
                    "members": members,
                    "created_at": data.get("created_at", ""),
                }
            except (json.JSONDecodeError, Exception):
                continue

    def _save_group(self, group_id: str):
        """保存单个群数据"""
        group = self.groups.get(group_id)
        if not group:
            return
        data = {
            "group_id": group_id,
            "name": group.get("name", ""),
            "created_at": group.get("created_at", ""),
            "members": {uid: m.to_dict() for uid, m in group["members"].items()},
        }
        filepath = self.state_dir / f"{group_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

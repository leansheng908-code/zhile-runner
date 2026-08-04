#!/usr/bin/env python3
"""
P0.46③ 自然语言Cron调度器
将自然语言描述转换为cron表达式，并管理定时任务

功能：
  - parse_to_cron(natural_text): 用LLM将自然语言解析为cron表达式
  - create_scheduled_task(cron, callback, description): 创建定时任务
  - list_tasks(): 列出所有定时任务
  - cancel_task(task_id): 取消任务
  - fallback_to_manual(): LLM解析失败时提示手动输入cron

cron格式: 分 时 日 月 周 (5字段)
  示例: "0 9 * * 1-5" = 每个工作日9点
        "0 * * * *"   = 每小时整点
        "*/30 * * * *" = 每30分钟

依赖：requests
"""

import os
import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import requests


# ─── Cron表达式解析器 ──────────────────────────────

class CronParser:
    """简化的cron表达式解析器（5字段：分 时 日 月 周）"""

    # 各字段取值范围
    FIELD_RANGES = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day of month
        (1, 12),   # month
        (0, 6),    # day of week (0=Sunday, 6=Saturday)
    ]
    FIELD_NAMES = ["minute", "hour", "day", "month", "weekday"]
    WEEKDAY_ALIASES = {
        "sun": "0", "mon": "1", "tue": "2", "wed": "3",
        "thu": "4", "fri": "5", "sat": "6",
    }

    @classmethod
    def parse(cls, expr: str) -> List[set]:
        """
        解析cron表达式，返回5个set（每个set包含该字段所有合法值）

        Args:
            expr: 5字段cron表达式，如 "0 9 * * 1-5"

        Returns:
            List[set]: [minute_set, hour_set, day_set, month_set, weekday_set]

        Raises:
            ValueError: 表达式格式错误
        """
        expr = expr.strip().lower()
        # 替换星期缩写
        for alias, num in cls.WEEKDAY_ALIASES.items():
            expr = re.sub(r'\b' + alias + r'\b', num, expr)

        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"cron表达式需要5个字段(分 时 日 月 周)，得到{len(parts)}个: '{expr}'"
            )

        result = []
        for i, part in enumerate(parts):
            lo, hi = cls.FIELD_RANGES[i]
            values = cls._parse_field(part, lo, hi)
            if not values:
                raise ValueError(
                    f"cron字段{cls.FIELD_NAMES[i]}解析为空: '{part}'"
                )
            result.append(values)
        return result

    @classmethod
    def _parse_field(cls, field: str, lo: int, hi: int) -> set:
        """解析单个cron字段"""
        values = set()
        for item in field.split(","):
            item = item.strip()
            if not item:
                continue

            # 处理步长: */n 或 a-b/n
            step = 1
            if "/" in item:
                range_part, step_str = item.split("/", 1)
                step = int(step_str)
                if step <= 0:
                    raise ValueError(f"步长必须>0: '{item}'")
            else:
                range_part = item

            # 解析范围
            if range_part == "*":
                start, end = lo, hi
            elif "-" in range_part:
                parts = range_part.split("-")
                if len(parts) != 2:
                    raise ValueError(f"无效的范围: '{range_part}'")
                start, end = int(parts[0]), int(parts[1])
            else:
                start = end = int(range_part)

            # 边界检查
            if start < lo or end > hi:
                raise ValueError(
                    f"值超出范围[{lo},{hi}]: '{item}'"
                )

            v = start
            while v <= end:
                values.add(v)
                v += step

        return values

    @classmethod
    def next_run(cls, expr: str, after: Optional[datetime] = None) -> Optional[datetime]:
        """
        计算cron表达式的下一次运行时间

        Args:
            expr: cron表达式
            after: 从哪个时间点开始搜索，默认当前时间

        Returns:
            下一次运行时间，如果一年内无匹配则返回None
        """
        fields = cls.parse(expr)
        after = after or datetime.now()

        # 从下一分钟开始搜索
        check = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        max_check = after + timedelta(days=366)

        while check <= max_check:
            # Python weekday(): 0=Monday..6=Sunday
            # Cron dow: 0=Sunday..6=Saturday
            cron_dow = (check.weekday() + 1) % 7

            if (check.minute in fields[0] and
                    check.hour in fields[1] and
                    check.day in fields[2] and
                    check.month in fields[3] and
                    cron_dow in fields[4]):
                return check

            check += timedelta(minutes=1)

        return None

    @classmethod
    def validate(cls, expr: str) -> bool:
        """验证cron表达式是否合法"""
        try:
            cls.parse(expr)
            return True
        except (ValueError, IndexError):
            return False


# ─── 定时任务 ─────────────────────────────────────

class ScheduledTask:
    """单个定时任务的封装"""

    def __init__(self, task_id: str, cron: str, callback: Callable,
                 description: str = ""):
        self.task_id = task_id
        self.cron = cron
        self.callback = callback
        self.description = description
        self.active = True
        self.next_run: Optional[datetime] = None
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def schedule_next(self):
        """计算下次运行时间并设置Timer"""
        with self._lock:
            if not self.active:
                return

            self.next_run = CronParser.next_run(self.cron)
            if self.next_run is None:
                print(f"  ⚠ 任务 {self.task_id} 无效的cron或一年内无匹配时间")
                self.active = False
                return

            delay = (self.next_run - datetime.now()).total_seconds()
            if delay < 0:
                delay = 0

            self._timer = threading.Timer(delay, self._execute)
            self._timer.daemon = True
            self._timer.start()
            print(f"  ⏰ 任务 '{self.description or self.task_id}' "
                  f"下次运行: {self.next_run.strftime('%Y-%m-%d %H:%M')}")

    def _execute(self):
        """Timer回调：执行任务并重新调度"""
        if not self.active:
            return
        try:
            self.callback()
            self.run_count += 1
            self.last_run = datetime.now()
        except Exception as e:
            print(f"  ⚠ 任务 {self.task_id} 执行失败: {e}")
        finally:
            if self.active:
                self.schedule_next()

    def cancel(self):
        """取消任务"""
        with self._lock:
            self.active = False
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def to_dict(self) -> dict:
        """返回任务状态字典"""
        return {
            "task_id": self.task_id,
            "cron": self.cron,
            "description": self.description,
            "active": self.active,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
        }


# ─── 自然语言调度器 ───────────────────────────────

class NaturalLanguageScheduler:
    """
    自然语言Cron调度器

    使用LLM将自然语言描述转换为cron表达式，
    然后通过threading.Timer实现定时任务管理。

    用法:
        scheduler = NaturalLanguageScheduler()
        result = scheduler.parse_to_cron("每个工作日早上9点汇总收件箱")
        # result = {"cron": "0 9 * * 1-5", "description": "...", "task_type": "..."}
        task_id = scheduler.create_scheduled_task(
            result["cron"], my_callback, result["description"]
        )
    """

    # DeepSeek API配置
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-v4-flash"

    # LLM系统提示词
    SYSTEM_PROMPT = """你是一个cron表达式解析器。用户会用自然语言描述定时任务，你需要将其转换为标准的5字段cron表达式。

cron格式: 分 时 日 月 周
- 分: 0-59
- 时: 0-23
- 日: 1-31
- 月: 1-12
- 周: 0-6 (0=周日, 1=周一, ..., 6=周六)

规则:
- "每个工作日" → 周1-5
- "每天" → *
- "每小时" → 时为*
- "每N分钟" → 分为*/N
- "每N小时" → 时为*/N
- "早上9点" → 时为9, 分为0
- "每月1号" → 日为1

你必须严格返回JSON格式，不要包含其他文字:
{"cron": "0 9 * * 1-5", "description": "每个工作日早上9点执行", "task_type": "定时汇总"}

task_type从以下选择: 定时汇总, 定时检查, 定时提醒, 定时推送, 定时清理, 定时备份, 其他"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化调度器

        Args:
            config: 配置字典，可包含:
                - base_url: API地址
                - api_key: API密钥
                - model: 模型名
                - temperature: 温度参数
        """
        cfg = config or {}
        self._load_api_config(cfg)

        # 任务表
        self._tasks: Dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()

    def _load_api_config(self, cfg: dict):
        """加载API配置：优先config.json，其次环境变量"""
        # 尝试从传入的config读取
        llm_cfg = cfg.get("llm", {})

        self.base_url = llm_cfg.get("base_url", self.DEFAULT_BASE_URL)
        self.model = llm_cfg.get("model", self.DEFAULT_MODEL)
        self.temperature = llm_cfg.get("temperature", 0.1)  # 低温度保证输出稳定
        self.api_key = (
            llm_cfg.get("api_key")
            or os.environ.get("DEEPSEEK_API_KEY")
            or ""
        )

        # 如果传入的config没有llm段，尝试从config.json读取
        if not llm_cfg:
            config_path = cfg.get("config_path", "config.json")
            file_cfg = self._load_config_file(config_path)
            if file_cfg:
                file_llm = file_cfg.get("llm", {})
                self.base_url = file_llm.get("base_url", self.base_url)
                self.model = file_llm.get("model", self.DEFAULT_MODEL)
                self.api_key = file_llm.get("api_key", self.api_key)

        # 环境变量覆盖
        env_key = os.environ.get("DEEPSEEK_API_KEY")
        if env_key:
            self.api_key = env_key

    @staticmethod
    def _load_config_file(path: str) -> dict:
        """从文件加载配置"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            return {}

    # ─── 自然语言解析 ─────────────────────────────

    def parse_to_cron(self, natural_text: str) -> dict:
        """
        用LLM将自然语言解析为cron表达式

        Args:
            natural_text: 自然语言描述，如 "每个工作日早上9点汇总收件箱"

        Returns:
            dict: {
                "cron": "0 9 * * 1-5",
                "description": "每个工作日早上9点执行",
                "task_type": "定时汇总"
            }

        Raises:
            RuntimeError: LLM解析失败且无法回退
        """
        if not self.api_key:
            print("  ⚠ 未配置API Key，尝试本地规则匹配...")
            return self._local_parse(natural_text)

        try:
            result = self._call_llm(natural_text)
            if result and CronParser.validate(result.get("cron", "")):
                return result
            else:
                print("  ⚠ LLM返回的cron表达式无效，尝试本地规则匹配...")
                local_result = self._local_parse(natural_text)
                if local_result:
                    return local_result
                return self.fallback_to_manual()
        except Exception as e:
            print(f"  ⚠ LLM解析失败: {e}")
            local_result = self._local_parse(natural_text)
            if local_result:
                return local_result
            return self.fallback_to_manual()

    def _call_llm(self, natural_text: str) -> Optional[dict]:
        """调用DeepSeek API解析自然语言"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": natural_text},
            ],
            "temperature": self.temperature,
            "max_tokens": 256,
            "stream": False,
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # 从回复中提取JSON
        return self._extract_json(content)

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """从LLM回复中提取JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从markdown代码块中提取
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个{...}块
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _local_parse(natural_text: str) -> Optional[dict]:
        """
        本地规则匹配回退（当LLM不可用时）

        支持常见模式：
        - "每个工作日早上9点" → "0 9 * * 1-5"
        - "每小时" → "0 * * * *"
        - "每天X点" → "0 X * * *"
        - "每天晚上10点" → "0 22 * * *"（支持上午/下午/晚上转换）
        - "每N分钟" → "*/N * * * *"
        """
        text = natural_text.lower().strip()

        def _extract_hour(text_str):
            """从文本中提取小时，处理上午/下午/晚上"""
            h_match = re.search(r'(\d+)\s*点', text_str)
            if not h_match:
                return None
            hour = int(h_match.group(1))
            # 处理12小时制→24小时制
            if any(kw in text_str for kw in ["下午", "晚上", "晚间", "傍晚"]):
                if hour < 12:
                    hour += 12
            elif any(kw in text_str for kw in ["凌晨"]):
                if hour == 12:
                    hour = 0
            elif any(kw in text_str for kw in ["中午"]):
                if hour < 12:
                    hour += 12  # 中午12点 = 12, 中午1点 = 13
            return hour

        def _extract_minute(text_str):
            """从文本中提取分钟"""
            m_match = re.search(r'(\d+)\s*分', text_str)
            return int(m_match.group(1)) if m_match else 0

        # 每个工作日 + 时间
        if "工作日" in text:
            hour = _extract_hour(text) or 9
            minute = _extract_minute(text)
            return {
                "cron": f"{minute} {hour} * * 1-5",
                "description": natural_text,
                "task_type": "定时汇总",
            }

        # 每小时
        if "每小时" in text:
            return {
                "cron": "0 * * * *",
                "description": natural_text,
                "task_type": "定时检查",
            }

        # 每N分钟
        m = re.search(r'每\s*(\d+)\s*分钟', text)
        if m:
            n = int(m.group(1))
            return {
                "cron": f"*/{n} * * * *",
                "description": natural_text,
                "task_type": "定时检查",
            }

        # 每N小时
        h = re.search(r'每\s*(\d+)\s*小时', text)
        if h:
            n = int(h.group(1))
            return {
                "cron": f"0 */{n} * * *",
                "description": natural_text,
                "task_type": "定时检查",
            }

        # 每天X点（支持上午/下午/晚上）
        daily = re.search(r'每天.*?(\d+)\s*点', text)
        if daily:
            hour = _extract_hour(text)
            if hour is not None:
                return {
                    "cron": f"0 {hour} * * *",
                    "description": natural_text,
                    "task_type": "定时提醒",
                }

        # 每天
        if "每天" in text:
            return {
                "cron": "0 9 * * *",
                "description": natural_text,
                "task_type": "定时提醒",
            }

        return None

    def fallback_to_manual(self) -> dict:
        """
        LLM解析失败时，提示用户手动输入cron表达式

        Returns:
            dict: 包含提示信息的字典，cron为None表示需要手动输入
        """
        print("\n  ╔══════════════════════════════════════════╗")
        print("  ║  ⚠ 无法自动解析，请手动输入cron表达式    ║")
        print("  ╠══════════════════════════════════════════╣")
        print("  ║  格式: 分 时 日 月 周                     ║")
        print("  ║  示例:                                    ║")
        print("  ║    0 9 * * 1-5    每个工作日9点          ║")
        print("  ║    0 * * * *      每小时整点             ║")
        print("  ║    */30 * * * *   每30分钟               ║")
        print("  ║    0 9 * * *      每天9点                ║")
        print("  ║    0 0 1 * *      每月1号0点             ║")
        print("  ╚══════════════════════════════════════════╝\n")

        return {
            "cron": None,
            "description": "需要手动输入cron表达式",
            "task_type": "待确认",
            "manual_input_required": True,
        }

    # ─── 任务管理 ─────────────────────────────────

    def create_scheduled_task(self, cron: str, callback: Callable,
                              description: str = "") -> str:
        """
        创建定时任务

        Args:
            cron: cron表达式，如 "0 9 * * 1-5"
            callback: 任务回调函数（无参数）
            description: 任务描述

        Returns:
            str: 任务ID

        Raises:
            ValueError: cron表达式无效
        """
        if not CronParser.validate(cron):
            raise ValueError(f"无效的cron表达式: '{cron}'")

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = ScheduledTask(task_id, cron, callback, description)

        with self._lock:
            self._tasks[task_id] = task

        # 计算下次运行并启动Timer
        task.schedule_next()
        print(f"  ✅ 定时任务已创建: {task_id} | {description} | cron={cron}")

        return task_id

    def list_tasks(self) -> List[dict]:
        """
        列出所有定时任务

        Returns:
            List[dict]: 任务状态列表，每个元素为任务的状态字典
        """
        with self._lock:
            return [task.to_dict() for task in self._tasks.values()]

    def cancel_task(self, task_id: str) -> bool:
        """
        取消定时任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.cancel()
            del self._tasks[task_id]
        print(f"  🗑 定时任务已取消: {task_id}")
        return True

    def cancel_all(self):
        """取消所有定时任务"""
        with self._lock:
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()
        print("  🗑 所有定时任务已取消")

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取单个任务状态"""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def status(self) -> dict:
        """获取调度器整体状态"""
        with self._lock:
            tasks = list(self._tasks.values())
        active_count = sum(1 for t in tasks if t.active)
        return {
            "total_tasks": len(tasks),
            "active_tasks": active_count,
            "api_configured": bool(self.api_key),
            "model": self.model,
            "base_url": self.base_url,
        }


# ─── 独立运行入口 ─────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print("  自然语言Cron调度器 · 独立测试")
    print("=" * 52)

    scheduler = NaturalLanguageScheduler()

    # 测试cron解析
    test_cases = [
        "每个工作日早上9点汇总收件箱",
        "每小时检查一次股票",
        "每30分钟同步数据",
        "每天晚上10点备份",
    ]

    for text in test_cases:
        print(f"\n📝 输入: {text}")
        result = scheduler.parse_to_cron(text)
        print(f"   输出: {result}")

    # 测试任务创建
    print("\n" + "─" * 52)
    print("⏰ 测试任务创建")
    print("─" * 52)

    def dummy_callback():
        print(f"  🔔 任务执行 @ {datetime.now().strftime('%H:%M:%S')}")

    task_id = scheduler.create_scheduled_task(
        "*/1 * * * *",  # 每分钟（测试用）
        dummy_callback,
        "每分钟测试任务"
    )

    print(f"\n📋 任务列表:")
    for t in scheduler.list_tasks():
        print(f"  {t}")

    print(f"\n📊 调度器状态: {scheduler.status()}")

    # 取消任务
    scheduler.cancel_task(task_id)
    print(f"\n📋 取消后任务列表: {scheduler.list_tasks()}")

    print(f"\n{'=' * 52}")
    print("  测试完成")
    print(f"{'=' * 52}")

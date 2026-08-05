#!/usr/bin/env python3
"""
股票盯盘插件 — 使用新浪财经API查实时股价

功能：
  - query_price(stock_code)  查单只股票实时行情
  - query_all()              查所有关注股票（从config.json读取）
  - format_report()          格式化输出所有股票行情
  - check_alerts()           检查目标价告警

独立运行：python3 plugins/stock_monitor.py
依赖：requests（标准库外唯一依赖）

新浪API说明：
  - URL: http://hq.sinajs.cn/list=sh600664
  - 必须带 Referer: https://finance.sina.com.cn 头，否则返回空
  - 返回格式: var hq_str_sh600664="名称,开盘,昨收,当前,最高,最低,..."
  - 免费免key，国内直连
"""

import os
import json
import requests
from datetime import datetime

# ─── 常量 ──────────────────────────────────────

SINA_API = "http://hq.sinajs.cn/list="
SINA_REFERER = "https://finance.sina.com.cn"
REQUEST_TIMEOUT = 10

# 默认关注列表（独立运行时使用）
DEFAULT_STOCKS = [
    {"code": "sh600664", "name": "哈药股份", "strategy": "2/7/9/10月周期低买高卖"},
    {"code": "sh600350", "name": "山东高速", "cost": 11.425, "target": 12.0},
    {"code": "sh601169", "name": "北京银行", "strategy": "2028起大周期"},
]


# ─── 核心函数 ──────────────────────────────────

def _load_config():
    """从config.json读取stocks配置，读不到则用默认值"""
    # 尝试多个可能的config路径
    config_paths = [
        "config.json",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"),
        os.path.join(os.path.dirname(__file__), "..", "config.json"),
    ]
    for path in config_paths:
        path = os.path.normpath(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                stocks_cfg = cfg.get("stocks", {})
                if stocks_cfg.get("enabled") and stocks_cfg.get("watch_list"):
                    return stocks_cfg
            except (json.JSONDecodeError, IOError):
                pass
    # 回退到默认配置
    return {
        "enabled": True,
        "watch_list": DEFAULT_STOCKS,
        "alert_enabled": True,
        "check_interval": 1800,
    }


def query_price(stock_code):
    """
    查询单只股票实时行情

    Args:
        stock_code: 股票代码，如 "sh600664"

    Returns:
        dict: {
            "code": "sh600664",
            "name": "哈药股份",
            "current": 3.45,       # 当前价
            "open": 3.40,          # 开盘价
            "yesterday_close": 3.38, # 昨收价
            "high": 3.50,          # 最高价
            "low": 3.35,           # 最低价
            "change_pct": 2.07,    # 涨跌幅%
        }
        查询失败返回 None
    """
    url = SINA_API + stock_code
    headers = {"Referer": SINA_REFERER}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.encoding = "gbk"
        text = resp.text.strip()

        # 解析: var hq_str_sh600664="名称,开盘,昨收,当前,最高,最低,..."
        if 'hq_str_' not in text or '=""' in text:
            return None

        # 提取引号内内容
        start = text.index('"') + 1
        end = text.rindex('"')
        fields = text[start:end].split(",")

        if len(fields) < 6:
            return None

        name = fields[0]
        open_price = float(fields[1])
        yesterday_close = float(fields[2])
        current = float(fields[3])
        high = float(fields[4])
        low = float(fields[5])

        # 涨跌幅
        if yesterday_close > 0:
            change_pct = round((current - yesterday_close) / yesterday_close * 100, 2)
        else:
            change_pct = 0.0

        return {
            "code": stock_code,
            "name": name,
            "current": current,
            "open": open_price,
            "yesterday_close": yesterday_close,
            "high": high,
            "low": low,
            "change_pct": change_pct,
        }

    except requests.RequestException as e:
        print(f"[stock_monitor] 网络错误 {stock_code}: {e}")
        return None
    except (ValueError, IndexError) as e:
        print(f"[stock_monitor] 解析错误 {stock_code}: {e}")
        return None


def query_all():
    """
    查询所有关注股票的实时行情

    Returns:
        list[dict]: 每只股票的行情字典（查询失败的会被跳过）
    """
    cfg = _load_config()
    watch_list = cfg.get("watch_list", [])
    results = []

    for stock in watch_list:
        code = stock["code"]
        info = query_price(code)
        if info:
            # 合并配置中的额外字段（cost, target, strategy等）
            info["strategy"] = stock.get("strategy", "")
            info["cost"] = stock.get("cost")
            info["target"] = stock.get("target")
            results.append(info)

    return results


def format_report():
    """
    格式化输出所有关注股票的行情报告

    Returns:
        str: 格式化的行情报告文本
    """
    results = query_all()
    if not results:
        return "❌ 未能获取任何股票行情（检查网络连接）"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"📊 股票行情  {now}")
    lines.append("─" * 52)

    for r in results:
        # 涨跌标识
        if r["change_pct"] > 0:
            arrow = "🔴"  # 红涨
            pct_str = f"+{r['change_pct']}%"
        elif r["change_pct"] < 0:
            arrow = "🟢"  # 绿跌
            pct_str = f"{r['change_pct']}%"
        else:
            arrow = "⚪"
            pct_str = "0.00%"

        line = f"{arrow} {r['name']}({r['code']})"
        line += f"  现价:{r['current']:.3f}"
        line += f"  {pct_str}"
        lines.append(line)

        detail = f"   开:{r['open']:.3f}  昨收:{r['yesterday_close']:.3f}"
        detail += f"  高:{r['high']:.3f}  低:{r['low']:.3f}"
        lines.append(detail)

        # 成本与盈亏
        if r.get("cost"):
            cost = r["cost"]
            profit_pct = round((r["current"] - cost) / cost * 100, 2)
            sign = "+" if profit_pct >= 0 else ""
            target_str = ""
            if r.get("target"):
                target_str = f"  目标:{r['target']:.3f}"
            lines.append(f"   成本:{cost:.3f}  盈亏:{sign}{profit_pct}%{target_str}")

        # 策略
        if r.get("strategy"):
            lines.append(f"   策略: {r['strategy']}")

        lines.append("")

    return "\n".join(lines).rstrip()


def check_alerts():
    """
    检查是否达到目标价，返回告警消息列表

    Returns:
        list[str]: 告警消息列表，无告警则返回空列表
    """
    cfg = _load_config()
    if not cfg.get("alert_enabled", True):
        return []

    results = query_all()
    alerts = []

    for r in results:
        # 检查目标价
        if r.get("target"):
            target = r["target"]
            if r["current"] >= target:
                msg = (f"🎯 {r['name']}({r['code']}) "
                       f"已达到目标价 {target:.3f}！"
                       f"当前价 {r['current']:.3f}，"
                       f"涨幅 +{r['change_pct']}%")
                alerts.append(msg)

        # 检查成本线（跌破成本5%预警）
        if r.get("cost"):
            cost = r["cost"]
            drop_pct = (r["current"] - cost) / cost * 100
            if drop_pct <= -5:
                msg = (f"⚠️ {r['name']}({r['code']}) "
                       f"跌破成本线！成本 {cost:.3f}，"
                       f"当前 {r['current']:.3f}，"
                       f"亏损 {drop_pct:.1f}%")
                alerts.append(msg)

    return alerts


# ─── 独立运行入口 ──────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print("  股票盯盘插件 · 独立测试")
    print("=" * 52)
    print()

    # 打印所有关注股票行情
    report = format_report()
    print(report)
    print()

    # 检查告警
    print("─" * 52)
    print("🔔 告警检查")
    print("─" * 52)
    alerts = check_alerts()
    if alerts:
        for a in alerts:
            print(f"  {a}")
    else:
        print("  ✅ 暂无告警")
    print()
    print(f"{'=' * 52}")
    print(f"  查询完成 · {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 52}")


# ─── BackgroundPlugin 子类 ─────────────────────

import sys
import os

# 确保能导入 background_plugin
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from background_plugin import BackgroundPlugin


class StockMonitorPlugin(BackgroundPlugin):
    """股票盯盘后台插件 — 周期性检查股价并推送告警"""

    NAME = "stock_monitor"
    DESCRIPTION = "股票盯盘插件（新浪财经API，目标价/成本线告警）"
    VERSION = "1.1"

    def on_start(self):
        self._last_alert_date = {}  # {stock_code: "YYYY-MM-DD"} 避免同一天重复告警
        print(f"  📈 股票盯盘插件启动，关注 {len(self._get_watch_list())} 只股票")

    def get_interval(self) -> float:
        return self.config.get("check_interval", 1800)  # 默认30分钟

    def tick(self):
        """每次循环：检查告警，有告警则通过输出通道推送"""
        # 周末跳过（股市休市）
        now = datetime.now()
        if now.weekday() >= 5:  # 5=周六, 6=周日
            return

        # 非交易时段跳过（9:15-15:30）
        hour_min = now.hour * 100 + now.minute
        if hour_min < 915 or hour_min > 1530:
            return

        # 检查告警
        try:
            alerts = check_alerts()
            if not alerts:
                return

            today = now.strftime("%Y-%m-%d")
            for alert in alerts:
                # 从告警文本提取股票代码去重
                # 格式: "🎯 哈药股份(sh600664) ..." 或 "⚠️ 哈药股份(sh600664) ..."
                code = ""
                if "(" in alert and ")" in alert:
                    code = alert[alert.index("(")+1:alert.index(")")]

                if code and self._last_alert_date.get(code) == today:
                    continue  # 今天已告警过，跳过

                self.send_output(alert)
                if code:
                    self._last_alert_date[code] = today
                print(f"  📈 股票告警已推送: {alert[:50]}")

        except Exception as e:
            print(f"  ⚠ stock_monitor tick 异常: {e}")

    def _get_watch_list(self):
        cfg = _load_config()
        return cfg.get("watch_list", [])

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d101 用户侧实时行情大屏（Tkinter）。

这是一个只依赖 Tkinter 和 ``websocket-client`` 的用户侧测试面板：

* 通过本地 ``ws://127.0.0.1:8080/d101`` 订阅实时行情；
* 支持行情全推、K 线切片和盘口异动三个独立 TAB；
* 行情 TAB 支持 ``universe`` 全市场订阅和 ``limit=0`` 全量推送；
* 盘口异动 TAB 按时间/序号去重排序，滚动到底部自动用游标拼接更早历史；
* 按 ``code`` 合并增量行情，处理 null、缺失字段和单位换算；
* 每个 TAB 用独立的大型 Treeview 表格实时更新，并支持横向查看全部字段；
* 所有网络接收都在后台线程，Tkinter 主线程只负责绘制和交互。

运行：

    python d101_gui.py
    python d101_gui.py --url ws://127.0.0.1:8080/d101

依赖：

    python -m pip install websocket-client

先启动本地数据接口程序并完成登录，再点击面板右上角的“连接”。
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import re
import sys
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

try:
    import websocket
except ImportError:  # pragma: no cover - 运行时给出更友好的 GUI 提示
    websocket = None  # type: ignore[assignment]


def websocket_install_hint() -> str:
    return f'当前 Python：{sys.executable}\n请执行："{sys.executable}" -m pip install websocket-client'


# ── 视觉系统 ────────────────────────────────────────────────────────────────

BG = "#070b14"
BG_2 = "#0a1220"
SURFACE = "#101a2a"
SURFACE_2 = "#14243a"
SURFACE_3 = "#0c1524"
INPUT = "#0b1524"
BORDER = "#203650"
BORDER_BRIGHT = "#315375"
TEXT = "#edf6ff"
TEXT_SOFT = "#b5c8df"
MUTED = "#7289a4"
CYAN = "#43d9ff"
CYAN_DARK = "#123f56"
PURPLE = "#a38bff"
PINK = "#ff5c85"
UP = "#ff5c72"  # A 股界面约定：上涨为红色
DOWN = "#36d399"
FLAT = "#92a4ba"
AMBER = "#ffc857"
WHITE = "#ffffff"

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_UI_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)
FONT_WATERMARK = ("Microsoft YaHei UI", 24, "bold")

MODE_INFO = {
    "snapshot": ("行情全推", "全市场或自定义标的快照", CYAN),
    "kline": ("K 线", "单标的历史切片", PURPLE),
    "market_event": ("盘口异动", "市场异动事件流", AMBER),
}

UNIVERSE_OPTIONS = {
    "沪深京 A 股 · 全市场": "cn_hsj_stock",
    "沪深 A 股 · 全市场": "cn_hs_stock",
    "上海 A 股 · 全市场": "cn_sh_stock",
    "深圳 A 股 · 全市场": "cn_sz_stock",
    "北交所股票 · 全市场": "cn_bse_stock",
    "科创板股票 · 全市场": "cn_star_stock",
    "上海 B 股 · 全市场": "cn_sh_b_stock",
    "深圳 B 股 · 全市场": "cn_sz_b_stock",
    "沪深指数 · 全市场": "cn_index",
    "沪深基金（ETF/LOF/REIT）· 全市场": "cn_fund",
    "上海基金 · 全市场": "cn_sh_fund",
    "深圳基金 · 全市场": "cn_sz_fund",
    "REIT · 全市场": "cn_reit",
    "上海债券 · 全市场": "cn_sh_bond",
    "深圳债券 · 全市场": "cn_sz_bond",
    "期权 · 全市场": "cn_option",
    "ETF 期权 · 全市场": "cn_etf_option",
    "期权认购 · 全市场": "cn_option_call",
    "期权认沽 · 全市场": "cn_option_put",
    "中金所股指期货 · 当前合约": "cn_cffex_index_futures",
    "中金所国债期货 · 当前合约": "cn_cffex_treasury_futures",
    "中金所期货 · 当前合约": "cn_cffex_futures",
}

TABLE_FALLBACK_COLUMNS = {
    "snapshot": [
        "__kind",
        "code",
        "name",
        "price",
        "change_pct",
        "change_amt",
        "high",
        "low",
        "pre_close",
        "open_price",
        "avg_price",
        "volume",
        "amount",
        "turnover_ratio",
        "volume_ratio",
        "industry_name",
        "__updated",
    ],
    "kline": [
        "__kind",
        "code",
        "date",
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "__updated",
    ],
    "market_event": [
        "__kind",
        "pk_time",
        "pk_name",
        "code",
        "pk_type_name",
        "pk_value",
        "pk_detail",
        "__updated",
    ],
}

TABLE_HEADINGS = {
    "__kind": "推送类型",
    "__updated": "最近更新",
    "code": "代码",
    "name": "名称",
    "price": "最新价",
    "change_pct": "涨跌幅",
    "change_amt": "涨跌额",
    "high": "最高",
    "low": "最低",
    "pre_close": "昨收",
    "open_price": "今开",
    "avg_price": "均价",
    "close": "收盘",
    "volume": "成交量",
    "amount": "成交额",
    "turnover_ratio": "换手率",
    "volume_ratio": "量比",
    "industry_name": "行业",
    "date": "日期",
    "time": "时间",
    "type": "事件类型",
    "type_name": "事件名称",
    "info": "事件说明",
    "pk_time": "时间",
    "pk_name": "股票名称",
    "pk_type_name": "异动类型",
    "pk_value": "关键值",
    "pk_detail": "指标拆解",
}

QUOTE_FIELDS = [
    "code",
    "name",
    "price",
    "high",
    "low",
    "pre_close",
    "open_price",
    "avg_price",
    "volume",
    "amount",
    "change_pct",
    "change_amt",
    "turnover_ratio",
    "amplitude",
    "volume_ratio",
    "bid1_price",
    "bid1_vol",
    "ask1_price",
    "ask1_vol",
    "inner_vol",
    "outer_vol",
    "limit_up_price",
    "limit_down_price",
    "market_value",
    "float_market_value",
    "industry_name",
]

PRICE_FIELDS = {
    "price",
    "open",
    "close",
    "high",
    "low",
    "pre_close",
    "open_price",
    "avg_price",
    "bid1_price",
    "bid2_price",
    "bid3_price",
    "bid4_price",
    "bid5_price",
    "ask1_price",
    "ask2_price",
    "ask3_price",
    "ask4_price",
    "ask5_price",
    "limit_up_price",
    "limit_down_price",
}
PERCENT_FIELDS = {
    "change_pct",
    "turnover_ratio",
    "real_turnover_ratio",
    "amplitude",
    "body_change_pct",
    "change_pct_1min",
    "change_pct_2min",
    "change_pct_3min",
    "change_pct_5min",
    "change_pct_3d",
    "change_pct_5d",
    "change_pct_10d",
    "dividend_yield",
}
RATIO_FIELDS = {"volume_ratio", "dynamic_pe", "static_pe", "ttm_pe", "pb_ratio"}


def safe_number(value: Any) -> float | None:
    """返回有限数字；接口的 null/哨兵值不会进入绘图。"""

    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number == 2147483647:
        return None
    return number


def normalize_d101_code(value: str) -> str:
    """将用户输入转换为 D101 的规范代码。

    D101 的快照通道本身接受变长代码；这里补齐常见的市场前缀，避免
    把小写期货品种、美股代码或八位期权合约误当成普通 A 股代码。
    """

    code = value.strip()
    if not code:
        return ""

    if re.fullmatch(r"\d{6}", code):
        # 兼容传统的六位 A 股输入。
        prefix = "SH" if code.startswith(("5", "6", "9")) else "SZ"
        return prefix + code

    option_match = re.fullmatch(r"(SO|ZO)(\d{8})", code, re.IGNORECASE)
    if option_match:
        return option_match.group(1).upper() + option_match.group(2)

    if re.fullmatch(r"\d{8}", code):
        # 9 开头的八位期权合约属于深圳期权，其余常见合约属于上海期权。
        return ("ZO" if code.startswith("9") else "SO") + code

    cffex_option = re.fullmatch(
        r"(?:IO|HO|MO)\d{4}-[CP]-\d+(?:\.\d+)?",
        code,
        re.IGNORECASE,
    )
    if cffex_option:
        return "CFFEXOPTION|" + cffex_option.group(0).upper()

    if "|" in code:
        exchange, payload = code.split("|", 1)
        exchange = exchange.strip().upper()
        payload = payload.strip()
        if exchange in {"DCE", "SHFE", "CZCE", "INE", "GFEX"}:
            payload = payload.lower()
        elif exchange in {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC"}:
            payload = payload.upper()
        elif exchange == "CFFEXOPTION":
            payload = payload.upper()
        else:
            # HKDL 等市场的代码通常是数字；对未知市场保留可读的规范大写形式。
            payload = payload.upper()
        return f"{exchange}|{payload}"

    # 裸小写的 1~3 位品种名按国内商品期货连续合约处理，例如 jmm。
    # 美股请显式填写 NASDAQ|、NYSE| 或 AMEX|，避免市场歧义。
    if re.fullmatch(r"[a-z]{1,3}(?:\d{2,6})?", code):
        return "DCE|" + code.lower()

    return code.upper()


def is_option_code(code: str) -> bool:
    normalized = code.strip().upper()
    return bool(
        re.fullmatch(r"(?:SO|ZO)\d{8}", normalized)
        or normalized.startswith("CFFEXOPTION|")
    )


def normalize_value(field: str, value: Any, code: str = "") -> float | None:
    """把接口数值转换成适合用户界面显示的值。"""

    number = safe_number(value)
    if number is None:
        return None
    if field in PRICE_FIELDS:
        divisor = 10000.0 if is_option_code(code) else 100.0
        return number / divisor
    if field in PERCENT_FIELDS or field in RATIO_FIELDS:
        return number / 100.0
    return number


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    """保留接口行键，同时生成少量带单位的内部显示值。"""

    code = str(row.get("code") or "")
    result = dict(row)
    for key, value in row.items():
        if key in PRICE_FIELDS or key in PERCENT_FIELDS or key in RATIO_FIELDS:
            result[f"_{key}"] = normalize_value(key, value, code)
    return result


def split_codes(value: str) -> list[str]:
    """把输入框中的代码转换为 D101 支持的规范代码数组。"""

    result: list[str] = []
    for item in re.split(r"[,;\s]+", value.strip()):
        code = normalize_d101_code(item)
        if not code:
            continue
        if code not in result:
            result.append(code)
    return result


def display_time(value: Any = None) -> str:
    if value is None:
        return datetime.now().strftime("%H:%M:%S")
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return str(value)
    if 0 <= raw <= 235959:
        return f"{raw // 10000:02d}:{raw // 100 % 100:02d}:{raw % 100:02d}"
    return str(raw)


def compact_number(value: Any, digits: int = 2) -> str:
    number = safe_number(value)
    if number is None:
        return "—"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.{digits}f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.{digits}f}万"
    return f"{number:,.{digits}f}"


def compact_volume(value: Any) -> str:
    number = safe_number(value)
    if number is None:
        return "—"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.1f}万"
    return f"{number:,.0f}"


def format_price(value: Any) -> str:
    number = safe_number(value)
    return "—" if number is None else f"{number:.2f}"


def format_pct(value: Any) -> str:
    number = safe_number(value)
    if number is None:
        return "—"
    return f"{number:+.2f}%"


def quote_color(value: Any) -> str:
    number = safe_number(value)
    if number is None or number == 0:
        return FLAT
    return UP if number > 0 else DOWN


def build_command(
    mode: str,
    codes: list[str],
    seq: int,
    period: int = 7,
    universe: str = "",
    limit: int = 0,
) -> dict[str, Any]:
    if mode == "kline":
        code = codes[0] if codes else "SZ000001"
        code = code[2:] if len(code) > 6 and code[:2] in {"SH", "SZ", "BJ"} else code
        return {
            "type": "kline",
            "seq": seq,
            "enable": 1,
            "code": code,
            "period": period,
            "fq": 18,
            "count": 120,
        }
    if mode == "market_event":
        return {
            "type": "market_event",
            "seq": seq,
            "mode": 1,
            "count": 100,
            "enable": 1,
        }
    command: dict[str, Any] = {
        "type": "snapshot",
        "seq": seq,
        "enable": 1,
        "fields": QUOTE_FIELDS,
    }
    if universe:
        command["universe"] = universe
        command["limit"] = max(0, min(int(limit), 65535))
    else:
        command["codes"] = codes or ["SZ000001", "SH600000"]
    return command


def build_market_event_history_command(
    seq: int,
    cursor: dict[str, int],
    count: int = -100,
) -> dict[str, Any]:
    """构造 market_event 的上一页请求；cursor 必须来自当前列表最末一行。"""

    return {
        "type": "market_event",
        "seq": seq,
        "mode": 2,
        "count": -abs(int(count)) or -100,
        "cursor": {
            "time": int(cursor["time"]),
            "seq": int(cursor["seq"]),
        },
        "enable": 1,
    }


@dataclass
class Quote:
    code: str
    data: dict[str, Any] = field(default_factory=dict)
    history: deque[float] = field(default_factory=lambda: deque(maxlen=160))
    updates: int = 0
    received_at: float = field(default_factory=time.time)

    @property
    def display(self) -> dict[str, Any]:
        return normalized_row(self.data)


class D101Stream:
    """后台 WebSocket 线程；不触碰 Tkinter 对象。"""

    def __init__(
        self,
        url: str,
        command: dict[str, Any] | list[dict[str, Any]],
        on_state: Callable[[str, str], None],
        on_message: Callable[[str], None],
    ) -> None:
        self.url = url
        self.command = command
        self.on_state = on_state
        self.on_message = on_message
        self.stop_event = threading.Event()
        self.ws: Any = None
        self.ws_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="d101-gui-ws", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.ws_lock:
            current = self.ws
        if current is not None:
            try:
                current.close()
            except Exception:
                pass
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=3.0)

    def send(self, payload: dict[str, Any] | list[dict[str, Any]]) -> bool:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.ws_lock:
            current = self.ws
            if current is None:
                return False
            try:
                current.send(text)
                return True
            except Exception as exc:
                self.on_state("error", f"发送失败：{exc}")
                return False

    def _run(self) -> None:
        if websocket is None:
            self.on_state("error", f"缺少 websocket-client。\n{websocket_install_hint()}")
            return

        retry_delay = 1.0
        while not self.stop_event.is_set():
            try:
                self._run_once()
                retry_delay = 1.0
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.on_state("error", f"连接异常：{exc}")
            finally:
                with self.ws_lock:
                    self.ws = None
            if self.stop_event.is_set():
                break
            self.on_state("retry", f"连接已断开，{retry_delay:.0f} 秒后重试")
            self.stop_event.wait(retry_delay)
            retry_delay = min(retry_delay * 2.0, 8.0)

    def _run_once(self) -> None:
        assert websocket is not None
        self.on_state("connecting", "正在建立 d101 连接…")
        current = websocket.create_connection(
            self.url,
            timeout=8,
            enable_multithread=True,
            http_proxy_host=None,
            http_proxy_port=None,
        )
        current.settimeout(1.0)
        with self.ws_lock:
            self.ws = current
        self.on_state("connected", "连接已建立，正在等待数据…")
        current.send(json.dumps(self.command, ensure_ascii=False, separators=(",", ":")))
        self.on_state("subscribed", "订阅指令已发送")
        try:
            while not self.stop_event.is_set():
                try:
                    raw = current.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    return
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                self.on_message(str(raw))
        finally:
            try:
                commands = self.command if isinstance(self.command, list) else [self.command]
                disable_payload: dict[str, Any] | list[dict[str, Any]]
                disable_commands = [
                    {"type": item.get("type", "snapshot"), "enable": 0}
                    for item in commands
                ]
                disable_payload = disable_commands[0] if len(disable_commands) == 1 else disable_commands
                current.send(
                    json.dumps(
                        disable_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            except Exception:
                pass
            try:
                current.close()
            except Exception:
                pass


class D101Gui:
    def __init__(self, root: tk.Tk, url: str) -> None:
        self.root = root
        self.root.title("d101 · 用户侧实时全推控制台")
        self.root.geometry("1600x960")
        self.root.minsize(1180, 700)
        self.root.configure(bg=BG)

        self.endpoint_var = tk.StringVar(value=url)
        self.codes_var = tk.StringVar(value="SZ000001,SH600000,SZ300750")
        self.universe_var = tk.StringVar(value="沪深京 A 股 · 全市场")
        self.subscription_mode_var = tk.StringVar(value="market")
        self.limit_var = tk.StringVar(value="0")
        self.period_var = tk.StringVar(value="日 K")
        self.mode = "snapshot"
        self.periods = {"1 分钟": 1, "5 分钟": 2, "15 分钟": 3, "30 分钟": 4, "60 分钟": 5, "日 K": 7, "周 K": 8, "月 K": 9}

        # 三个 TAB 各自保存自己的推送表，不混合、不覆盖。
        self.rows_by_mode: dict[str, dict[str, dict[str, Any]]] = {
            "snapshot": {},
            "kline": {},
            "market_event": {},
        }
        self.tree_iids: dict[str, dict[str, str]] = {"snapshot": {}, "kline": {}, "market_event": {}}
        self.tree_key_by_iid: dict[str, str] = {}
        self.table_columns: dict[str, tuple[str, ...]] = {
            mode: tuple(columns) for mode, columns in TABLE_FALLBACK_COLUMNS.items()
        }
        self.table_ordinal = 0
        self._table_refresh_pending = False
        self.market_event_cursor: dict[str, int] | None = None
        self.market_event_loading = False
        self.market_event_has_more = True
        self.market_event_request_seq = 1000
        self.market_event_history_pages = 0
        self.market_event_scroll_at_bottom = False

        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._configure_widgets()

        self.queue: queue.Queue[tuple[int, str, Any]] = queue.Queue()
        self.session_id = 0
        self.stream: D101Stream | None = None
        self.connected = False
        self.connecting = False
        self.connection_text = "未连接"
        self.quotes: dict[str, Quote] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=80)
        self.kline_rows: list[dict[str, Any]] = []
        self.selected_code = ""
        self.message_count = 0
        self.row_count = 0
        self.error_count = 0
        self.last_message_at = 0.0
        self.last_draw_at = 0.0
        self.hover_target = ""
        self.layout: dict[str, tuple[float, float, float, float]] = {}

        self.canvas.bind("<Configure>", lambda _event: self.schedule_draw())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._set_hover(""))
        self.root.bind("<Return>", lambda _event: self.toggle_connection())
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda _event: self.leave_fullscreen())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self.drain_queue)
        self.root.after(1000, self._tick)
        self._add_event("SYS", "准备就绪，选择市场池或自定义代码后点击连接", MUTED)
        self.schedule_draw()

        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

    # ── Tk 控件和布局 ────────────────────────────────────────────────────

    def _configure_widgets(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.endpoint_entry = tk.Entry(
            self.root,
            textvariable=self.endpoint_var,
            bg=INPUT,
            fg=TEXT,
            insertbackground=CYAN,
            selectbackground=CYAN_DARK,
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=CYAN,
            font=FONT_MONO_SMALL,
        )
        self.codes_entry = tk.Entry(
            self.root,
            textvariable=self.codes_var,
            bg=INPUT,
            fg=TEXT,
            insertbackground=CYAN,
            selectbackground=CYAN_DARK,
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=CYAN,
            font=FONT_MONO_SMALL,
        )
        self.universe_box = ttk.Combobox(
            self.root,
            textvariable=self.universe_var,
            values=list(UNIVERSE_OPTIONS),
            state="readonly",
            style="D101.TCombobox",
            width=30,
        )
        self.period_box = ttk.Combobox(
            self.root,
            textvariable=self.period_var,
            values=list(self.periods),
            state="readonly",
            style="D101.TCombobox",
            width=8,
        )
        self.limit_entry = tk.Entry(
            self.root,
            textvariable=self.limit_var,
            bg=INPUT,
            fg=TEXT,
            insertbackground=CYAN,
            selectbackground=CYAN_DARK,
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=CYAN,
            font=FONT_MONO_SMALL,
            justify="center",
        )
        style.configure(
            "D101.TCombobox",
            fieldbackground=INPUT,
            background=INPUT,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowcolor=CYAN,
            padding=(6, 4),
            font=FONT_MONO_SMALL,
        )
        style.map(
            "D101.TCombobox",
            fieldbackground=[("readonly", INPUT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", CYAN_DARK)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "D101.Treeview",
            background=SURFACE_3,
            fieldbackground=SURFACE_3,
            foreground=TEXT_SOFT,
            borderwidth=0,
            relief="flat",
            rowheight=29,
            font=FONT_MONO_SMALL,
        )
        style.configure(
            "D101.Treeview.Heading",
            background=SURFACE_2,
            foreground=CYAN,
            borderwidth=0,
            relief="flat",
            padding=(8, 7),
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map(
            "D101.Treeview",
            background=[("selected", "#1d4564")],
            foreground=[("selected", WHITE)],
        )
        style.configure(
            "D101.Vertical.TScrollbar",
            background=SURFACE_2,
            troughcolor=BG_2,
            bordercolor=BG_2,
            arrowcolor=CYAN,
        )
        style.configure(
            "D101.Horizontal.TScrollbar",
            background=SURFACE_2,
            troughcolor=BG_2,
            bordercolor=BG_2,
            arrowcolor=CYAN,
        )
        self.data_tree = ttk.Treeview(
            self.root,
            columns=self.table_columns[self.mode],
            show="headings",
            selectmode="browse",
            style="D101.Treeview",
        )
        self.vertical_scroll = ttk.Scrollbar(
            self.root,
            orient="vertical",
            command=self._on_vertical_scroll,
            style="D101.Vertical.TScrollbar",
        )
        self.horizontal_scroll = ttk.Scrollbar(
            self.root,
            orient="horizontal",
            command=self.data_tree.xview,
            style="D101.Horizontal.TScrollbar",
        )
        self.data_tree.configure(
            yscrollcommand=self._on_tree_yview,
            xscrollcommand=self.horizontal_scroll.set,
        )
        self.data_tree.tag_configure("even", background="#0d1828")
        self.data_tree.tag_configure("odd", background="#101e31")
        self.data_tree.tag_configure("even_red", background="#0d1828", foreground=UP)
        self.data_tree.tag_configure("odd_red", background="#101e31", foreground=UP)
        self.data_tree.tag_configure("even_green", background="#0d1828", foreground=DOWN)
        self.data_tree.tag_configure("odd_green", background="#101e31", foreground=DOWN)
        self.data_tree.tag_configure("even_unknown", background="#0d1828", foreground=TEXT_SOFT)
        self.data_tree.tag_configure("odd_unknown", background="#101e31", foreground=TEXT_SOFT)
        self.data_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.universe_box.bind("<<ComboboxSelected>>", self._on_universe_selected)
        self._sync_subscription_controls()

    def _place_widgets(self, width: int, toolbar_y: int) -> None:
        self._sync_subscription_controls()
        endpoint_x = 98
        endpoint_w = min(360, max(270, int(width * 0.27)))
        self.endpoint_entry.place(x=endpoint_x, y=toolbar_y + 27, width=endpoint_w, height=28)

        toggle_x = 98
        toggle_w = 178
        toggle_y = toolbar_y + 72
        self.layout["subscription_market"] = (toggle_x, toggle_y, toggle_x + 86, toggle_y + 31)
        self.layout["subscription_codes"] = (toggle_x + 91, toggle_y, toggle_x + toggle_w, toggle_y + 31)

        source_x = toggle_x + toggle_w + 18
        source_w = min(256, max(210, int(width * 0.20)))
        codes_x = source_x + source_w + 34
        codes_w = min(280, max(200, int(width * 0.20)))
        using_universe = self.mode == "snapshot" and self.subscription_mode_var.get() == "market"
        show_market = using_universe
        show_codes = self.mode != "market_event" and not using_universe

        if show_market:
            self.universe_box.place(x=source_x, y=toolbar_y + 75, width=source_w, height=28)
            input_x = codes_x
        else:
            self.universe_box.place_forget()
            input_x = source_x

        if show_codes:
            self.codes_entry.place(x=input_x, y=toolbar_y + 75, width=codes_w, height=28)
            period_x = input_x + codes_w + 56
        else:
            self.codes_entry.place_forget()
            period_x = source_x + source_w + 44 if show_market else source_x + 44
        self.period_box.place(x=period_x, y=toolbar_y + 75, width=100, height=28)

        limit_x = period_x + 142
        self.limit_entry.place(x=limit_x, y=toolbar_y + 75, width=72, height=28)

        self.layout["connect"] = (max(endpoint_x + endpoint_w + 24, width - 178), toolbar_y + 23, width - 96, toolbar_y + 58)
        self.layout["clear"] = (width - 86, toolbar_y + 23, width - 30, toolbar_y + 58)

    def _sync_subscription_controls(self) -> None:
        """让 UI 状态直接表达 market/code 二选一关系。"""

        is_snapshot = self.mode == "snapshot"
        using_universe = is_snapshot and self.subscription_mode_var.get() == "market"
        self.universe_box.configure(state="readonly" if using_universe else "disabled")
        self.codes_entry.configure(
            state="normal" if not is_snapshot or not using_universe else "disabled",
            disabledforeground="#536a83",
        )
        self.limit_entry.configure(
            state="normal" if using_universe else "disabled",
            disabledforeground="#536a83",
        )

    def _on_universe_selected(self, _event: tk.Event) -> None:
        was_active = self.connected or self.connecting
        self.subscription_mode_var.set("market")
        self._sync_subscription_controls()
        self._add_event("SYS", "已选择市场池：代码输入和 limit 规则已停用", CYAN)
        if was_active:
            self.disconnect(silent=True)
            self._add_event("SYS", "市场池已改变，请点击连接使新市场生效", AMBER)
        self.schedule_draw()

    def _set_subscription_mode(self, mode: str) -> None:
        if mode not in {"market", "codes"} or mode == self.subscription_mode_var.get():
            return
        was_active = self.connected or self.connecting
        self.subscription_mode_var.set(mode)
        self._sync_subscription_controls()
        if mode == "market":
            self._add_event("SYS", "订阅模式：市场池", CYAN)
        else:
            self._add_event("SYS", "订阅模式：自定义代码", PURPLE)
        if was_active:
            self.disconnect(silent=True)
            self._add_event("SYS", "订阅方式已改变，请确认参数后点击连接", AMBER)
        self.schedule_draw()

    def _place_table(self, rect: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = rect
        tree_x = int(x1 + 14)
        tree_y = int(y1 + 50)
        tree_w = max(320, int(x2 - x1 - 32))
        tree_h = max(120, int(y2 - y1 - 70))
        scroll_w = 16
        self.data_tree.place(x=tree_x, y=tree_y, width=tree_w - scroll_w, height=tree_h)
        self.vertical_scroll.place(x=x2 - 17, y=tree_y, width=16, height=tree_h)
        self.horizontal_scroll.place(x=tree_x, y=y2 - 19, width=tree_w - scroll_w, height=16)

    def _on_tree_yview(self, first: str, last: str) -> None:
        self.vertical_scroll.set(first, last)
        if self.mode != "market_event":
            return
        at_bottom = float(last) >= 0.995
        if at_bottom and not self.market_event_scroll_at_bottom:
            self.market_event_scroll_at_bottom = True
            self.root.after_idle(self.load_previous_market_event)
        elif not at_bottom:
            self.market_event_scroll_at_bottom = False

    def _on_vertical_scroll(self, *args: str) -> None:
        self.data_tree.yview(*args)

    # ── 网络和数据 ──────────────────────────────────────────────────────

    def _enqueue_state(self, session_id: int, state: str, text: str) -> None:
        self.queue.put((session_id, "state", (state, text)))

    def _enqueue_message(self, session_id: int, raw: str) -> None:
        self.queue.put((session_id, "message", raw))

    def toggle_connection(self) -> None:
        if self.connected or self.connecting:
            self.disconnect()
        else:
            self.connect()

    def connect(self) -> None:
        if websocket is None:
            messagebox.showerror(
                "缺少依赖",
                f"此面板需要 websocket-client。\n\n{websocket_install_hint()}",
                parent=self.root,
            )
            return
        url = self.endpoint_var.get().strip()
        if not url.startswith(("ws://", "wss://")):
            self._add_event("ERR", "连接地址必须以 ws:// 或 wss:// 开头", PINK)
            self.connection_text = "地址无效"
            self.schedule_draw()
            return
        codes = split_codes(self.codes_var.get())
        use_market = self.mode == "snapshot" and self.subscription_mode_var.get() == "market"
        universe = UNIVERSE_OPTIONS.get(self.universe_var.get(), "") if use_market else ""
        if self.mode == "snapshot" and not universe and not codes:
            self._add_event("ERR", "选择全市场，或至少填写一个自定义代码", PINK)
            return
        if self.mode == "kline" and not codes:
            self._add_event("ERR", "至少填写一个标的代码", PINK)
            return

        limit = 0
        if universe:
            try:
                limit = max(0, min(int(self.limit_var.get().strip() or "0"), 65535))
            except ValueError:
                self._add_event("ERR", "limit 必须是 0 到 65535 的整数", PINK)
                return

        self.disconnect(silent=True)
        self.session_id += 1
        sid = self.session_id
        if self.mode == "market_event":
            self.market_event_cursor = None
            self.market_event_loading = False
            self.market_event_has_more = True
            self.market_event_history_pages = 0
            self.market_event_scroll_at_bottom = False
            self.market_event_request_seq = max(1000, (sid * 1000) % 60000)
        command = build_command(
            self.mode,
            codes,
            sid,
            self.periods.get(self.period_var.get(), 7),
            universe=universe,
            limit=limit,
        )
        self.connected = False
        self.connecting = True
        self.connection_text = "连接中"
        self._add_event("SYS", f"正在连接 {url}", CYAN)
        self.stream = D101Stream(
            url,
            command,
            lambda state, text, sid=sid: self._enqueue_state(sid, state, text),
            lambda raw, sid=sid: self._enqueue_message(sid, raw),
        )
        self.stream.start()
        self.schedule_draw()

    def disconnect(self, silent: bool = False) -> None:
        self.session_id += 1
        stream = self.stream
        self.stream = None
        self.connected = False
        self.connecting = False
        self.connection_text = "已断开"
        self.market_event_loading = False
        if stream is not None:
            stream.stop()
        if not silent:
            self._add_event("SYS", "已断开 d101 数据流", MUTED)
        self.schedule_draw()

    def change_mode(self, mode: str) -> None:
        if mode not in MODE_INFO or mode == self.mode:
            return
        was_active = self.connected or self.connecting
        if was_active:
            self.disconnect(silent=True)
        self.mode = mode
        self.selected_code = ""
        self._add_event("MODE", f"切换到：{MODE_INFO[mode][0]}", MODE_INFO[mode][2])
        if was_active:
            self.connect()
        self.schedule_draw()

    def _next_market_event_request_seq(self) -> int:
        self.market_event_request_seq = self.market_event_request_seq % 65535 + 1
        return self.market_event_request_seq

    def load_previous_market_event(self) -> None:
        """滚动到列表底部或点击按钮时，向服务端请求更早的一页。"""

        if self.mode != "market_event" or self.market_event_loading or not self.market_event_has_more:
            return
        if not self.connected or self.stream is None:
            self._add_event("SYS", "先连接盘口异动数据流", MUTED)
            return
        if self.market_event_cursor is None:
            self._add_event("SYS", "当前页还没有完整游标，等待盘口异动数据", MUTED)
            return
        command = build_market_event_history_command(
            self._next_market_event_request_seq(),
            self.market_event_cursor,
            count=-100,
        )
        if self.stream.send(command):
            self.market_event_loading = True
            self.market_event_history_pages += 1
            self._add_event("HIST", f"正在加载更早异动 · 游标 {display_time(self.market_event_cursor['time'])}", AMBER)
            self.schedule_draw()

    def drain_queue(self) -> None:
        changed = False
        for _ in range(120):
            try:
                sid, kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if sid != self.session_id:
                continue
            if kind == "state":
                state, text = payload
                self._handle_state(state, text)
                changed = True
            elif kind == "message":
                self._handle_message(str(payload))
                changed = True
        if changed:
            self.schedule_draw()
        self.root.after(80, self.drain_queue)

    def _handle_state(self, state: str, text: str) -> None:
        if state == "connecting":
            self.connecting = True
            self.connected = False
            self.connection_text = "连接中"
        elif state in {"connected", "subscribed"}:
            self.connecting = False
            self.connected = True
            self.connection_text = "在线"
        elif state == "retry":
            self.connecting = True
            self.connected = False
            self.connection_text = "重试中"
        elif state == "error":
            self.error_count += 1
            self.connection_text = "异常"
            self._add_event("ERR", text, PINK)
        else:
            self.connection_text = text
        if state not in {"connected", "subscribed"}:
            self._add_event("NET", text, CYAN if state == "connecting" else MUTED)

    def _handle_message(self, raw: str) -> None:
        self.message_count += 1
        self.last_message_at = time.time()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.error_count += 1
            self._add_event("ERR", f"收到无法解析的 JSON：{exc}", PINK)
            return
        if not isinstance(message, dict):
            return
        items = message.get("list", [])
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "info":
                message = self._neutral_message(item.get("msg"))
                self._add_event("INFO", message, CYAN)
            elif item_type == "error":
                self.error_count += 1
                message = self._neutral_message(item.get("msg"))
                self._add_event("ERR", message, PINK)
                if self.mode == "market_event":
                    self.market_event_loading = False
            elif item_type == "snapshot":
                self._handle_snapshot(item.get("data", []))
            elif item_type == "kline":
                self._handle_kline(item)
            elif item_type == "market_event":
                self._handle_market_event(item)
            elif item_type == "diag":
                self._add_event("DIAG", self._neutral_message(item.get("msg")), MUTED)

    @staticmethod
    def _neutral_message(value: Any) -> str:
        """服务端消息只做诊断展示，不将其当成业务状态机。"""

        if value is None:
            return "收到服务通知"
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        return text[:120] if text else "收到服务通知"

    def _handle_snapshot(self, rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("code")
            if not isinstance(code, str) or not code:
                continue
            code = code.upper()
            quote = self.quotes.setdefault(code, Quote(code))
            old_price = quote.display.get("_price")
            quote.data.update(row)  # 增量行：缺失键保留，显式 null 保留为无效
            current_price = quote.display.get("_price")
            if current_price is not None and current_price != old_price:
                quote.history.append(current_price)
            quote.updates += 1
            quote.received_at = time.time()
            table_row = dict(row)
            table_row["code"] = code
            self._upsert_table_row("snapshot", code, table_row, merge=True)
            self.row_count += 1
            if not self.selected_code:
                self.selected_code = code

    def _handle_kline(self, payload: Any) -> None:
        outer_code = ""
        if isinstance(payload, dict):
            rows = payload.get("data", [])
            outer_code = str(payload.get("code") or "")
        else:
            rows = payload
        if not isinstance(rows, list):
            return
        clean: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            item = dict(row)
            code = str(item.get("code") or outer_code or self._first_code() or "")
            if code:
                item["code"] = code
            for key in ("open", "high", "low", "close"):
                item[f"_{key}"] = normalize_value("price", item.get(key), code)
            clean.append(item)
            raw_item = dict(row)
            if code and not raw_item.get("code"):
                raw_item["code"] = code
            identity = raw_item.get("date", raw_item.get("time", index))
            self._upsert_table_row("kline", f"{code}:{identity}", raw_item)
        if clean:
            self.kline_rows = clean[-160:]
            self.row_count += len(clean)

    def _handle_market_event(self, payload: Any) -> None:
        outer_code = ""
        if isinstance(payload, dict):
            rows = payload.get("data", [])
            outer_code = str(payload.get("code") or "")
        else:
            rows = payload
        if not isinstance(rows, list):
            return
        history_page = self.market_event_loading
        valid_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or outer_code or "—").upper()
            event_name = str(row.get("type_name") or "异动事件")
            info = str(row.get("info") or "").replace("\r", " ").replace("\n", " ").strip()
            event_time = self._market_event_int(row.get("time"))
            event_seq = self._market_event_int(row.get("seq"))
            valid_cursor = event_time > 0 and event_seq > 0
            if valid_cursor:
                valid_rows.append(row)
            key = self._market_event_key(row, code)
            quote = self.quotes.get(code)
            cached_name = quote.data.get("name") if quote else None
            table_row = {
                "pk_time": display_time(event_time) if event_time else "—",
                "pk_name": str(cached_name or row.get("name") or "—"),
                "code": code,
                "pk_type_name": event_name,
                "pk_value": self._market_event_value_text(row),
                "pk_detail": self._market_event_detail_text(row),
                "__market_event_time": event_time,
                "__market_event_seq": event_seq,
                "__market_event_color": row.get("type_color"),
            }
            self._upsert_table_row("market_event", key, table_row)
            message = f"{code}  {event_name}"
            if info:
                message += f"  ·  {info[:56]}"
            self._add_event("EVENT", message, DOWN if row.get("type_color") == 1 else UP)
            self.row_count += 1
        if valid_rows and (self.market_event_cursor is None or history_page):
            last = valid_rows[-1]
            self.market_event_cursor = {
                "time": self._market_event_int(last.get("time")),
                "seq": self._market_event_int(last.get("seq")),
            }
        if history_page:
            self.market_event_loading = False
        if not rows and history_page:
            self.market_event_loading = False
            self.market_event_has_more = False
            self._add_event("HIST", "已经加载到当前游标之前的最早记录", MUTED)

    @staticmethod
    def _market_event_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _market_event_key(self, row: dict[str, Any], code: str) -> str:
        event_time = self._market_event_int(row.get("time"))
        event_seq = self._market_event_int(row.get("seq"))
        if event_time > 0 and event_seq > 0:
            return f"{event_time}:{event_seq}:{code}"
        try:
            fingerprint = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            fingerprint = repr(row)
        return f"fallback:{code}:{fingerprint}"

    @staticmethod
    def _market_event_numbers(info: Any) -> list[float]:
        text = str(info or "")
        values: list[float] = []
        for token in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text):
            try:
                values.append(float(token))
            except ValueError:
                pass
        return values

    @staticmethod
    def _market_event_price(value: float) -> str:
        return f"{value:.2f}"

    @staticmethod
    def _market_event_percent(value: float) -> str:
        return f"{value * 100:+.2f}%"

    @staticmethod
    def _market_event_lots(value: float) -> str:
        if abs(value) >= 10000:
            return f"{value / 10000:.2f}万手"
        return f"{value:,.0f}手"

    def _market_event_value_text(self, row: dict[str, Any]) -> str:
        name = str(row.get("type_name") or "")
        values = self._market_event_numbers(row.get("info"))
        event_type = self._market_event_int(row.get("type"))
        if not values:
            return "—"
        if event_type in {4, 8} or "大笔买" in name or "大笔卖" in name:
            return self._market_event_lots(values[1] if len(values) > 1 else values[0])
        if event_type in {64, 128} or "打开" in name:
            return self._market_event_price(values[1] if len(values) > 1 else values[0])
        if event_type in {32, 16} or "封" in name:
            return self._market_event_price(values[0])
        if event_type in {8193, 8194}:
            return self._market_event_percent(values[2] if len(values) > 2 else values[0])
        if "缺口" in name or "涨停" in name or "跌停" in name:
            return self._market_event_price(values[0])
        return self._market_event_percent(values[0])

    def _market_event_detail_text(self, row: dict[str, Any]) -> str:
        name = str(row.get("type_name") or "")
        values = self._market_event_numbers(row.get("info"))
        event_type = self._market_event_int(row.get("type"))
        if not values:
            return "—"
        if event_type in {4, 8} or "大笔买" in name or "大笔卖" in name:
            detail = [f"价 {self._market_event_price(values[0])}"]
            if len(values) > 1:
                detail.append(f"量 {self._market_event_lots(values[1])}")
            if len(values) > 3:
                detail.append(f"额 {compact_number(values[3])}")
            return " · ".join(detail)
        if event_type in {64, 128} or "打开" in name:
            detail = [f"量 {self._market_event_lots(values[0])}"]
            if len(values) > 1:
                detail.append(f"价 {self._market_event_price(values[1])}")
            if len(values) > 2:
                detail.append(f"涨跌 {self._market_event_percent(values[2])}")
            if len(values) > 3:
                detail.append(f"额 {compact_number(values[3])}")
            return " · ".join(detail)
        if event_type in {32, 16} or "封" in name:
            detail = [f"价 {self._market_event_price(values[0])}"]
            if len(values) > 1:
                detail.append(f"涨跌 {self._market_event_percent(values[1])}")
            return " · ".join(detail)
        if event_type in {8193, 8194}:
            detail = [f"量 {self._market_event_lots(values[0])}"]
            if len(values) > 1:
                detail.append(f"价 {self._market_event_price(values[1])}")
            if len(values) > 2:
                detail.append(f"涨跌 {self._market_event_percent(values[2])}")
            return " · ".join(detail)
        if len(values) > 1:
            return f"涨跌 {self._market_event_percent(values[0])} · 价 {self._market_event_price(values[1])}"
        return f"指标 {self._market_event_percent(values[0])}"

    def _upsert_table_row(
        self,
        mode: str,
        key: str,
        data: dict[str, Any],
        merge: bool = False,
    ) -> None:
        rows = self.rows_by_mode[mode]
        current = rows.get(key) if merge else None
        if current is None:
            current = {}
            rows[key] = current
        current.update(data)
        current["__kind"] = mode
        current["__updated"] = time.time()
        self.table_ordinal += 1
        current["__ordinal"] = self.table_ordinal
        if mode == "market_event" and len(rows) > 5000:
            oldest_key = min(
                rows,
                key=lambda item: (
                    rows[item].get("__market_event_time", 0),
                    rows[item].get("__market_event_seq", 0),
                ),
            )
            if oldest_key != key:
                rows.pop(oldest_key, None)

    def _first_code(self) -> str:
        codes = split_codes(self.codes_var.get())
        return codes[0] if codes else ""

    # ── 绘制 ─────────────────────────────────────────────────────────────

    def schedule_draw(self) -> None:
        if getattr(self, "_draw_pending", False):
            return
        self._draw_pending = True
        self.root.after_idle(self._draw)

    def _draw(self) -> None:
        self._draw_pending = False
        canvas = self.canvas
        width = max(canvas.winfo_width(), 1180)
        height = max(canvas.winfo_height(), 700)
        canvas.delete("all")
        self.layout = {}
        self._draw_background(width, height)
        self._draw_header(width)
        toolbar_y = 78
        self._place_widgets(width, toolbar_y)
        self._draw_toolbar(width, toolbar_y)
        tabs_y = toolbar_y + 122
        self._draw_tabs(width, tabs_y)
        self._draw_stats(width, tabs_y + 58)

        table_y = tabs_y + 154
        table = (28, table_y, width - 28, height - 24)
        self.layout["table"] = table
        self._draw_table_shell(table)
        self._place_table(table)
        self._refresh_table()
        self.last_draw_at = time.time()

    def _draw_background(self, width: int, height: int) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, width, height, fill=BG, outline="")
        for x in range(0, width, 72):
            c.create_line(x, 0, x, height, fill="#0c1726", width=1)
        for y in range(0, height, 72):
            c.create_line(0, y, width, y, fill="#0c1726", width=1)
        c.create_oval(width - 500, -240, width + 130, 370, fill="#0b1e35", outline="")
        c.create_oval(-280, height - 220, 300, height + 340, fill="#0b182b", outline="")
        c.create_line(28, 0, width - 28, 0, fill=CYAN, width=2)

    def _draw_header(self, width: int) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, width, 64, fill="#09111e", outline="")
        c.create_line(28, 63, width - 28, 63, fill="#1c3a56", width=1)
        # 左侧紧凑产品标识
        c.create_rectangle(30, 23, 35, 51, fill=CYAN, outline="")
        c.create_rectangle(40, 30, 45, 51, fill=PURPLE, outline="")
        c.create_rectangle(50, 37, 55, 51, fill=PINK, outline="")
        c.create_text(72, 34, text="达塔接口  ·  d101", anchor="w", fill=AMBER, font=("Microsoft YaHei UI", 18, "bold"))
        c.create_text(width - 244, 11, text="d101 · data interface", anchor="e", fill="#17304a", font=FONT_MONO_SMALL)

        status_color = CYAN if self.connected else (AMBER if self.connecting else MUTED)
        status_text = "●  " + self.connection_text.upper()
        self._pill(width - 224, 24, width - 32, 55, status_text, status_color, status_color == CYAN)
        c.create_text(width - 32, 57, text="F11 全屏  ·  ESC 退出全屏", anchor="e", fill="#58728f", font=("Microsoft YaHei UI", 8))

    def _draw_toolbar(self, width: int, y: int) -> None:
        self._panel((28, y, width - 28, y + 106), accent=CYAN)
        c = self.canvas
        c.create_text(38, y + 12, text="WEBSOCKET 端点", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        endpoint_w = min(360, max(270, int(width * 0.27)))
        c.create_text(98 + endpoint_w + 20, y + 12, text="连接后只保持当前 TAB 的一种订阅", anchor="w", fill="#58728f", font=("Microsoft YaHei UI", 8))
        self._button(self.layout.get("connect", (width - 178, y + 23, width - 96, y + 58)), "断开" if self.connected or self.connecting else "连接", CYAN if not self.connected else PINK, "connect")
        self._button(self.layout.get("clear", (width - 86, y + 23, width - 30, y + 58)), "清空", BORDER_BRIGHT, "clear")

        toggle_x = 98
        toggle_w = 178
        source_x = toggle_x + toggle_w + 18
        source_w = min(256, max(210, int(width * 0.20)))
        codes_x = source_x + source_w + 34
        codes_w = min(280, max(200, int(width * 0.20)))
        using_universe = self.mode == "snapshot" and self.subscription_mode_var.get() == "market"
        show_market = using_universe
        show_codes = self.mode != "market_event" and not using_universe
        input_x = codes_x if show_market else source_x
        period_x = input_x + codes_w + 56 if show_codes else source_x + source_w + 44 if show_market else source_x + 44
        limit_x = period_x + 142
        c.create_text(38, y + 87, text="订阅方式", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        self._button(
            self.layout.get("subscription_market", (toggle_x, y + 72, toggle_x + 86, y + 103)),
            "市场池",
            CYAN if using_universe else BORDER_BRIGHT,
            "subscription_market",
            filled=using_universe,
        )
        self._button(
            self.layout.get("subscription_codes", (toggle_x + 91, y + 72, toggle_x + toggle_w, y + 103)),
            "自定义代码",
            PURPLE if not using_universe else BORDER_BRIGHT,
            "subscription_codes",
            filled=not using_universe,
        )
        if show_market:
            c.create_text(source_x, y + 61, text="市场池（市场模式）", anchor="w", fill=CYAN, font=FONT_MONO_SMALL)
        if show_codes:
            c.create_text(input_x, y + 61, text="代码（支持交易所|代码）", anchor="w", fill=PURPLE, font=FONT_MONO_SMALL)
        c.create_text(period_x, y + 61, text="K 线周期（K 线 TAB）", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        c.create_text(limit_x, y + 61, text="limit（市场池）", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        if self.mode == "snapshot":
            selection_text = "当前模式：市场池 · 代码输入已禁用" if using_universe else "当前模式：自定义代码 · 市场池已禁用"
        else:
            selection_text = "当前 TAB 使用代码：市场池设置仅对行情全推生效"
        c.create_text(width - 31, y + 85, text=selection_text, anchor="e", fill=CYAN if using_universe else TEXT_SOFT, font=("Microsoft YaHei UI", 8))

    def _draw_tabs(self, width: int, y: int) -> None:
        self._panel((28, y, width - 28, y + 46), accent=MODE_INFO[self.mode][2])
        c = self.canvas
        c.create_text(42, y + 23, text="数据 TAB", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        tab_x = 128
        tab_w = 148
        for key in ("snapshot", "kline", "market_event"):
            rect = (tab_x, y + 8, tab_x + tab_w, y + 38)
            self.layout[f"tab_{key}"] = rect
            active = key == self.mode
            color = MODE_INFO[key][2]
            self._button(rect, MODE_INFO[key][0], color if active else BORDER_BRIGHT, f"tab_{key}", filled=active)
            tab_x += tab_w + 10
        c.create_text(width - 42, y + 23, text=MODE_INFO[self.mode][1], anchor="e", fill=TEXT_SOFT, font=FONT_UI)

    def _draw_stats(self, width: int, y: int) -> None:
        pad = 28
        gap = 12
        card_w = (width - pad * 2 - gap * 4) / 5
        current_rows = len(self.rows_by_mode[self.mode])
        cards = [
            ("当前 TAB 行数", f"{current_rows:,}", MODE_INFO[self.mode][2]),
            ("累计推送行", f"{self.row_count:,}", PURPLE),
            ("消息帧", f"{self.message_count:,}", AMBER),
            ("订阅范围", self._subscription_text(), CYAN),
            ("最近消息", self._age_text(), DOWN),
        ]
        for index, (title, value, accent) in enumerate(cards):
            x1 = pad + index * (card_w + gap)
            rect = (x1, y, x1 + card_w, y + 84)
            self._panel(rect, accent=accent)
            c = self.canvas
            c.create_text(x1 + 16, y + 17, text=title.upper(), anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
            value_font = ("Segoe UI", 16 if len(value) > 9 else 21, "bold")
            c.create_text(x1 + 16, y + 52, text=value, anchor="w", fill=TEXT, font=value_font)
            c.create_rectangle(x1 + card_w - 18, y + 16, x1 + card_w - 14, y + 68, fill=accent, outline="")

    def _draw_table_shell(self, rect: tuple[float, float, float, float]) -> None:
        accent = MODE_INFO[self.mode][2]
        self._panel(rect, accent=accent)
        x1, y1, x2, y2 = rect
        c = self.canvas
        row_count = len(self.rows_by_mode[self.mode])
        title = "盘口异动 · 实时事件流" if self.mode == "market_event" else f"{MODE_INFO[self.mode][0]} · 实时全字段表"
        c.create_text(x1 + 18, y1 + 20, text=title, anchor="w", fill=TEXT, font=("Microsoft YaHei UI", 12, "bold"))
        if self.mode == "market_event":
            more_rect = (x2 - 132, y1 + 7, x2 - 18, y1 + 35)
            self.layout["market_event_more"] = more_rect
            more_text = "加载中…" if self.market_event_loading else ("加载更早" if self.market_event_has_more else "没有更早")
            self._button(more_rect, more_text, AMBER if self.market_event_has_more else BORDER_BRIGHT, "market_event_more", filled=False)
            c.create_text(x2 - 148, y1 + 20, text=f"{row_count:,} 条  ·  滚到底部自动拼接历史", anchor="e", fill=MUTED, font=FONT_MONO_SMALL)
        else:
            c.create_text(x2 - 18, y1 + 20, text=f"{row_count:,} 行  ·  增量实时更新  ·  横向滚动查看全部字段", anchor="e", fill=MUTED, font=FONT_MONO_SMALL)
        c.create_line(x1 + 14, y1 + 39, x2 - 14, y1 + 39, fill=BORDER, width=1)

    def _refresh_table(self) -> None:
        mode = self.mode
        columns = self._table_columns_for_mode(mode)
        if columns != self.table_columns.get(mode):
            self.table_columns[mode] = columns
        current_tree_columns = tuple(self.data_tree["columns"])
        headings_ready = bool(columns) and bool(self.data_tree.heading(columns[0], "text"))
        if current_tree_columns != columns or not headings_ready:
            self.data_tree.configure(columns=columns)
            for column in columns:
                self.data_tree.heading(column, text=TABLE_HEADINGS.get(column, column), anchor="w")
                self.data_tree.column(column, width=self._table_column_width(column), minwidth=64, stretch=False, anchor="w")

        if getattr(self, "_visible_tree_mode", "") != mode:
            for iid in self.data_tree.get_children(""):
                self.data_tree.delete(iid)
            self.tree_iids[mode].clear()
            self.tree_key_by_iid.clear()
            self._visible_tree_mode = mode

        table_rows = self.rows_by_mode[mode]
        sorted_rows = sorted(table_rows.items(), key=lambda item: self._table_sort_key(mode, item[0], item[1]))
        visible_keys = {key for key, _row in sorted_rows}
        current_iids = self.tree_iids[mode]
        for stale_key in list(current_iids):
            if stale_key not in visible_keys:
                iid = current_iids.pop(stale_key)
                if self.data_tree.exists(iid):
                    self.data_tree.delete(iid)
                self.tree_key_by_iid.pop(iid, None)

        for index, (key, row) in enumerate(sorted_rows):
            iid = current_iids.get(key)
            if iid is None or not self.data_tree.exists(iid):
                self.table_ordinal += 1
                iid = f"row_{self.table_ordinal}"
                current_iids[key] = iid
                self.data_tree.insert("", index, iid=iid, values=self._table_values(columns, row), tags=(self._table_tag(mode, row, index),))
            else:
                self.data_tree.item(iid, values=self._table_values(columns, row), tags=(self._table_tag(mode, row, index),))
                self.data_tree.move(iid, "", index)
            self.tree_key_by_iid[iid] = key

    def _table_columns_for_mode(self, mode: str) -> tuple[str, ...]:
        allowed = set(TABLE_FALLBACK_COLUMNS[mode])
        if mode == "snapshot":
            allowed.update(QUOTE_FIELDS)
        keys = set(TABLE_FALLBACK_COLUMNS[mode])
        for row in self.rows_by_mode[mode].values():
            keys.update(
                key
                for key in row
                if key in allowed
            )
        preferred = list(TABLE_FALLBACK_COLUMNS[mode])
        extras = sorted(keys.difference(preferred))
        return tuple(preferred + extras)

    @staticmethod
    def _table_sort_key(mode: str, key: str, row: dict[str, Any]) -> tuple[Any, ...]:
        if mode == "market_event":
            return (
                -int(row.get("__market_event_time", 0)),
                -int(row.get("__market_event_seq", 0)),
                -int(row.get("__ordinal", 0)),
            )
        if mode == "kline":
            return (str(row.get("code") or ""), str(row.get("date", row.get("time", ""))))
        return (str(row.get("code") or ""), str(row.get("name") or ""), key)

    @staticmethod
    def _table_tag(mode: str, row: dict[str, Any], index: int) -> str:
        parity = "even" if index % 2 == 0 else "odd"
        if mode != "market_event":
            return parity
        color = row.get("__market_event_color")
        if color == 0:
            return f"{parity}_red"
        if color == 1:
            return f"{parity}_green"
        return f"{parity}_unknown"

    @staticmethod
    def _table_column_width(column: str) -> int:
        widths = {
            "__kind": 104,
            "__updated": 92,
            "code": 92,
            "name": 112,
            "price": 92,
            "change_pct": 92,
            "change_amt": 92,
            "volume": 118,
            "amount": 132,
            "info": 300,
            "industry_name": 130,
            "type_name": 150,
            "date": 104,
            "time": 92,
            "pk_time": 94,
            "pk_name": 120,
            "pk_type_name": 148,
            "pk_value": 118,
            "pk_detail": 360,
        }
        return widths.get(column, 112)

    def _table_values(self, columns: tuple[str, ...], row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(self._format_table_value(column, row.get(column), row) for column in columns)

    def _format_table_value(self, column: str, value: Any, row: dict[str, Any]) -> str:
        if column == "__kind":
            return MODE_INFO.get(str(value), ("服务信息" if value == "info" else "错误", "", MUTED))[0]
        if column == "__updated":
            try:
                return datetime.fromtimestamp(float(value)).strftime("%H:%M:%S.%f")[:-4]
            except (TypeError, ValueError, OSError):
                return "—"
        if value is None:
            return "—"
        code = str(row.get("code") or "")
        if column in PRICE_FIELDS:
            return format_price(normalize_value(column, value, code))
        if column in PERCENT_FIELDS:
            return format_pct(normalize_value(column, value, code))
        if column in RATIO_FIELDS:
            normalized = normalize_value(column, value, code)
            return "—" if normalized is None else f"{normalized:.2f}"
        if column == "volume":
            return compact_volume(value)
        if column == "amount":
            return compact_number(value)
        if column == "time":
            return display_time(value)
        if column == "type_color":
            return {0: "红色", 1: "绿色"}.get(value, "—")
        if isinstance(value, (dict, list, tuple)):
            try:
                text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError):
                text = str(value)
            return text[:260]
        return str(value).replace("\r", " ").replace("\n", " ")[:260]

    def _subscription_text(self) -> str:
        if self.mode == "market_event":
            suffix = " · 加载中" if self.market_event_loading else (f" · 历史 {self.market_event_history_pages} 页" if self.market_event_history_pages else "")
            return f"全市场异动{suffix}"
        if self.mode == "kline":
            codes = split_codes(self.codes_var.get())
            return codes[0] if codes else "未选择"
        universe = UNIVERSE_OPTIONS.get(self.universe_var.get(), "")
        if self.mode == "snapshot" and self.subscription_mode_var.get() == "market" and universe:
            try:
                limit = int(self.limit_var.get() or "0")
            except ValueError:
                limit = 0
            return "全市场" if limit == 0 else f"全市场 · {limit}"
        return f"自定义 · {len(split_codes(self.codes_var.get()))} 个"

    def _draw_watermark(self, rect: tuple[float, float, float, float]) -> None:
        """在图表背景层绘制固定视口的产品水印。"""
        x1, y1, x2, y2 = rect
        height = max(1.0, y2 - y1)
        for fraction in (0.34, 0.72):
            self.canvas.create_text(
                (x1 + x2) / 2,
                y1 + height * fraction,
                text="d101\ndata interface",
                anchor="center",
                justify="center",
                fill="#122235",
                font=FONT_WATERMARK,
            )

    def _draw_chart(self, rect: tuple[float, float, float, float]) -> None:
        self._panel(rect, accent=CYAN if self.mode == "snapshot" else PURPLE)
        x1, y1, x2, y2 = rect
        c = self.canvas
        self._draw_watermark(rect)
        selected = self.quotes.get(self.selected_code)
        selected_data = selected.display if selected else {}
        title = "行情脉冲" if self.mode == "snapshot" else ("走势切片" if self.mode == "kline" else "异动雷达")
        subtitle = "等待数据流" if not selected else f"{selected.code}  {selected_data.get('name') or '—'}"
        c.create_text(x1 + 18, y1 + 20, text=title, anchor="w", fill=TEXT, font=FONT_UI_BOLD)
        c.create_text(x1 + 18, y1 + 43, text=subtitle, anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        c.create_text(x2 - 18, y1 + 21, text=MODE_INFO[self.mode][1], anchor="e", fill=MUTED, font=("Microsoft YaHei UI", 8))
        plot = (x1 + 46, y1 + 66, x2 - 24, y2 - 30)
        px1, py1, px2, py2 = plot
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            gy = py1 + (py2 - py1) * fraction
            c.create_line(px1, gy, px2, gy, fill="#1a2d44", width=1)
            c.create_text(px1 - 8, gy, text="·", anchor="e", fill="#4a6782", font=FONT_MONO_SMALL)
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = px1 + (px2 - px1) * fraction
            c.create_line(gx, py1, gx, py2, fill="#13243a", width=1)

        values: list[float] = []
        candles: list[dict[str, Any]] = []
        if self.mode == "kline":
            candles = self.kline_rows
            values = [row["_close"] for row in candles if row.get("_close") is not None]
        elif selected is not None:
            values = list(selected.history)

        if len(values) < 2:
            c.create_text((px1 + px2) / 2, (py1 + py2) / 2, text="等待 d101 数据流…", fill="#52708e", font=("Microsoft YaHei UI", 13))
            c.create_text((px1 + px2) / 2, (py1 + py2) / 2 + 27, text="连接后这里会出现实时轨迹", fill="#344e69", font=FONT_MONO_SMALL)
            return

        low = min(values)
        high = max(values)
        if math.isclose(low, high):
            low -= 1.0
            high += 1.0
        def y_for(value: float) -> float:
            return py2 - (value - low) / (high - low) * (py2 - py1)

        if self.mode == "kline" and candles:
            candle_values = [row for row in candles if row.get("_close") is not None]
            count = len(candle_values)
            step = max(3.0, (px2 - px1) / max(count, 1))
            body_w = max(2.0, min(8.0, step * 0.55))
            for index, row in enumerate(candle_values):
                open_value = row.get("_open")
                high_value = row.get("_high")
                low_value = row.get("_low")
                close_value = row.get("_close")
                if None in (open_value, high_value, low_value, close_value):
                    continue
                cx = px1 + (index + 0.5) * step
                color = UP if close_value >= open_value else DOWN
                c.create_line(cx, y_for(high_value), cx, y_for(low_value), fill=color, width=1)
                top = min(y_for(open_value), y_for(close_value))
                bottom = max(y_for(open_value), y_for(close_value))
                c.create_rectangle(cx - body_w, top, cx + body_w, max(bottom, top + 2), fill=color, outline=color)
        else:
            points: list[float] = []
            for index, value in enumerate(values):
                x = px1 + index * (px2 - px1) / (len(values) - 1)
                points.extend((x, y_for(value)))
            area = [px1, py2, *points, px2, py2]
            c.create_polygon(area, fill="#102b45", outline="", stipple="gray25")
            c.create_line(*points, fill=CYAN, width=2, smooth=True)
            c.create_line(*points, fill="#b3f4ff", width=1, smooth=True)
            last_x, last_y = points[-2], points[-1]
            c.create_oval(last_x - 5, last_y - 5, last_x + 5, last_y + 5, fill=CYAN, outline=WHITE, width=1)
            c.create_text(px2, last_y - 14, text=f"{values[-1]:.2f}", anchor="e", fill=CYAN, font=FONT_MONO_SMALL)
        c.create_text(px1, py2 + 15, text=f"低 {low:.2f}", anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
        c.create_text(px2, py2 + 15, text=f"高 {high:.2f}", anchor="e", fill=MUTED, font=FONT_MONO_SMALL)

    def _draw_detail(self, rect: tuple[float, float, float, float]) -> None:
        self._panel(rect, accent=PINK)
        x1, y1, x2, y2 = rect
        c = self.canvas
        quote = self.quotes.get(self.selected_code)
        data = quote.display if quote else {}
        name = str(data.get("name") or "未选择标的")
        code = quote.code if quote else "—"
        c.create_text(x1 + 18, y1 + 20, text="焦点标的", anchor="w", fill=TEXT, font=FONT_UI_BOLD)
        c.create_text(x2 - 18, y1 + 20, text=code, anchor="e", fill=MUTED, font=FONT_MONO_SMALL)
        c.create_text(x1 + 18, y1 + 55, text=name, anchor="w", fill=TEXT, font=("Microsoft YaHei UI", 17, "bold"))
        price = data.get("_price")
        change = data.get("_change_pct")
        color = quote_color(change)
        c.create_text(x1 + 18, y1 + 96, text=format_price(price), anchor="w", fill=color if price is not None else MUTED, font=("Consolas", 27, "bold"))
        c.create_text(x1 + 166, y1 + 99, text=format_pct(change), anchor="w", fill=color, font=("Consolas", 13, "bold"))
        c.create_line(x1 + 18, y1 + 120, x2 - 18, y1 + 120, fill=BORDER, width=1)

        metrics = [
            ("今开", data.get("_open_price")),
            ("最高", data.get("_high")),
            ("最低", data.get("_low")),
            ("昨收", data.get("_pre_close")),
            ("成交量", compact_volume(data.get("volume"))),
            ("成交额", compact_number(data.get("amount"))),
        ]
        col_w = (x2 - x1 - 36) / 3
        for index, (label, value) in enumerate(metrics):
            col = index % 3
            row = index // 3
            xx = x1 + 18 + col * col_w
            yy = y1 + 143 + row * 43
            c.create_text(xx, yy, text=label, anchor="w", fill=MUTED, font=("Microsoft YaHei UI", 8))
            value_text = value if isinstance(value, str) else format_price(value)
            c.create_text(xx, yy + 20, text=value_text, anchor="w", fill=TEXT_SOFT, font=FONT_MONO_SMALL)

        book_y = y1 + 238
        if book_y + 70 < y2:
            c.create_text(x1 + 18, book_y, text="盘口", anchor="w", fill=MUTED, font=("Microsoft YaHei UI", 8))
            bid = data.get("_bid1_price")
            ask = data.get("_ask1_price")
            bid_vol = safe_number(data.get("bid1_vol"))
            ask_vol = safe_number(data.get("ask1_vol"))
            max_vol = max(bid_vol or 0, ask_vol or 0, 1)
            for index, (label, value, volume, color) in enumerate((("买一", bid, bid_vol, UP), ("卖一", ask, ask_vol, DOWN))):
                yy = book_y + 22 + index * 25
                c.create_text(x1 + 18, yy, text=label, anchor="w", fill=MUTED, font=FONT_MONO_SMALL)
                c.create_text(x1 + 64, yy, text=format_price(value), anchor="w", fill=color, font=FONT_MONO_SMALL)
                bar_x = x1 + 146
                bar_w = max(0.0, (x2 - 28 - bar_x) * min((volume or 0) / max_vol, 1.0))
                c.create_rectangle(bar_x, yy - 7, bar_x + bar_w, yy + 6, fill=color, outline="")
                c.create_text(x2 - 18, yy, text=compact_volume(volume), anchor="e", fill=TEXT_SOFT, font=FONT_MONO_SMALL)

        if quote is None:
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2 + 25, text="点击左下行情表选择标的", fill="#526d88", font=FONT_UI)

    def _draw_table(self, rect: tuple[float, float, float, float]) -> None:
        self._panel(rect, accent=PURPLE)
        x1, y1, x2, y2 = rect
        c = self.canvas
        c.create_text(x1 + 18, y1 + 20, text="实时行情列表", anchor="w", fill=TEXT, font=FONT_UI_BOLD)
        c.create_text(x2 - 18, y1 + 20, text="按 code 合并增量 · 点击行查看焦点", anchor="e", fill=MUTED, font=("Microsoft YaHei UI", 8))
        header_y = y1 + 48
        c.create_rectangle(x1 + 12, header_y, x2 - 12, header_y + 28, fill=SURFACE_2, outline="")
        columns = [("代码", 0.02), ("名称", 0.18), ("最新价", 0.39), ("涨跌幅", 0.53), ("成交量", 0.66), ("成交额", 0.78), ("更新", 0.92)]
        for label, fraction in columns:
            c.create_text(x1 + 18 + (x2 - x1 - 36) * fraction, header_y + 14, text=label, anchor="w", fill=CYAN, font=("Microsoft YaHei UI", 8, "bold"))
        row_h = 30
        codes = list(self.quotes)
        requested = split_codes(self.codes_var.get())
        codes.sort(key=lambda code: (requested.index(code) if code in requested else 9999, code))
        for index, code in enumerate(codes):
            yy = header_y + 32 + index * row_h
            if yy + row_h > y2 - 10:
                break
            quote = self.quotes[code]
            data = quote.display
            selected = code == self.selected_code
            if selected:
                self._rounded_rect(x1 + 12, yy, x2 - 12, yy + row_h - 2, 5, "#17314b", "")
            elif index % 2 == 0:
                c.create_rectangle(x1 + 12, yy, x2 - 12, yy + row_h - 2, fill="#0d1828", outline="")
            color = quote_color(data.get("_change_pct"))
            values = [
                (code, TEXT_SOFT),
                (str(data.get("name") or "—")[:8], TEXT),
                (format_price(data.get("_price")), color),
                (format_pct(data.get("_change_pct")), color),
                (compact_volume(data.get("volume")), TEXT_SOFT),
                (compact_number(data.get("amount")), TEXT_SOFT),
                (datetime.fromtimestamp(quote.received_at).strftime("%H:%M:%S"), MUTED),
            ]
            for (value, text_color), (_label, fraction) in zip(values, columns):
                c.create_text(x1 + 18 + (x2 - x1 - 36) * fraction, yy + 14, text=value, anchor="w", fill=text_color, font=FONT_MONO_SMALL)
        if not codes:
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2 + 12, text="连接 d101 后等待行情行…", fill="#526d88", font=FONT_UI)

    def _draw_events(self, rect: tuple[float, float, float, float]) -> None:
        self._panel(rect, accent=AMBER)
        x1, y1, x2, y2 = rect
        c = self.canvas
        c.create_text(x1 + 18, y1 + 20, text="活动流", anchor="w", fill=TEXT, font=FONT_UI_BOLD)
        c.create_text(x2 - 18, y1 + 20, text=f"错误 {self.error_count}", anchor="e", fill=PINK if self.error_count else MUTED, font=FONT_MONO_SMALL)
        row_h = 30
        visible = max(1, int((y2 - y1 - 50) / row_h))
        for index, event in enumerate(list(self.events)[-visible:]):
            yy = y1 + 44 + index * row_h
            color = event.get("color", MUTED)
            c.create_oval(x1 + 18, yy + 10, x1 + 24, yy + 16, fill=color, outline="")
            c.create_text(x1 + 34, yy + 13, text=event.get("time", ""), anchor="w", fill=MUTED, font=("Consolas", 8))
            c.create_text(x1 + 92, yy + 13, text=event.get("level", ""), anchor="w", fill=color, font=("Consolas", 8, "bold"))
            c.create_text(x1 + 140, yy + 13, text=event.get("message", "")[: max(12, int((x2 - x1) / 8))], anchor="w", fill=TEXT_SOFT, font=("Microsoft YaHei UI", 8))
        if not self.events:
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="暂无活动", fill="#526d88", font=FONT_UI)

    # ── 交互 ─────────────────────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        x, y = float(event.x), float(event.y)
        for target, rect in self.layout.items():
            if self._inside(rect, x, y):
                if target == "connect":
                    self.toggle_connection()
                    return
                if target == "clear":
                    self.clear_data()
                    return
                if target == "market_event_more":
                    self.load_previous_market_event()
                    return
                if target == "subscription_market":
                    self._set_subscription_mode("market")
                    return
                if target == "subscription_codes":
                    self._set_subscription_mode("codes")
                    return
                if target.startswith("tab_"):
                    self.change_mode(target[4:])
                    return

    def _on_tree_select(self, _event: tk.Event) -> None:
        selection = self.data_tree.selection()
        if not selection:
            return
        row = self.rows_by_mode[self.mode].get(self.tree_key_by_iid.get(selection[0], ""), {})
        code = row.get("code")
        if code:
            self.selected_code = str(code)

    def _on_motion(self, event: tk.Event) -> None:
        x, y = float(event.x), float(event.y)
        target = ""
        for key, rect in self.layout.items():
            if key.startswith(("tab_", "connect", "clear", "market_event_more", "subscription_")) and self._inside(rect, x, y):
                target = key
                break
        self._set_hover(target)

    def _set_hover(self, target: str) -> None:
        if self.hover_target != target:
            self.hover_target = target
            self.schedule_draw()

    def clear_data(self) -> None:
        self.quotes.clear()
        self.kline_rows.clear()
        for rows in self.rows_by_mode.values():
            rows.clear()
        for mapping in self.tree_iids.values():
            mapping.clear()
        for iid in self.data_tree.get_children(""):
            self.data_tree.delete(iid)
        self.tree_key_by_iid.clear()
        self.events.clear()
        self.message_count = 0
        self.row_count = 0
        self.error_count = 0
        self.selected_code = ""
        self.market_event_cursor = None
        self.market_event_loading = False
        self.market_event_has_more = True
        self.market_event_history_pages = 0
        self.market_event_scroll_at_bottom = False
        self._add_event("SYS", "面板数据已清空", MUTED)
        self.schedule_draw()

    def toggle_fullscreen(self) -> None:
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)

    def leave_fullscreen(self) -> None:
        self.root.attributes("-fullscreen", False)

    def close(self) -> None:
        self.disconnect(silent=True)
        self.root.destroy()

    def _tick(self) -> None:
        self.schedule_draw()
        self.root.after(1000, self._tick)

    # ── 绘图小工具 ──────────────────────────────────────────────────────

    @staticmethod
    def _inside(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
        return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]

    def _panel(self, rect: tuple[float, float, float, float], accent: str = BORDER_BRIGHT) -> None:
        x1, y1, x2, y2 = rect
        self._rounded_rect(x1, y1, x2, y2, 10, SURFACE, BORDER)
        self.canvas.create_rectangle(x1 + 14, y1 + 1, x1 + 82, y1 + 3, fill=accent, outline="")

    def _button(self, rect: tuple[float, float, float, float], text: str, color: str, target: str, filled: bool = False) -> None:
        x1, y1, x2, y2 = rect
        hover = self.hover_target == target
        fill = color if filled else ("#1a2f49" if hover else SURFACE_2)
        outline = color if (filled or hover) else BORDER_BRIGHT
        self._rounded_rect(x1, y1, x2, y2, 7, fill, outline)
        self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=BG if filled else (color if hover else TEXT_SOFT), font=FONT_UI_BOLD)

    def _pill(self, x1: float, y1: float, x2: float, y2: float, text: str, color: str, filled: bool) -> None:
        self._rounded_rect(x1, y1, x2, y2, 16, color if filled else "#102337", color)
        self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=BG if filled else color, font=("Consolas", 9, "bold"))

    def _rounded_rect(self, x1: float, y1: float, x2: float, y2: float, radius: float, fill: str, outline: str) -> None:
        c = self.canvas
        r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        if outline:
            c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
            c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
            for box, start in (((x1, y1, x1 + 2 * r, y1 + 2 * r), 90), ((x2 - 2 * r, y1, x2, y1 + 2 * r), 0), ((x2 - 2 * r, y2 - 2 * r, x2, y2), 270), ((x1, y2 - 2 * r, x1 + 2 * r, y2), 180)):
                c.create_arc(*box, start=start, extent=90, fill=fill, outline="")
            c.create_line(x1 + r, y1, x2 - r, y1, fill=outline)
            c.create_line(x1 + r, y2, x2 - r, y2, fill=outline)
            c.create_line(x1, y1 + r, x1, y2 - r, fill=outline)
            c.create_line(x2, y1 + r, x2, y2 - r, fill=outline)
            for box, start in (((x1, y1, x1 + 2 * r, y1 + 2 * r), 90), ((x2 - 2 * r, y1, x2, y1 + 2 * r), 0), ((x2 - 2 * r, y2 - 2 * r, x2, y2), 270), ((x1, y2 - 2 * r, x1 + 2 * r, y2), 180)):
                c.create_arc(*box, start=start, extent=90, style="arc", outline=outline)
        else:
            c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
            c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
            for box, start in (((x1, y1, x1 + 2 * r, y1 + 2 * r), 90), ((x2 - 2 * r, y1, x2, y1 + 2 * r), 0), ((x2 - 2 * r, y2 - 2 * r, x2, y2), 270), ((x1, y2 - 2 * r, x1 + 2 * r, y2), 180)):
                c.create_arc(*box, start=start, extent=90, fill=fill, outline="")

    def _add_event(self, level: str, message: str, color: str) -> None:
        self.events.append({"time": display_time(), "level": level, "message": message, "color": color})

    def _age_text(self) -> str:
        if not self.last_message_at:
            return "—"
        age = max(0, int(time.time() - self.last_message_at))
        return "刚刚" if age < 2 else f"{age}s 前"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="d101 Tkinter 用户侧实时行情大屏")
    parser.add_argument("--url", default="ws://127.0.0.1:8080/d101", help="d101 WebSocket 地址")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = tk.Tk()
    D101Gui(root, args.url)
    root.mainloop()


if __name__ == "__main__":
    main()

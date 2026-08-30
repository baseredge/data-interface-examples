#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4 用户侧数据浏览器。

只使用 Python 标准库：Tkinter + urllib。程序启动后不会自动访问网络，
点击按钮后才向本地 D4 HTTP 接口发起只读请求。

运行：
    python d4_gui.py
    python d4_gui.py --base-url http://127.0.0.1:8080
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKGROUND = "#080d1b"
SURFACE = "#111a2b"
SURFACE_2 = "#17243a"
SURFACE_3 = "#0d1424"
BORDER = "#263a56"
NAVY = "#070b16"
TEXT = "#e8f2ff"
MUTED = "#91a4bd"
CYAN = "#43d9ff"
PURPLE = "#9b8cff"
UP = "#ff5b72"
DOWN = "#36d399"
FLAT = "#9eb0c5"
FONT_WATERMARK = ("Microsoft YaHei UI", 24, "bold")

KLINE_PERIODS = [
    ("7", "日 K"),
    ("8", "周 K"),
    ("9", "月 K"),
    ("1", "1 分钟"),
    ("2", "5 分钟"),
    ("3", "15 分钟"),
    ("4", "30 分钟"),
    ("5", "60 分钟"),
]
KLINE_PERIOD_LABELS = [label for _code, label in KLINE_PERIODS]
KLINE_FQ_OPTIONS = [(18, "前复权"), (0, "不复权"), (9, "后复权")]
KLINE_FQ_LABELS = [label for _code, label in KLINE_FQ_OPTIONS]


UNIVERSES = [
    ("cn_hsj_stock", "沪深京 A 股"),
    ("cn_hs_stock", "沪深 A 股"),
    ("cn_sh_stock", "上海 A 股"),
    ("cn_sz_stock", "深圳 A 股"),
    ("cn_bse_stock", "北交所股票"),
    ("cn_star_stock", "科创板股票"),
    ("cn_sh_b_stock", "上海 B 股"),
    ("cn_sz_b_stock", "深圳 B 股"),
    ("cn_index", "沪深指数"),
    ("cn_fund", "基金混合集合"),
    ("cn_sh_fund", "上海基金"),
    ("cn_sz_fund", "深圳基金"),
    ("cn_reit", "REIT"),
    ("cn_sh_bond", "上海债券"),
    ("cn_sz_bond", "深圳债券"),
    ("cn_option", "期权合并集合"),
    ("cn_etf_option", "ETF 期权"),
    ("cn_option_call", "期权认购"),
    ("cn_option_put", "期权认沽"),
]

UNIVERSE_LABELS = [label for _code, label in UNIVERSES]
UNIVERSE_CODES = {label: code for code, label in UNIVERSES}


MIN_FIELDS = "code,name,price"
CONCISE_FIELDS = "code,name,price,change_pct,volume,amount_wan,total_mv_wan"
EQUITY_FIELDS = (
    "code,name,price,total_share,total_mv_wan,float_share,float_mv,"
    "amount_wan,amount_yuan"
)
ORDER_BOOK_FIELDS = (
    "code,name,price,change_pct,bid1,bid2,bid3,bid4,bid5,"
    "ask1,ask2,ask3,ask4,ask5,bid1_vol,bid2_vol,bid3_vol,bid4_vol,"
    "bid5_vol,ask1_vol,ask2_vol,ask3_vol,ask4_vol,ask5_vol"
)
FUNDAMENTAL_FIELDS = (
    "code,name,price,pe_ttm,pb,eps,roe,net_profit_yoy,book_value_per_share,"
    "main_net_flow_wan,super_large_net_flow_wan,medium_net_flow_wan,"
    "small_net_flow_wan,turnover_rate,volume_ratio"
)
STOCK_DETAIL_FIELDS = (
    "code,name,price,change_pct,change_amt,pre_close,open,high,low,"
    "volume,amount_wan,turnover_rate,volume_ratio,bid1,ask1,bid1_vol,"
    "ask1_vol,pe_ttm,pb,total_share,total_mv_wan,float_share,float_mv,industry_name"
)
STOCK_OVERVIEW_FIELDS = (
    "code,name,price,change_pct,change_amt,pre_close,open,high,low,amplitude,"
    "volume,amount_wan,turnover_rate,volume_ratio,bid1,ask1,bid1_vol,ask1_vol,"
    "pe_ttm,pb,total_share,total_mv_wan,float_share,float_mv,outer_vol,inner_vol,"
    "change_pct_3d,change_pct_6d,turnover_3d,turnover_6d,eps,roe,list_date,industry_name"
)
OPTION_DETAIL_FIELDS = (
    "code,name,price,change_pct,change_amt,pre_close,open,high,low,volume,"
    "amount_wan,opt_price,open_interest,remain_days,strike,unit_size,delta,"
    "gamma,vega,theta,amount_yuan,leverage,contract"
)

FIELD_PRESETS = [
    ("简洁字段组", CONCISE_FIELDS),
    ("股票详情（推荐）", STOCK_DETAIL_FIELDS),
    ("最小稳定字段", MIN_FIELDS),
    ("行情摘要", "code,name,price,change_pct,change_amt,volume,amount_wan,turnover_rate,volume_ratio"),
    ("股本与市值", EQUITY_FIELDS),
    ("盘口五档", ORDER_BOOK_FIELDS),
    ("资金与财务", FUNDAMENTAL_FIELDS),
    ("股票扩展信息（页数调小）", STOCK_OVERVIEW_FIELDS),
    ("期权详情", OPTION_DETAIL_FIELDS),
]


FIELD_LABELS = {
    "code": "代码",
    "name": "名称",
    "price": "最新价",
    "change_pct": "涨跌幅",
    "change_amt": "涨跌额",
    "pre_close": "昨收",
    "open": "开盘",
    "high": "最高",
    "low": "最低",
    "amplitude": "振幅",
    "volume": "成交量",
    "tick_vol": "现手量",
    "amount_wan": "成交额(万元)",
    "amount": "成交金额",
    "turnover_rate": "换手率",
    "volume_ratio": "量比",
    "speed_3min": "3 分钟涨速",
    "bid1": "买一价",
    "ask1": "卖一价",
    "bid1_vol": "买一量",
    "ask1_vol": "卖一量",
    "pe_ttm": "TTM 市盈率",
    "pb": "市净率",
    "total_share": "总股本（股）",
    "total_mv_wan": "总市值(万元)",
    "float_share": "流通股本",
    "float_mv": "流通市值",
    "outer_vol": "外盘量",
    "inner_vol": "内盘量",
    "change_pct_3d": "3 日涨跌幅",
    "change_pct_6d": "6 日涨跌幅",
    "turnover_3d": "3 日换手率",
    "turnover_6d": "6 日换手率",
    "eps": "每股收益",
    "roe": "净资产收益率",
    "list_date": "上市日期",
    "industry_name": "行业",
    "opt_price": "期权价",
    "open_interest": "持仓量",
    "remain_days": "剩余天数",
    "strike": "行权价",
    "unit_size": "合约单位",
    "delta": "Delta",
    "gamma": "Gamma",
    "vega": "Vega",
    "theta": "Theta",
    "amount_yuan": "成交额（元）",
    "leverage": "杠杆率",
    "contract": "合约描述",
}

FIELD_LABELS.update(
    {
        "net_profit_yoy": "净利润同比",
        "book_value_per_share": "每股净资产",
        "change_pct_3d_alt": "3 日涨跌幅（扩展）",
        "change_pct_5d": "5 日涨跌幅",
        "change_pct_10d": "10 日涨跌幅",
        "main_net_flow_wan": "主力净流额(万元)",
        "main_net_flow_auction_wan": "集合竞价主力净流额(万元)",
        "super_large_inflow_wan": "超大单流入(万元)",
        "super_large_outflow_wan": "超大单流出(万元)",
        "super_large_net_flow_wan": "超大单净流额(万元)",
        "super_large_net_ratio": "超大单净比",
        "medium_inflow_wan": "中单流入(万元)",
        "medium_outflow_wan": "中单流出(万元)",
        "medium_net_flow_wan": "中单净流额(万元)",
        "medium_net_ratio": "中单净比",
        "small_inflow_wan": "小单流入(万元)",
        "small_outflow_wan": "小单流出(万元)",
        "small_net_flow_wan": "小单净流额(万元)",
        "small_net_ratio": "小单净比",
        "sector_leader_name": "板块领涨股",
        "sector_for_sale_count": "板块在售家数",
        "sector_total_count": "板块总家数",
        "sector_rise_count": "板块涨家数",
        "sector_fall_count": "板块跌家数",
        "bid2": "买二价",
        "bid3": "买三价",
        "bid4": "买四价",
        "bid5": "买五价",
        "ask2": "卖二价",
        "ask3": "卖三价",
        "ask4": "卖四价",
        "ask5": "卖五价",
        "bid2_vol": "买二量",
        "bid3_vol": "买三量",
        "bid4_vol": "买四量",
        "bid5_vol": "买五量",
        "ask2_vol": "卖二量",
        "ask3_vol": "卖三量",
        "ask4_vol": "卖四量",
        "ask5_vol": "卖五量",
        "sector_leader_code": "板块领涨股代码",
        "speed_5min": "5 分钟涨速",
        "order_ratio": "委比",
        "inner_outer_ratio": "内外比",
        "average_price": "均价",
        "limit_up": "涨停价",
        "limit_down": "跌停价",
        "margin_financing": "融资融券",
        "security_type": "品种类型",
        "consecutive_up_days": "连涨天数",
        "change_pct_month": "本月涨跌幅",
        "change_pct_year": "本年涨跌幅",
        "change_pct_1m": "近 1 月涨跌幅",
        "change_pct_1y": "近 1 年涨跌幅",
    }
)

FIELD_ID_TO_NAME = {
    "1": "code",
    "2": "name",
    "3": "price",
    "4": "change_pct",
    "5": "change_amt",
    "6": "bid1",
    "7": "ask1",
    "8": "industry_name",
    "9": "volume",
    "10": "tick_vol",
    "11": "amount_wan",
    "12": "pe_ttm",
    "13": "speed_3min",
    "14": "turnover_rate",
    "15": "volume_ratio",
    "16": "pre_close",
    "17": "open",
    "18": "high",
    "19": "low",
    "20": "amplitude",
    "21": "pb",
    "22": "total_share",
    "23": "total_mv_wan",
    "24": "float_share",
    "25": "float_mv",
    "26": "outer_vol",
    "27": "inner_vol",
    "28": "change_pct_3d",
    "29": "change_pct_6d",
    "30": "turnover_3d",
    "31": "turnover_6d",
    "32": "eps",
    "33": "roe",
    "34": "list_date",
    "157": "bid1_vol",
    "162": "ask1_vol",
    "181": "opt_price",
    "195": "open_interest",
    "196": "remain_days",
    "197": "strike",
    "199": "unit_size",
    "200": "delta",
    "201": "gamma",
    "202": "vega",
    "203": "theta",
    "247": "amount",
    "293": "amount_yuan",
    "316": "leverage",
    "320": "contract",
}

FIELD_ID_TO_NAME.update(
    {
        "37": "net_profit_yoy",
        "39": "book_value_per_share",
        "69": "change_pct_3d_alt",
        "73": "change_pct_5d",
        "77": "change_pct_10d",
        "78": "main_net_flow_wan",
        "79": "main_net_flow_auction_wan",
        "80": "super_large_inflow_wan",
        "81": "super_large_outflow_wan",
        "82": "super_large_net_flow_wan",
        "83": "super_large_net_ratio",
        "84": "medium_inflow_wan",
        "85": "medium_outflow_wan",
        "86": "medium_net_flow_wan",
        "87": "medium_net_ratio",
        "88": "small_inflow_wan",
        "89": "small_outflow_wan",
        "90": "small_net_flow_wan",
        "91": "small_net_ratio",
        "92": "sector_leader_name",
        "93": "sector_for_sale_count",
        "95": "sector_total_count",
        "96": "sector_rise_count",
        "97": "sector_fall_count",
        "98": "bid2",
        "99": "bid3",
        "100": "bid4",
        "101": "bid5",
        "102": "ask2",
        "103": "ask3",
        "104": "ask4",
        "105": "ask5",
        "158": "bid2_vol",
        "159": "bid3_vol",
        "160": "bid4_vol",
        "161": "bid5_vol",
        "163": "ask2_vol",
        "164": "ask3_vol",
        "165": "ask4_vol",
        "166": "ask5_vol",
        "171": "sector_leader_code",
        "173": "speed_5min",
        "176": "order_ratio",
        "177": "inner_outer_ratio",
        "183": "average_price",
        "186": "limit_up",
        "187": "limit_down",
        "209": "margin_financing",
        "239": "security_type",
        "240": "consecutive_up_days",
        "241": "change_pct_month",
        "242": "change_pct_year",
        "243": "change_pct_1m",
        "244": "change_pct_1y",
    }
)

ALL_KNOWN_FIELD_IDS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 37, 39, 69,
    73, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92,
    93, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 157, 158, 159,
    160, 161, 162, 163, 164, 165, 166, 171, 173, 176, 177, 181, 183, 186,
    187, 195, 196, 197, 199, 200, 201, 202, 203, 209, 239, 240, 241, 242,
    243, 244, 247, 293, 316, 320,
)
ALL_KNOWN_FIELDS = ",".join(FIELD_ID_TO_NAME[str(field_id)] for field_id in ALL_KNOWN_FIELD_IDS)
ALL_KNOWN_PRESET = "全部已知字段（建议每页100）"
FIELD_PRESETS.append((ALL_KNOWN_PRESET, ALL_KNOWN_FIELDS))
FIELD_PRESET_LABELS = [label for label, _fields in FIELD_PRESETS]


class D4RequestError(RuntimeError):
    """可直接显示给用户的 D4 请求错误。"""


@dataclass
class PageResult:
    total: int
    rows: list[dict]
    skip: int
    requested_count: int


@dataclass
class AllResult:
    total: int
    rows: list[dict]
    pages: int
    cancelled: bool


@dataclass
class KlineResult:
    code: str
    rows: list[dict]
    requested_count: int
    period: int
    fq: int


def fetch_page(
    base_url: str,
    universe: str,
    skip: int,
    count: int,
    fields: str,
    timeout: float,
) -> PageResult:
    """请求一页 D4 数据，不在这里修改 GUI。"""
    endpoint = base_url.rstrip("/") + "/d4/l1/instrument_list"
    query = urlencode(
        {
            "universe": universe,
            "skip": skip,
            "count": count,
            "fields": fields,
        }
    )
    request = Request(
        f"{endpoint}?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = json.loads(response.read().decode(charset))
    except HTTPError as exc:
        raise D4RequestError(f"数据请求失败（HTTP {exc.code}）") from exc
    except URLError as exc:
        raise D4RequestError("无法连接本地数据服务") from exc
    except TimeoutError as exc:
        raise D4RequestError("D4 请求超时") from exc
    except json.JSONDecodeError as exc:
        raise D4RequestError("D4 返回的内容不是合法 JSON") from exc

    if not isinstance(payload, dict):
        raise D4RequestError("D4 返回格式错误：顶层不是 JSON 对象")
    if payload.get("error"):
        raise D4RequestError("数据服务返回错误，请检查查询条件")

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise D4RequestError("D4 返回格式错误：缺少 rows 数组")

    try:
        total = int(payload.get("total", 0))
    except (TypeError, ValueError) as exc:
        raise D4RequestError("D4 返回格式错误：total 不是数字") from exc

    return PageResult(total=max(0, total), rows=rows, skip=skip, requested_count=count)


def fetch_kline(
    base_url: str,
    code: str,
    period: int,
    count: int,
    fq: int,
    timeout: float,
) -> KlineResult:
    """请求 D4 K 线列表，不在这里修改 GUI。"""
    endpoint = base_url.rstrip("/") + "/d4/l1/kline"
    query = urlencode(
        {
            "code": code,
            "period": period,
            "count": count,
            "fq": fq,
        }
    )
    request = Request(
        f"{endpoint}?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = json.loads(response.read().decode(charset))
    except HTTPError as exc:
        raise D4RequestError(f"K 线请求失败（HTTP {exc.code}）") from exc
    except URLError as exc:
        raise D4RequestError("无法连接本地数据服务") from exc
    except TimeoutError as exc:
        raise D4RequestError("K 线请求超时") from exc
    except json.JSONDecodeError as exc:
        raise D4RequestError("D4 K 线返回的内容不是合法 JSON") from exc

    if not isinstance(payload, dict):
        raise D4RequestError("D4 K 线返回格式错误：顶层不是 JSON 对象")
    if payload.get("error"):
        raise D4RequestError("K 线服务返回错误，请检查查询条件")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise D4RequestError("D4 K 线返回格式错误：缺少 rows 数组")

    valid_rows = [row for row in rows if isinstance(row, dict)]
    return KlineResult(
        code=str(payload.get("code") or code),
        rows=valid_rows,
        requested_count=count,
        period=period,
        fq=fq,
    )


class D4Gui:
    def __init__(self, root: tk.Tk, base_url: str, timeout: float) -> None:
        self.root = root
        self.timeout = timeout
        self.root.title("D4 证券数据浏览器")
        self.root.geometry("1440x920")
        self.root.minsize(1080, 700)
        self.root.configure(background=BACKGROUND)

        self.base_url_var = tk.StringVar(value=base_url)
        self.universe_var = tk.StringVar(value=UNIVERSE_LABELS[0])
        self.preset_var = tk.StringVar(value=FIELD_PRESET_LABELS[0])
        self.fields_var = tk.StringVar(value=STOCK_DETAIL_FIELDS)
        self.field_count_var = tk.StringVar(value="字段数：0")
        self.skip_var = tk.StringVar(value="0")
        self.count_var = tk.StringVar(value="300")
        self.status_var = tk.StringVar(value="准备就绪。请选择品种池和字段后查询。")
        self.summary_var = tk.StringVar(value="尚未查询")
        self.total_stat_var = tk.StringVar(value="—")
        self.page_stat_var = tk.StringVar(value="—")
        self.loaded_stat_var = tk.StringVar(value="—")
        self.kline_code_var = tk.StringVar(value="000001")
        self.kline_period_var = tk.StringVar(value=KLINE_PERIOD_LABELS[0])
        self.kline_fq_var = tk.StringVar(value=KLINE_FQ_LABELS[0])
        self.kline_count_var = tk.StringVar(value="100")
        self.kline_summary_var = tk.StringVar(value="选择左侧品种后加载 K 线")
        self.kline_status_var = tk.StringVar(value="K 线面板待命")

        self.current_skip = 0
        self.current_rows: list[dict] = []
        self.current_total = 0
        self.last_page_size = 300
        self.kline_rows: list[dict] = []
        self.busy = False
        self.cancel_event = threading.Event()
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.tree_columns: list[str] = []
        self.row_by_item: dict[str, dict] = {}

        self._build_style()
        self.fields_var.trace_add("write", self._on_fields_changed)
        self._on_fields_changed()
        self._build_header()
        self._build_controls()
        self._build_stat_cards()
        self._build_table()
        self._update_navigation()
        self.root.after(50, self._drain_worker_queue)

        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Return>", lambda _event: self.query_current_page())

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Panel.TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background=SURFACE, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure(
            "Small.TLabel",
            background=BACKGROUND,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Treeview",
            background=SURFACE_3,
            fieldbackground=SURFACE_3,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            rowheight=29,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=SURFACE_2,
            foreground=CYAN,
            bordercolor=BORDER,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#214b6f")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TLabelframe",
            background=SURFACE,
            foreground=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.configure(
            "TLabelframe.Label",
            background=SURFACE,
            foreground=CYAN,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "TButton",
            background=SURFACE_2,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(10, 6),
            font=("Microsoft YaHei UI", 10),
        )
        style.map(
            "TButton",
            background=[("active", "#2b496b"), ("pressed", "#315d84"), ("disabled", "#101827")],
            foreground=[("disabled", "#53657c")],
        )
        style.configure(
            "Accent.TButton",
            background=CYAN,
            foreground="#06111f",
            bordercolor=CYAN,
            padding=(12, 6),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#8beaff"), ("pressed", "#22b7df")])
        style.configure(
            "TEntry",
            fieldbackground=SURFACE_3,
            foreground=TEXT,
            insertcolor=CYAN,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_3,
            foreground=TEXT,
            background=SURFACE_2,
            arrowcolor=CYAN,
            bordercolor=BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", SURFACE_3)],
            foreground=[("readonly", TEXT)],
        )
        style.configure(
            "TNotebook",
            background=BACKGROUND,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=SURFACE_2,
            foreground=MUTED,
            padding=(16, 7),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CYAN), ("active", "#2b496b")],
            foreground=[("selected", "#06111f"), ("active", TEXT)],
        )

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=NAVY, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_box = tk.Frame(header, bg=NAVY)
        title_box.pack(side="left", padx=24, pady=14)
        tk.Label(
            title_box,
            text="达塔接口  ·  D4",
            bg=NAVY,
            fg=CYAN,
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="MARKET TERMINAL  /  READ-ONLY DATA",
            bg=NAVY,
            fg="#7fa3c4",
            font=("Consolas", 9),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            header,
            text="●  LOCAL  ONLINE",
            bg="#102b3c",
            fg=CYAN,
            padx=12,
            pady=5,
            font=("Consolas", 9, "bold"),
        ).pack(side="right", padx=24, pady=18)
        tk.Label(
            header,
            text="d4\ndata interface",
            bg=NAVY,
            fg="#25415d",
            justify="right",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="right", padx=(0, 18), pady=10)
        tk.Frame(header, bg=CYAN, height=2).pack(side="bottom", fill="x")

    def _build_controls(self) -> None:
        panel = ttk.LabelFrame(self.root, text="查询条件", padding=10)
        panel.pack(fill="x", padx=14, pady=(12, 8))

        ttk.Label(panel, text="本地地址").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(panel, textvariable=self.base_url_var, width=30).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(0, 16), pady=4
        )

        ttk.Label(panel, text="品种池").grid(row=0, column=3, sticky="w", padx=(0, 6), pady=4)
        self.universe_box = ttk.Combobox(
            panel,
            textvariable=self.universe_var,
            values=UNIVERSE_LABELS,
            state="readonly",
            width=28,
        )
        self.universe_box.grid(row=0, column=4, columnspan=3, sticky="ew", padx=(0, 16), pady=4)

        ttk.Label(panel, text="字段预设").grid(row=0, column=7, sticky="w", padx=(0, 6), pady=4)
        self.preset_box = ttk.Combobox(
            panel,
            textvariable=self.preset_var,
            values=FIELD_PRESET_LABELS,
            state="readonly",
            width=23,
        )
        self.preset_box.grid(row=0, column=8, columnspan=2, sticky="ew", padx=(0, 4), pady=4)
        self.preset_box.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Label(panel, text="字段").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(panel, textvariable=self.fields_var).grid(
            row=1, column=1, columnspan=8, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(panel, text="应用预设", command=self._apply_preset).grid(
            row=1, column=9, padx=3, pady=4
        )

        ttk.Label(panel, text="跳过").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(panel, textvariable=self.skip_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(0, 18), pady=4
        )
        ttk.Label(panel, text="每页条数").grid(row=2, column=2, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(panel, textvariable=self.count_var, width=10).grid(
            row=2, column=3, sticky="w", padx=(0, 18), pady=4
        )
        ttk.Label(
            panel,
            text="详情字段较多时建议 300；想更快浏览可切换“最小稳定字段”。",
            style="Small.TLabel",
        ).grid(row=2, column=4, columnspan=4, sticky="w", padx=(0, 12), pady=4)

        self.first_button = ttk.Button(panel, text="首页", command=self.first_page)
        self.first_button.grid(row=2, column=8, padx=3, pady=4)
        self.query_button = ttk.Button(
            panel, text="查询当前页", command=self.query_current_page, style="Accent.TButton"
        )
        self.query_button.grid(row=2, column=9, padx=3, pady=4)
        self.previous_button = ttk.Button(panel, text="上一页", command=self.previous_page)
        self.previous_button.grid(row=3, column=8, padx=3, pady=4)
        self.next_button = ttk.Button(panel, text="下一页", command=self.next_page)
        self.next_button.grid(row=3, column=9, padx=3, pady=4)
        self.all_button = ttk.Button(panel, text="读取全部", command=self.read_all, style="Accent.TButton")
        self.all_button.grid(row=3, column=6, padx=3, pady=4)
        self.cancel_button = ttk.Button(panel, text="取消读取", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=3, column=7, padx=3, pady=4)

        ttk.Label(
            panel,
            text="字段填写业务名称并用逗号分隔；表格只显示业务含义。",
            style="Small.TLabel",
        ).grid(row=3, column=0, columnspan=6, sticky="w", padx=(0, 8), pady=4)

        quick_frame = ttk.Frame(panel, style="Panel.TFrame")
        quick_frame.grid(row=4, column=0, columnspan=10, sticky="ew", pady=(5, 0))
        ttk.Label(quick_frame, text="快捷字段组", style="Panel.TLabel").pack(
            side="left", padx=(0, 8)
        )
        quick_groups = [
            ("简洁字段组", "简洁字段组"),
            ("行情摘要", "行情摘要"),
            ("股本 / 市值", "股本与市值"),
            ("盘口五档", "盘口五档"),
            ("资金 / 财务", "资金与财务"),
            ("全部已知字段", ALL_KNOWN_PRESET),
        ]
        for button_text, preset_label in quick_groups:
            ttk.Button(
                quick_frame,
                text=button_text,
                command=lambda label=preset_label: self._select_field_group(label),
            ).pack(side="left", padx=2)
        ttk.Label(quick_frame, textvariable=self.field_count_var, style="Panel.TLabel").pack(
            side="right", padx=(8, 0)
        )

        for column in (1, 2, 4, 5, 6, 8, 9):
            panel.columnconfigure(column, weight=1)

    def _build_stat_cards(self) -> None:
        cards = tk.Frame(self.root, bg=BACKGROUND)
        cards.pack(fill="x", padx=14, pady=(0, 8))

        self._make_stat_card(cards, "品种总数", self.total_stat_var, CYAN).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        self._make_stat_card(cards, "当前页", self.page_stat_var, PURPLE).pack(
            side="left", fill="x", expand=True, padx=3
        )
        self._make_stat_card(cards, "已展示", self.loaded_stat_var, UP).pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )

        summary = ttk.Label(self.root, textvariable=self.summary_var, anchor="w", style="Small.TLabel")
        summary.pack(fill="x", padx=17, pady=(0, 2))
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", style="Small.TLabel")
        status.pack(fill="x", padx=17, pady=(0, 8))

    @staticmethod
    def _make_stat_card(parent, title: str, value_var: tk.StringVar, color: str) -> tk.Frame:
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")
        content = tk.Frame(card, bg=SURFACE)
        content.pack(side="left", fill="both", expand=True)
        tk.Label(
            content,
            text=title,
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=12, pady=(8, 0))
        tk.Label(
            content,
            textvariable=value_var,
            bg=SURFACE,
            fg="#f2f8ff",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", padx=12, pady=(0, 8))
        return card

    def _build_table(self) -> None:
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # The instrument table is the primary workspace.  Keep K-line in a
        # separate tab so the list gets the full width and height instead of
        # being permanently squeezed by a chart panel.
        workspace = ttk.Notebook(body)
        workspace.pack(fill="both", expand=True)
        self.workspace_tabs = workspace

        table_panel = ttk.LabelFrame(workspace, text="品种列表  /  INSTRUMENTS", padding=7)
        kline_panel = ttk.LabelFrame(workspace, text="K 线列表  /  KLINE", padding=8)
        workspace.add(table_panel, text="品种列表")
        workspace.add(kline_panel, text="K 线分析")
        self.kline_panel = kline_panel

        self.tree = ttk.Treeview(table_panel, columns=("message",), show="headings", selectmode="browse")
        self.tree.heading("message", text="数据")
        self.tree.column("message", width=650, anchor="w")
        self.tree.tag_configure("up", foreground=UP)
        self.tree.tag_configure("down", foreground=DOWN)
        self.tree.tag_configure("flat", foreground=FLAT)
        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self.tree.bind("<Double-1>", self._load_selected_kline)

        vertical = ttk.Scrollbar(table_panel, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table_panel, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_panel.rowconfigure(0, weight=1)
        table_panel.columnconfigure(0, weight=1)

        kline_controls = ttk.Frame(kline_panel, style="Panel.TFrame")
        kline_controls.pack(fill="x", pady=(0, 5))
        ttk.Label(kline_controls, text="代码", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 5), pady=3
        )
        ttk.Entry(kline_controls, textvariable=self.kline_code_var, width=10).grid(
            row=0, column=1, sticky="ew", padx=(0, 7), pady=3
        )
        ttk.Label(kline_controls, text="周期", style="Panel.TLabel").grid(
            row=0, column=2, sticky="w", padx=(0, 5), pady=3
        )
        ttk.Combobox(
            kline_controls,
            textvariable=self.kline_period_var,
            values=KLINE_PERIOD_LABELS,
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky="ew", padx=(0, 7), pady=3)
        ttk.Label(kline_controls, text="复权", style="Panel.TLabel").grid(
            row=0, column=4, sticky="w", padx=(0, 5), pady=3
        )
        ttk.Combobox(
            kline_controls,
            textvariable=self.kline_fq_var,
            values=KLINE_FQ_LABELS,
            state="readonly",
            width=10,
        ).grid(row=0, column=5, sticky="ew", padx=(0, 7), pady=3)
        ttk.Label(kline_controls, text="条数", style="Panel.TLabel").grid(
            row=0, column=6, sticky="w", padx=(0, 5), pady=3
        )
        ttk.Entry(kline_controls, textvariable=self.kline_count_var, width=8).grid(
            row=0, column=7, sticky="ew", padx=(0, 7), pady=3
        )
        self.kline_button = ttk.Button(
            kline_controls,
            text="加载 K 线",
            command=self.query_kline,
            style="Accent.TButton",
        )
        self.kline_button.grid(row=0, column=8, sticky="ew", pady=3)
        kline_controls.columnconfigure(1, weight=1)
        kline_controls.columnconfigure(3, weight=1)
        kline_controls.columnconfigure(5, weight=1)
        kline_controls.columnconfigure(7, weight=1)

        ttk.Label(
            kline_panel,
            textvariable=self.kline_summary_var,
            style="Panel.TLabel",
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        kline_panes = ttk.Frame(kline_panel, style="Panel.TFrame")
        kline_panes.pack(fill="both", expand=True)
        kline_panes.rowconfigure(0, weight=1)
        kline_panes.columnconfigure(0, weight=3)
        kline_panes.columnconfigure(1, weight=7)
        chart_panel = ttk.Frame(kline_panes, style="Panel.TFrame")
        kline_box = ttk.Frame(kline_panes, style="Panel.TFrame")
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        kline_box.grid(row=0, column=1, sticky="nsew")

        self.kline_canvas = tk.Canvas(
            chart_panel,
            height=145,
            background=SURFACE_3,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.kline_canvas.pack(fill="both", expand=True)
        self.kline_canvas.bind("<Configure>", lambda _event: self._draw_kline_chart())

        kline_columns = (
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "turnover",
            "turnover_real",
        )
        self.kline_tree = ttk.Treeview(
            kline_box,
            columns=kline_columns,
            show="headings",
            selectmode="browse",
        )
        kline_headings = {
            "date": "日期/时间",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
            "turnover": "换手",
            "turnover_real": "实际换手",
        }
        for column in kline_columns:
            self.kline_tree.heading(column, text=kline_headings[column])
            self.kline_tree.column(
                column,
                width=115 if column in {"date", "amount"} else 82,
                minwidth=68,
                anchor="w",
                stretch=False,
            )
        self.kline_tree.tag_configure("up", foreground=UP)
        self.kline_tree.tag_configure("down", foreground=DOWN)
        self.kline_tree.tag_configure("flat", foreground=FLAT)
        kline_scroll_y = ttk.Scrollbar(kline_box, orient="vertical", command=self.kline_tree.yview)
        kline_scroll_x = ttk.Scrollbar(kline_box, orient="horizontal", command=self.kline_tree.xview)
        self.kline_tree.configure(yscrollcommand=kline_scroll_y.set, xscrollcommand=kline_scroll_x.set)
        self.kline_tree.grid(row=0, column=0, sticky="nsew")
        kline_scroll_y.grid(row=0, column=1, sticky="ns")
        kline_scroll_x.grid(row=1, column=0, sticky="ew")
        kline_box.rowconfigure(0, weight=1)
        kline_box.columnconfigure(0, weight=1)

        ttk.Label(
            kline_panel,
            textvariable=self.kline_status_var,
            style="Panel.TLabel",
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

    def _on_preset_selected(self, _event=None) -> None:
        self._apply_preset()

    def _on_fields_changed(self, *_args) -> None:
        tokens = [token.strip() for token in self.fields_var.get().split(",") if token.strip()]
        self.field_count_var.set(f"字段数：{len(tokens)}")

    def _select_field_group(self, label: str) -> None:
        self.preset_var.set(label)
        self._apply_preset()

    def _apply_preset(self) -> None:
        selected = self.preset_var.get()
        for label, fields in FIELD_PRESETS:
            if label == selected:
                self.fields_var.set(fields)
                if label == ALL_KNOWN_PRESET:
                    self.count_var.set("100")
                    self.status_var.set("已应用全部已知字段；每页已调整为 100 条，避免单页过大。")
                else:
                    self.status_var.set(f"已应用字段预设：{label}。")
                return

    def _set_min_fields(self) -> None:
        self.preset_var.set("最小稳定字段")
        self.fields_var.set(MIN_FIELDS)

    def _set_common_fields(self) -> None:
        self.preset_var.set("行情摘要")
        self.fields_var.set("code,name,price,change_pct,change_amt,volume,amount_wan,turnover_rate,volume_ratio")

    def _selected_universe(self) -> str:
        value = self.universe_var.get().strip()
        return UNIVERSE_CODES.get(value, UNIVERSES[0][0])

    def _read_options(self) -> tuple[str, str, int, int]:
        base_url = self.base_url_var.get().strip()
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("本地地址必须以 http:// 或 https:// 开头")

        fields = self.fields_var.get().strip()
        if not fields:
            raise ValueError("字段不能为空")
        if not any(token.strip() for token in fields.split(",")):
            raise ValueError("字段不能为空")

        try:
            skip = int(self.skip_var.get().strip())
            count = int(self.count_var.get().strip())
        except ValueError as exc:
            raise ValueError("跳过和每页条数必须是整数") from exc
        if skip < 0:
            raise ValueError("跳过不能小于 0")
        if count <= 0:
            raise ValueError("每页条数必须大于 0")
        if count > 1000:
            self.status_var.set("提示：单页最多建议 1000 条；字段较多时请进一步调小。")

        return base_url, fields, skip, count

    def _start_worker(self, worker, on_success) -> None:
        if self.busy:
            return
        self.busy = True
        self.cancel_event.clear()
        self._update_navigation()

        def run() -> None:
            try:
                result = worker()
            except Exception as exc:  # 网络错误和数据错误都回到 GUI 线程处理
                self.worker_queue.put(("error", str(exc)))
            else:
                self.worker_queue.put(("success", (on_success, result)))

        threading.Thread(target=run, name="d4-gui-worker", daemon=True).start()

    def _drain_worker_queue(self) -> None:
        """只在 Tk 主线程执行 GUI 更新，网络线程只负责投递结果。"""
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "error":
                    self._worker_failed(str(payload))
                elif kind == "progress":
                    self.status_var.set(str(payload))
                elif kind == "success":
                    on_success, result = payload
                    self._worker_succeeded(on_success, result)
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(50, self._drain_worker_queue)
        except tk.TclError:
            pass

    def _worker_succeeded(self, on_success, result) -> None:
        self.busy = False
        self._update_navigation()
        on_success(result)

    def _worker_failed(self, message: str) -> None:
        self.busy = False
        self._update_navigation()
        self.status_var.set("请求失败：" + message)
        messagebox.showerror("D4 请求失败", message, parent=self.root)

    def query_current_page(self) -> None:
        try:
            base_url, fields, skip, count = self._read_options()
        except ValueError as exc:
            messagebox.showwarning("参数检查", str(exc), parent=self.root)
            return

        universe = self._selected_universe()
        self.status_var.set(f"正在读取 {universe} 的第 {skip} 条开始的数据 ...")
        self._start_worker(
            lambda: fetch_page(base_url, universe, skip, count, fields, self.timeout),
            self._show_page,
        )

    def first_page(self) -> None:
        if self.busy:
            return
        self.skip_var.set("0")
        self.query_current_page()

    def previous_page(self) -> None:
        if self.busy or self.current_skip <= 0:
            return
        try:
            base_url, fields, _skip, count = self._read_options()
        except ValueError as exc:
            messagebox.showwarning("参数检查", str(exc), parent=self.root)
            return

        new_skip = max(0, self.current_skip - self.last_page_size)
        universe = self._selected_universe()
        self.skip_var.set(str(new_skip))
        self.status_var.set(f"正在读取第 {new_skip} 条开始的数据 ...")
        self._start_worker(
            lambda: fetch_page(base_url, universe, new_skip, count, fields, self.timeout),
            self._show_page,
        )

    def next_page(self) -> None:
        if self.busy or not self.current_rows:
            return
        next_skip = self.current_skip + len(self.current_rows)
        if self.current_total and next_skip >= self.current_total:
            return
        try:
            base_url, fields, _skip, count = self._read_options()
        except ValueError as exc:
            messagebox.showwarning("参数检查", str(exc), parent=self.root)
            return

        universe = self._selected_universe()
        self.skip_var.set(str(next_skip))
        self.status_var.set(f"正在读取第 {next_skip} 条开始的数据 ...")
        self._start_worker(
            lambda: fetch_page(base_url, universe, next_skip, count, fields, self.timeout),
            self._show_page,
        )

    def read_all(self) -> None:
        try:
            base_url, fields, _skip, count = self._read_options()
        except ValueError as exc:
            messagebox.showwarning("参数检查", str(exc), parent=self.root)
            return

        universe = self._selected_universe()
        self.status_var.set(f"正在分页读取 {universe}，可以点击“取消读取”停止 ...")

        def worker() -> AllResult:
            rows_by_code: dict[str, dict] = {}
            rows_without_code: list[dict] = []
            total = 0
            skip = 0
            pages = 0

            while not self.cancel_event.is_set():
                page = fetch_page(base_url, universe, skip, count, fields, self.timeout)
                total = page.total
                pages += 1
                for row in page.rows:
                    if not isinstance(row, dict):
                        continue
                    identity = self._row_identity(row)
                    if identity is None:
                        rows_without_code.append(row)
                    else:
                        rows_by_code[identity] = row

                progress = (
                    f"已读取 {len(rows_by_code) + len(rows_without_code)} 条，"
                    f"源端总数 {total}，第 {pages} 页"
                )
                self.worker_queue.put(("progress", progress))

                if not page.rows:
                    break
                skip += len(page.rows)
                if total and skip >= total:
                    break

            rows = list(rows_by_code.values()) + rows_without_code
            return AllResult(total, rows, pages, self.cancel_event.is_set())

        self._start_worker(worker, self._show_all)

    def cancel(self) -> None:
        if self.busy:
            self.cancel_event.set()
            self.status_var.set("正在停止，等待当前请求返回 ...")

    def _show_page(self, result: PageResult) -> None:
        self.current_skip = result.skip
        self.current_rows = result.rows
        self.current_total = result.total
        self.last_page_size = result.requested_count
        self.skip_var.set(str(result.skip))
        self._render_rows(result.rows)
        end = result.skip + len(result.rows) - 1 if result.rows else result.skip - 1
        page_text = f"{result.skip}～{end}" if result.rows else "无数据"
        self.summary_var.set(
            f"当前请求：{self._selected_universe()} · 记录范围 {page_text} · 返回 {len(result.rows)} 条"
        )
        self._set_stats(result.total, page_text, len(result.rows))
        self.status_var.set("当前页读取完成。选择品种后，点击“加载 K 线”查看历史列表。")
        self._update_navigation()

    def _show_all(self, result: AllResult) -> None:
        self.current_skip = 0
        self.current_rows = result.rows
        self.current_total = result.total
        self.last_page_size = len(result.rows) or self.last_page_size
        self.skip_var.set("0")
        self._render_rows(result.rows)
        self.summary_var.set(
            f"已汇总：源端 {result.total} 条 · 当前显示 {len(result.rows)} 条 · 共读取 {result.pages} 页"
        )
        self._set_stats(result.total, "全部", len(result.rows))
        self.status_var.set("读取被取消，已显示已收到的数据。" if result.cancelled else "全部读取完成。")
        self._update_navigation()

    def _render_rows(self, rows: list[dict]) -> None:
        render_rows: list[tuple[dict, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            render_rows.append((row, dict(row)))

        columns: list[str] = []
        row_keys = {
            str(key)
            for _original, view in render_rows
            for key in view
        }
        preferred = []
        for token in (token.strip() for token in self.fields_var.get().split(",")):
            if not token:
                continue
            field_name = FIELD_ID_TO_NAME.get(token, token)
            if not row_keys or field_name in row_keys or token in FIELD_ID_TO_NAME:
                preferred.append(field_name)
        for column in preferred:
            if column not in columns:
                columns.append(column)
        for _original, view in render_rows:
            row = view
            for key in row:
                key = str(key)
                if key not in columns:
                    columns.append(key)

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.row_by_item.clear()

        if not columns:
            columns = ["message"]
            self.tree.configure(columns=columns, displaycolumns=columns)
            self.tree.heading("message", text="数据")
            self.tree.column("message", width=650, anchor="w")
            self.tree.insert("", "end", values=("当前没有数据",))
            self.tree_columns = columns
            return

        self.tree_columns = columns
        self.tree.configure(columns=columns, displaycolumns=columns)
        for column in columns:
            self.tree.heading(column, text=self._column_heading(column))
            width = self._column_width(column)
            self.tree.column(column, width=width, minwidth=75, anchor="w", stretch=False)

        for original, view in render_rows:
            values = [self._display_value(view.get(column, ""), column) for column in columns]
            item = self.tree.insert("", "end", values=values, tags=(self._change_tag(original),))
            self.row_by_item[item] = original

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._on_row_selected()

    def _on_row_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        row = self.row_by_item.get(selection[0])
        if row is not None:
            code = self._normalize_kline_code(self._row_identity(row) or "")
            if code:
                if code != self.kline_code_var.get() and self.kline_rows:
                    self.kline_rows = []
                    for item in self.kline_tree.get_children():
                        self.kline_tree.delete(item)
                    self._draw_kline_chart()
                self.kline_code_var.set(code)
                name = self._display_value(row.get("name", ""))
                self.kline_summary_var.set(f"已选择  {code}  {name} · 点击加载 K 线")
                self.kline_status_var.set("代码已带入 K 线面板")

    def _load_selected_kline(self, _event=None) -> None:
        if not self.tree.selection():
            return
        self.workspace_tabs.select(self.kline_panel)
        self.query_kline()

    def _read_kline_options(self) -> tuple[str, str, int, int, int]:
        base_url = self.base_url_var.get().strip()
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("本地地址必须以 http:// 或 https:// 开头")

        code = self._normalize_kline_code(self.kline_code_var.get())
        qualified = len(code) == 8 and code[:2] in {"SH", "SZ", "BJ"} and code[2:].isdigit()
        option_qualified = len(code) == 10 and code[:2] == "SO" and code[2:].isdigit()
        option_bare = len(code) == 8 and code.isdigit()
        if not ((len(code) == 6 and code.isdigit()) or qualified or option_qualified or option_bare):
            raise ValueError(
                "K 线代码请输入 6 位数字、SH/SZ/BJ 加 6 位，或 SO 加 8 位期权合约号"
            )

        try:
            period_label = self.kline_period_var.get().strip()
            period = int(next(code for code, label in KLINE_PERIODS if label == period_label))
            fq_label = self.kline_fq_var.get().strip()
            fq = next(code for code, label in KLINE_FQ_OPTIONS if label == fq_label)
            count = int(self.kline_count_var.get().strip())
        except (ValueError, StopIteration) as exc:
            raise ValueError("K 线周期、复权和条数必须是有效数字") from exc
        if count <= 0 or count > 1000:
            raise ValueError("K 线条数必须在 1 到 1000 之间")
        return base_url, code, period, count, fq

    def query_kline(self) -> None:
        try:
            base_url, code, period, count, fq = self._read_kline_options()
        except ValueError as exc:
            messagebox.showwarning("K 线参数检查", str(exc), parent=self.root)
            return

        self.kline_code_var.set(code)
        self.kline_status_var.set(f"正在读取 {code} 的 K 线 ...")
        self._start_worker(
            lambda: fetch_kline(base_url, code, period, count, fq, self.timeout),
            self._show_kline,
        )

    def _show_kline(self, result: KlineResult) -> None:
        self.kline_rows = result.rows
        period_label = next(
            (label for value, label in KLINE_PERIODS if value == str(result.period)),
            str(result.period),
        )
        self.kline_summary_var.set(
            f"{result.code}  ·  {period_label}  ·  {len(result.rows)} 根  ·  {self._kline_range_text(result.rows)}"
        )
        self.kline_status_var.set("K 线加载完成。红色为上涨，绿色为下跌。")
        self._render_kline_rows()
        self._update_navigation()

    def _render_kline_rows(self) -> None:
        for item in self.kline_tree.get_children():
            self.kline_tree.delete(item)
        for row in self.kline_rows:
            values = [
                self._format_kline_cell(row, column)
                for column in (
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "turnover",
                    "turnover_real",
                )
            ]
            self.kline_tree.insert("", "end", values=values, tags=(self._kline_change_tag(row),))
        self._draw_kline_chart()

    def _draw_kline_chart(self) -> None:
        if not hasattr(self, "kline_canvas"):
            return
        canvas = self.kline_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        for fraction in (0.34, 0.72):
            canvas.create_text(
                width / 2,
                height * fraction,
                text="d4\ndata interface",
                anchor="center",
                justify="center",
                fill="#1a2b3d",
                font=FONT_WATERMARK,
            )
        rows = self.kline_rows[-80:]
        if not rows or width < 40 or height < 40:
            canvas.create_text(
                width / 2,
                height / 2,
                text="LOAD KLINE",
                fill="#55718f",
                font=("Consolas", 12, "bold"),
            )
            return

        quotes = []
        for row in rows:
            try:
                values = tuple(self._kline_price(row.get(key)) for key in ("open", "high", "low", "close"))
                volume = float(row.get("volume") or 0)
            except (TypeError, ValueError):
                continue
            if any(value is None for value in values):
                continue
            quotes.append((values, max(0.0, volume)))
        if not quotes:
            canvas.create_text(width / 2, height / 2, text="NO DATA", fill="#55718f", font=("Consolas", 12, "bold"))
            return

        left, right, top, bottom = 12, 58, 12, 28
        volume_height = 28
        chart_bottom = height - bottom - volume_height
        lows = [item[0][2] for item in quotes]
        highs = [item[0][1] for item in quotes]
        low_value = min(lows)
        high_value = max(highs)
        margin = max((high_value - low_value) * 0.08, 0.01)
        low_value -= margin
        high_value += margin
        value_range = max(high_value - low_value, 0.01)

        def y(value: float) -> float:
            return top + (high_value - value) / value_range * max(1, chart_bottom - top)

        for index in range(5):
            ratio = index / 4
            line_y = top + ratio * max(1, chart_bottom - top)
            price = high_value - ratio * value_range
            canvas.create_line(left, line_y, width - right, line_y, fill="#1b2b40")
            canvas.create_text(
                width - right + 5,
                line_y,
                text=f"{price:.2f}",
                fill="#6e859f",
                anchor="w",
                font=("Consolas", 8),
            )

        step = (width - left - right) / max(1, len(quotes) - 1)
        candle_width = max(3.0, min(9.0, step * 0.58))
        max_volume = max((item[1] for item in quotes), default=1.0) or 1.0
        for index, ((open_value, high_value_row, low_value_row, close_value), volume) in enumerate(quotes):
            x = left + index * step
            color = UP if close_value > open_value else DOWN if close_value < open_value else FLAT
            canvas.create_line(x, y(high_value_row), x, y(low_value_row), fill=color, width=1)
            body_top = y(max(open_value, close_value))
            body_bottom = y(min(open_value, close_value))
            if body_bottom - body_top < 2:
                body_bottom = body_top + 2
            canvas.create_rectangle(
                x - candle_width / 2,
                body_top,
                x + candle_width / 2,
                body_bottom,
                outline=color,
                fill=color if close_value != open_value else SURFACE_3,
            )
            volume_top = height - bottom - volume / max_volume * volume_height
            canvas.create_rectangle(x - candle_width / 2, volume_top, x + candle_width / 2, height - bottom, fill=color, outline="")

        canvas.create_text(left, height - 10, text=self._format_kline_date(self.kline_rows[-len(quotes)].get("date")), fill="#6e859f", anchor="w", font=("Consolas", 8))
        canvas.create_text(width - right, height - 10, text=self._format_kline_date(self.kline_rows[-1].get("date")), fill="#6e859f", anchor="e", font=("Consolas", 8))

    @staticmethod
    def _format_kline_cell(row: dict, column: str) -> str:
        value = row.get(column)
        if value is None:
            return ""
        if column == "date":
            return D4Gui._format_kline_date(value)
        if column in {"open", "high", "low", "close"}:
            price = D4Gui._kline_price(value)
            return "" if price is None else f"{price:.4f}"
        if column in {"volume", "amount"}:
            try:
                return f"{int(float(value)):,}"
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    @staticmethod
    def _kline_price(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        # D4 K 线 OHLC 使用 1/10000 价格精度；保留小数输入以兼容未来服务端格式。
        return number / 10000.0 if abs(number) > 100 else number

    @staticmethod
    def _format_kline_date(value) -> str:
        text = str(value or "")
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        if len(text) == 10 and text.isdigit():
            return f"20{text[:2]}-{text[2:4]}-{text[4:6]} {text[6:8]}:{text[8:]}"
        return text

    @staticmethod
    def _kline_range_text(rows: list[dict]) -> str:
        if not rows:
            return "暂无数据"
        return f"{D4Gui._format_kline_date(rows[0].get('date'))} → {D4Gui._format_kline_date(rows[-1].get('date'))}"

    @staticmethod
    def _kline_change_tag(row: dict) -> str:
        open_value = D4Gui._kline_price(row.get("open"))
        close_value = D4Gui._kline_price(row.get("close"))
        if open_value is None or close_value is None:
            return "flat"
        if close_value > open_value:
            return "up"
        if close_value < open_value:
            return "down"
        return "flat"

    def _set_stats(self, total: int, page_text: str, loaded: int) -> None:
        self.total_stat_var.set(f"{total:,}")
        self.page_stat_var.set(page_text)
        self.loaded_stat_var.set(f"{loaded:,}")

    def _update_navigation(self) -> None:
        normal = "normal" if not self.busy else "disabled"
        self.first_button.configure(state=normal)
        self.query_button.configure(state=normal)
        self.all_button.configure(state=normal)
        self.kline_button.configure(state=normal)
        self.previous_button.configure(
            state="normal" if not self.busy and self.current_skip > 0 else "disabled"
        )
        can_next = bool(self.current_rows) and (
            not self.current_total or self.current_skip + len(self.current_rows) < self.current_total
        )
        self.next_button.configure(state="normal" if not self.busy and can_next else "disabled")
        self.cancel_button.configure(state="normal" if self.busy else "disabled")

    @staticmethod
    def _column_heading(column: str) -> str:
        return FIELD_LABELS.get(column, "其他数据")

    @staticmethod
    def _column_width(column: str) -> int:
        if column in {"code", "price", "change_pct", "change_amt", "pre_close", "open", "high", "low"}:
            return 105
        if column in {"name", "industry_name", "contract"}:
            return 180
        return 125

    @staticmethod
    def _change_tag(row: dict) -> str:
        value = row.get("change_pct")
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "flat"
        if number > 0:
            return "up"
        if number < 0:
            return "down"
        return "flat"

    @staticmethod
    def _row_identity(row: dict) -> str | None:
        for key in ("code", "1"):
            value = row.get(key)
            if value is not None and str(value) != "":
                return str(value)
        return None

    @staticmethod
    def _normalize_kline_code(value: str) -> str:
        code = str(value or "").strip().upper()
        return code

    @staticmethod
    def _display_value(value, column: str = "") -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            return f"对象（{len(value)}项）"
        if isinstance(value, list):
            return f"列表（{len(value)}项）"
        return str(value)

    def _close(self) -> None:
        self.cancel_event.set()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="D4 用户侧证券数据浏览 GUI")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="本地程序地址，默认: %(default)s",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="单次请求超时时间（秒），默认: %(default)s",
    )
    args = parser.parse_args()

    root = tk.Tk()
    D4Gui(root, args.base_url, max(1.0, args.timeout))
    root.mainloop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d102_quickstart.py — D102 本地服务快速上手示例。

本示例只连接客户本机运行的 data_interface 服务：

    · WebSocket 推流  ws://127.0.0.1:8080/d102   （9 大订阅类型）
    · HTTP 查询       http://127.0.0.1:8080/d1/{分类路径}
    · 连接管理和数据整理由本地服务统一完成

示例不会直连外部服务，也不包含客户端密钥或内部 SDK。

运行示例：
    python d102_quickstart.py --mode ws --dry-run     # 离线演练：仅打印将发送的订阅指令
    python d102_quickstart.py --mode ws               # 连接本地服务，订阅并打印推流（默认）
    python d102_quickstart.py --mode http --dry-run   # 离线演练：打印 HTTP 表单
    python d102_quickstart.py --mode http             # 连接本地服务 /d1/ 查询
依赖：python -m pip install websocket-client
"""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WS_URL = "ws://127.0.0.1:8080/d102"      # 本地 D102 WebSocket 端点
HTTP_BASE = "http://127.0.0.1:8080"      # 本地 HTTP 端点
D102_INFO_URL = f"{HTTP_BASE}/d102/info" # 状态探活端点

# D102 WebSocket 支持的 9 大订阅类型（type -> 用途 / 是否需 codes）
SUBSCRIPTION_TYPES = {
    "daban_stock": "全市场打板/连板流（涨停板、连板梯队、封单、题材标签）",
    "daban_head":  "封板头部统计（涨停/跌停数、封板率、昨日涨停表现）",
    "daban_radar": "短线市场雷达（大单封板、炸板、急速拉升等盘口异动）",
    "ladder":      "连板高度梯队（1-5板及以上家数与晋级率）",
    "reason":      "涨停驱动原因（核心驱动事件、行业利好、公告）",
    "trends":      "指数分时走势（上证/深成/创业板分时领先线与均价）",
    "energy":      "市场情绪能量（赚钱效应、投机温度、涨跌家数比）",
    "stock":       "个股实时行情（最新价、分时快照、五档盘口、成交额）",
    "sector":      "板块/题材行情（板块排名、涨跌幅、主力资金）",
}

# 订阅演示使用的示例代码（沪市 SH + 深市 SZ，8 位大写格式）
DEMO_CODES = ["SH600519", "SZ000001", "SZ300750"]
DEMO_INDEX_CODES = ["SH000001", "SZ399001", "SZ399006"]


def build_subscribe_commands(codes=None, index_codes=None) -> list:
    """构造 9 大订阅类型的完整订阅指令。"""
    return [
        {"type": "daban_stock", "enable": 1},
        {"type": "daban_head", "enable": 1},
        {"type": "daban_radar", "enable": 1},
        {"type": "ladder", "enable": 1},
        {"type": "reason", "enable": 1},
        {"type": "trends", "codes": index_codes or DEMO_INDEX_CODES, "enable": 1},
        {"type": "energy", "enable": 1},
        {"type": "stock", "codes": codes or DEMO_CODES, "enable": 1},
        {"type": "sector", "enable": 1},
    ]


def mode_ws(dry_run: bool, listen: int, codes: list) -> None:
    print(f"[Mode A · WS] 端点: {WS_URL}")
    cmds = build_subscribe_commands(codes=codes)
    print(f"[Mode A · WS] 9 大订阅类型: {', '.join(SUBSCRIPTION_TYPES)}")
    print(f"[Mode A · WS] 将发送指令: {json.dumps(cmds, ensure_ascii=False)}")
    if dry_run:
        print("[Mode A · WS] dry-run：不建立连接，以上即完整订阅流程。")
        return

    try:
        import websocket
    except ImportError as exc:
        raise SystemExit("缺少 websocket-client，请执行：python -m pip install websocket-client") from exc

    print("[Mode A · WS] 连接本地服务 ...")
    ws = websocket.create_connection(WS_URL, timeout=10)
    try:
        print("[Mode A · WS] 已连接，发送订阅指令 ...")
        ws.send(json.dumps(cmds, ensure_ascii=False))
        print("[Mode A · WS] 已发送，等待推流（Ctrl+C 退出）...")
        received = 0
        while listen <= 0 or received < listen:
            raw = ws.recv()
            if not raw:
                break
            received += 1
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[Mode A · WS] 非 JSON 消息: {raw[:200]!r}")
                continue
            ts = data.get("ts", 0)
            for item in data.get("list", []):
                itype = item.get("type", "?")
                print(f"[{ts}] {itype}: {json.dumps(item, ensure_ascii=False)}")
        if listen > 0 and received >= listen:
            print("[Mode A · WS] 达到演示消息数上限，退出。")
    finally:
        ws.close()


# ---------------------------------------------------------------------------
def mode_a_http(dry_run: bool) -> None:
    print(f"[Mode A · HTTP] 本地服务地址: {HTTP_BASE}")
    print(f"[Mode A · HTTP] 示例 1：探活 {D102_INFO_URL}")
    if not dry_run:
        try:
            req = Request(D102_INFO_URL, headers={"Accept": "application/json"})
            with urlopen(req, timeout=5) as response:
                info = json.loads(response.read().decode("utf-8"))
            print(f"[Mode A · HTTP] /d102/info -> {json.dumps(info, ensure_ascii=False)}")
        except Exception as exc:  # 本地服务未启动或未授权时给出明确提示
            print(f"[Mode A · HTTP] 探活失败（请确认本地服务已启动且 D102 可用）: {exc}")

    # 业务查询：POST /d1/{分类路径}，操作由表单字段 a 指定，c 为中性模块标识
    form = {
        "a": "GlobalCommon",   # 操作标识（全球指数-全球通用）
        "c": "d1",             # 中性模块标识（由管理后台目录提供）
        "View": "1,2,3,4,5,6", # 业务参数：关注的指数视图
    }
    print(f"[Mode A · HTTP] 示例 2：POST {HTTP_BASE}/d1/hq 表单: {json.dumps(form, ensure_ascii=False)}")
    if dry_run:
        print("[Mode A · HTTP] dry-run：不发起网络请求，以上即完整请求流程。")
        return

    try:
        body = urlencode(form).encode("utf-8")
        req = Request(
            f"{HTTP_BASE}/d1/hq",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as response:
            print(f"[Mode A · HTTP] HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
        print(f"[Mode A · HTTP] errcode={payload.get('errcode')} errmsg={payload.get('errmsg', '')}")
        print(f"[Mode A · HTTP] 响应摘要: {json.dumps(payload, ensure_ascii=False)[:600]}")
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"[Mode A · HTTP] 请求失败: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="D102 本地服务快速上手示例")
    parser.add_argument("--mode", choices=["ws", "http"], default="ws",
                        help="接入模式：ws=本地 WebSocket 推流，http=本地 HTTP 查询")
    parser.add_argument("--dry-run", action="store_true",
                        help="离线演练：只打印将发送的指令/请求，不建立网络连接")
    parser.add_argument("--listen", type=int, default=5,
                        help="ws 模式最多接收的推流消息数（0 表示不限）")
    parser.add_argument("--codes", nargs="*", default=DEMO_CODES,
                        help="ws 模式 stock 订阅的股票代码（默认: %(default)s）")
    args = parser.parse_args()

    if args.mode == "ws":
        mode_ws(args.dry_run, args.listen, args.codes)
    else:
        mode_a_http(args.dry_run)


if __name__ == "__main__":
    main()

# data-interface 用户侧示例

这是面向客户和 AI 助手的用户侧示例仓库。示例通过本机运行的
`data_interface` 服务访问数据和管理接口，不包含主程序源码、内部构建流程、
客户端密钥或独立直连 SDK。

## 30 秒开始

先启动 `data_interface` 并完成登录，然后在本仓库根目录执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

先做不联网自测：

```bash
python admin/ai_control.py --help
python websocket/d102_quickstart.py --mode ws --dry-run
python websocket/d102_quickstart.py --mode http --dry-run
```

服务已经启动并登录后，可以运行：

```bash
python admin/ai_control.py status
python admin/ai_control.py smoke
python websocket/d102_quickstart.py --mode ws --listen 5
python websocket/d102_quickstart.py --mode http
```

`smoke`、数据查询和 WebSocket 示例会访问本机服务；没有本地服务时，先运行
`--help` 或 `--dry-run`，不会伪造行情结果。

## 目录

| 目录 | 内容 | 默认依赖 |
| --- | --- | --- |
| `admin/` | 无界面管理、登录、启停和基础探活 | Python 标准库 |
| `http/` | D1、D4、D6 用户侧数据工作台 | 标准库；D6 需要 `websocket-client` |
| `websocket/` | D101、D102、D201、D202 实时数据示例 | `websocket-client` |
| `docs/` | 面向客户的运行说明 | 无 |

## 示例索引

### 管理和 AI 自动化

`admin/ai_control.py` 支持以下命令：

```text
status       查看管理端状态
login        使用环境变量登录
register     使用环境变量注册
recharge     使用环境变量充值
web-off      关闭管理页 Web 服务
start        启动本地数据服务
stop         停止本地数据服务
smoke        执行管理端和 D102 探活
```

凭据只从环境变量读取，不要把真实账号、密码或卡密写入脚本、Issue、日志或
提交记录。无界面服务器示例：

```bash
export DI_PHONE='你的手机号'
export DI_PASSWORD='你的密码'
export DI_CARD_KEY='需要充值时再设置'
python admin/ai_control.py login
python admin/ai_control.py start --port 8080
python admin/ai_control.py smoke
```

PowerShell 使用 `$env:DI_PHONE`、`$env:DI_PASSWORD` 和 `$env:DI_CARD_KEY` 设置
同名环境变量。

### D102

`websocket/d102_quickstart.py` 只演示通过本机服务接入：

- WebSocket：`ws://127.0.0.1:8080/d102`
- HTTP：`http://127.0.0.1:8080/d1/{分类路径}`

它不包含独立客户端模式，也不会绕过本机服务直连外部地址。需要连接自定义
端口时，可以在代码中修改本地地址，或按项目后续版本提供的参数运行。

### D201 / D202

```bash
python websocket/d201_l2_csv.py --help
python websocket/d201_batch_buysell.py --help
python websocket/d202_snapshot_auction.py --help
```

采集结果请放到 `output/` 或通过 `--output` 指定到仓库外部；仓库已经忽略
CSV、JSONL 和运行日志，避免把实时数据提交到公开仓库。

## GUI 示例

Windows、macOS 和 Linux 均可尝试运行 Tkinter 工作台。桌面环境不可用时，使用
管理脚本和 `--dry-run` 示例即可完成服务器自测。

```bash
python http/d1_gui.py
python http/d4_gui.py
python http/d6_gui.py
python websocket/d101_gui.py
python websocket/d201_gui.py
python websocket/d202_gui.py
```

## AI 使用约定

让 AI 操作本仓库时，建议先执行：

```bash
python admin/ai_control.py --help
python websocket/d102_quickstart.py --mode ws --dry-run
```

然后再根据实际状态执行 `status`、`login`、`start` 或 `smoke`。AI 不应猜测账号
信息、授权状态、端口或行情结果；遇到失败时先保留状态码和错误摘要，再检查
本地服务是否运行和授权是否有效。

## 兼容性

- Python 3.10 或更高版本；
- GUI 示例需要系统提供 Tkinter；
- WebSocket 示例需要 `websocket-client`；
- 默认管理端口为 `9527`，数据服务端口为 `8080`；
- 所有默认网络地址均指向 `127.0.0.1`。

## 许可证

示例代码使用 MIT License，见 [LICENSE](LICENSE)。主程序、安装包和未列入本仓库
的内部组件不因本示例仓库而改变其授权范围。

# 贡献指南

提交前请在仓库根目录运行：

```bash
python -m compileall -q examples tests
python examples/automation/ai_control.py --help
python examples/cli/d102_quickstart.py --mode ws --dry-run
python examples/cli/d102_quickstart.py --mode http --dry-run
```

提交内容应保持用户侧范围：只连接本机 `data_interface` 服务，不加入账号、密码、
令牌、抓包、实时数据、内部配置或独立直连实现。新增示例请说明：用途、Python
版本、依赖、启动命令、预期输出和无界面服务器替代方案。

# DSL 帧转换独立工具

`rebuild_uslp_dsl_frame.py` 仅依赖 Python 标准库，可单独复制到其他项目运行。
此目录不属于 TelecommandTool 的应用源码或打包资源，不随 EXE 构建。

```shell
python rebuild_uslp_dsl_frame.py ../app
```

输入路径相对于运行时的当前工作目录；具体目录规则和 CSV 格式见脚本说明。

当前脚本保留了原项目的 `E0 FF FF` 兼容布局。按 CCSDS USLP 规则 111，
标准布局应仅使用 `E0`，不带两字节指针；本次目录整理未改变协议行为。

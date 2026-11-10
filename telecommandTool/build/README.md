# USLP 遥控帧生成器


## 工程结构与维护

```text
telecommandTool/
├─ src/                         # Python源码与命令行入口
│  ├─ web_server.py              # HTTP入口与请求分发
│  ├─ *_generator.py            # 各类帧生成器
│  ├─ uslp_common.py             # 公共帧封装工具
│  └─ tests/                    # 回归测试
├─ frontend/index.html          # 前端表单、HEX及协议字段展示
├─ build/                       # 构建脚本和Markdown文档
│  ├─ build.ps1 / build-win7.ps1
│  ├─ clean.ps1
│  ├─ README.md / WIN7_BUILD.md
│  └─ work*/ / spec*/           # 可清理的构建中间文件
├─ .build-packages/             # Win7离线构建依赖
└─ dist/                       # 可执行程序
```

以下命令均从工程根目录运行。启动页面与运行测试：

```powershell
python src/web_server.py
python -B -m unittest discover -s src/tests -t src -v
```

统一发布名称为 `dist\TelecommandTool-V<version>.exe`，Win7版为 `dist\TelecommandTool-Win7-x64-V<version>.exe`。打包前关闭相应程序的服务窗口，避免文件占用；不再把 `-fixed` 作为日常版本名称。构建脚本将自动生成的spec文件放在构建目录。
Each packaging run increments the final version component before building and uses that version in the EXE filename.

清理构建缓存及历史修复产物：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\clean.ps1
```

清理脚本保留源码、测试、离线依赖和标准发布EXE；仅当fixed版与标准版字节一致时删除fixed副本，遇到占用则保留并提示。关闭旧fixed服务后可再次运行。`.gitignore`不影响已经跟踪的文件，首次清理产生的缓存/spec删除记录应随工程整理一并提交。

## 重新打包

### Windows 7 兼容版

如果目标电脑提示缺少 `api-ms-win-core-path-l1-1-0.dll`，通常是因为目标系统为 Windows 7，而程序使用了 Python 3.9 或更高版本打包。请使用 **64 位 Python 3.8.10** 和 **PyInstaller 5.13.2** 重新打包；不要从其他电脑复制该 DLL 到系统目录。

1. 安装 64 位 Python 3.8.10。
2. 使用该 Python 安装指定版本的打包工具：

   ```powershell
   C:\Python38\python.exe -m pip install pyinstaller==5.13.2
   ```

3. 在项目目录运行兼容版打包脚本：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build-win7.ps1 -PythonPath C:\Python38\python.exe
   ```

输出文件为 `dist\TelecommandTool-Win7-x64-V<version>.exe`。目标电脑还应安装 Windows 7 SP1 和系统可用的最后一批更新。由于 Windows 7 和 Python 3.8 均已停止官方维护，该版本仅用于兼容无法升级的设备。

### Windows 10/11 版

在 **Windows 64 位**电脑上打包。打包电脑需要 Python 和 PyInstaller；运行打包后的程序的电脑不需要安装 Python。

1. 安装 Python，并确认在 PowerShell 中运行 `python --version` 能显示版本号。
2. 安装打包工具：

   ```powershell
   python -m pip install pyinstaller
   ```

3. 在项目目录运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build.ps1
   ```

完成后，可执行文件位于 `dist\TelecommandTool-V<version>.exe`。将这个 `.exe` 复制到目标 Windows 电脑即可使用；`index.html`、全部帧生成模块及公共模块已打包在其中。每次修改页面或 Python 代码后，重新运行上述打包命令。

## 如何使用

1. 双击 TelecommandTool-V<version>.exe。程序会启动本地服务，并在默认浏览器打开 http://127.0.0.1:8000。如果浏览器没有自动打开，可手动输入该地址。
2. 选择需要的功能页：普通遥控帧、普通文件上注、ST11 时间调度、直接指令、高速遥控、高速文件上注或高速空闲帧。
3. 填写参数或选择文件后点击“生成帧”。数值字段支持十进制或 0x 开头的十六进制；HEX字段支持空格分隔。文件上注会按页内配置自动拆成多帧。
4. 结果区可切换查看各帧。点击帧结构分段或字段，可高亮对应字节；支持复制整帧 HEX、复制数据区 HEX及下载对应数据。文件上注还提供 Excel 或 422 BIN 导出。
5. 点击“刷新当前页”可清除当前功能页的数据。高速遥控和高速文件上注切换后会分别保留各自上次输入。
6. 关闭程序窗口即可停止服务。若 8000 端口已被占用，请先关闭占用该端口的程序。

开发环境中也可运行 python src/web_server.py 启动同一页面。
## 功能和能力

工具提供七种组帧模式：

| 功能页 | 能力概述 | 输出与导出 |
| --- | --- | --- |
| 普通遥控帧 | 按 SCID、VCF、PID、PCAT、服务类型/子类型、指令码和参数生成单帧低速 USLP 遥控帧 | HEX预览、复制整帧、BIN下载 |
| 普通文件上注 | 上传文件并按可配置参数长度拆包，默认指令码 0x5F01 | 多帧导航；逐帧BIN或含两张工作表的Excel |
| ST11 时间调度 | 生成启用、禁用、重置、插入、删除、时间转移和摘要请求 | HEX预览、复制整帧、BIN下载 |
| 直接指令 | 输入9字节指令码，自动添加同步字并重复两次，生成 TC(2,1) | HEX预览、复制整帧、BIN下载 |
| 高速遥控 | 生成1020字节高速 TC(2,2) 帧，可选VCID、MAP ID、分段标志和序列计数 | HEX预览、复制整帧/数据区、BIN下载 |
| 高速文件上注 | 通过HEX或文件输入，自动分段组帧；可选择是否把文件数据封装为422格式 | 多帧导航、复制整帧/数据区、下载整帧/数据区、Excel或422 BIN |
| 高速空闲帧 | 生成含977字节PN序列的1020字节高速空闲帧 | HEX预览、复制整帧、BIN下载 |

所有模式的结果均为原始 USLP 帧，不自动发送；可视化解析器展示帧主导头、安全头、TFDF、PUS包、数据区、填充、安全尾和FECF等字段。多帧结果按生成顺序显示，可逐帧查看。不同功能页的输入按页面管理；点击“刷新当前页”会清除当前页输入和生成结果。

### 普通文件上注

选择文件后，工具按“限制参数长度”拆分数据，默认勾选并以 450字节为每帧参数长度，可自定义 1..452字节；取消勾选时使用452字节上限。指令码默认 0x5F01，可编辑。每个文件分段分别生成一帧，VCF按帧顺序递增。

导出类型可选：

- BIN：每帧独立下载，文件名按帧顺序添加序号。
- Excel：一个工作簿包含“整帧数据”和“数据域”两个工作表，每帧一行。

### 高速遥控与高速空闲帧

页面新增“高速遥控”和“高速空闲帧”，命令行分别使用 `high_speed_frame_generator.py`、`high_speed_idle_frame_generator.py`。输出仍是未加扰、未做Turbo编码、不含ASM/CLTU的原始USLP帧，不自动发送。

| 字段 | 高速遥控 | 高速空闲 |
|---|---|---|
| 帧长 / 长度字段 | 1020字节 / 03FB | 1020字节 / 03FB |
| VCID | 默认10，可选10、5、4、63 | 63 |
| MAP ID | 14（大容量）或1（指令/注入） | 0 |
| VCF | 1字节，0..255 | 1字节，0..255 |
| 安全头 / 尾 | 14 / 16个5A | 14 / 16个5A |
| 构造规则 / UPID | 001 / 00000 | 001 / 00000 |
| 最后有效字节指针 | PUS包长度减1 | FFFE |
| TFDZ | 977字节：一个PUS包，剩余补AA | 977字节PN，无PUS包 |

高速业务包后台固定TC(2,2)，只输入完整应用数据HEX（0..964字节），原样组包，不自动添加0x5001/0x5F01。支持包序列计数0..16383和分段标志；当前生成一帧，不自动切分文件。AA填充在包ECF之后，不计入包长及包ECF，但计入帧FECF。

PN使用D^0+D^1+D^2+D^22+D^32，全1初态、MSB先出，每帧重置。前20字节为 `FF FF FF FF 6D B6 D8 61 45 1F 11 F1 97 16 72 3C BE 7E 00 B1`。

协议来源：用户提供的《XY-1_辅助变轨灵巧服务飞行器遥控实施方案_详细解读.md》及同目录Markdown转换原文。按“原低速/ST11实现优先”处理冲突：

- SCID默认FF01、源ID固定07F6、CRC沿用现有实现；不改原来的两个生成文件。
- 空闲正文写4字节VCF，但与1020字节帧、977字节TFDZ及其他段长度不相容。采用原实现1字节VCF，使8+14+3+977+16+2=1020。
- 空闲UPID正文为00000、图示为11111；采用正文与现有实现一致的00000。
- 高速正文有“TFDF=977”与“TFDZ=977”两种写法；采用TFDZ=977、TFDF=980，与总长相符。
- 按后续用户要求，高速应用数据改为原样输入，按977字节TFDZ减13字节PUS开销限制为964字节，不再套用普通遥控指令码/参数格式。
- 非零MAP按4位MAP ID加1位主导头结束标志编码；旧模块MAP固定0，原有字节不变。

```powershell
python src/high_speed_frame_generator.py --app-data "01 02 03" --output high.bin
python src/high_speed_idle_frame_generator.py --vcf 255 --output idle.bin
python -B -m unittest discover -s src/tests -t src -v
```

### 高速文件上注

支持直接输入应用数据HEX或上传文件；选择文件时优先使用文件内容，文件会自动拆分为多帧。每帧1020字节，TFDZ为977字节，其中PUS主、副导头共11字节、包ECF为2字节，因此应用数据区最多964字节。每帧应用数据保留 0x5F01 前缀。

“添加422帧格式（0XEB90）”默认勾选。勾选时应用数据格式为 5F01 EB90 0F + 两字节有效数据长度 + 文件数据 + 累加和，每帧最多承载956字节文件数据；累加和从类型字0x0F起计算，不包含帧头EB90。取消勾选时仍保留5F01，每帧最多承载962字节文件数据，不附加422子帧。

分段标志选择11时，所有生成帧均按独立包处理，序列计数保持0；选择其他标志时，拆分帧按首段、延续段和尾段规则设置标志，VCF逐帧递增。

生成后可以逐帧浏览、复制整帧HEX或数据区HEX，并下载整帧/数据区BIN。下载 Excel会生成三个工作表：整帧数据、有效TFDF数据、422数据；最后一帧的422数据包含完整TFDF及填充字节。下载 422 BIN将各帧422数据按帧顺序连续写入一个BIN文件。
### 测控编程数据专用处理

在“高速文件上注”页面底部可单独选择测控编程数据文件并生成DAT。该入口按固定522字节一条记录处理，每条记录生成独立的1020字节高速单帧单包；应用数据为5F01加原始记录，不添加422格式。参数固定为PID=49、PCAT=0x03，其余使用高速帧默认值；每帧TFDZ剩余位置以AA填充。所有生成帧保持默认VCF=0、独立包标志11和序列计数0，最终按记录顺序合并到一个DAT文件。文件长度必须是522字节的整数倍。
### USLP 直接指令帧

选择“直接指令”，填写一份9字节的指令码HEX（不含同步字）。每份前自动添加固定同步字 `2C 79 5E`，TC(2,1)应用数据合计24字节。程序自动将同步字和同一份指令码重复两次，不截断或补齐指令码。

VCID固定为4，安全头为6个 `5A`，安全尾沿用低速帧的16个 `5A`；无插入区、无OCF，帧长上限510字节。其余字段沿用低速规则，源ID固定为 `07 F6`。当前完整PUS包37字节，完整帧72字节。页面支持逐份展开同步字和指令码。

命令行示例（指令码仅用于演示）：

```powershell
python src/direct_command_frame_generator.py --command-code "00 01 02 03 04 05 06 07 08" --output direct.bin
```

新增公共封装层位于 `uslp_common.py`，复用已有PUS包编码和CRC方法，原低速和ST11生成文件保持不变。

### 普通低速遥控帧

设置 SCID、VCF、PID、PCAT、PUS 服务类型、消息子类型、指令码及参数字节，生成单个低速 USLP 遥控帧。PUS 包长度、包 CRC、帧长度和帧 CRC 由程序计算。

### ST11 时间调度帧

支持以下 TC(11) 指令：

| 指令 | 子类型 | 页面可填写内容 |
| --- | --- | --- |
| 启用 | 1 | 公共帧参数 |
| 禁用 | 2 | 公共帧参数 |
| 重置 | 3 | 公共帧参数 |
| 插入活动 | 4 | 子调度表 ID，以及一条或多条活动的释放时间、内层 TC 字段和应用数据 |
| 删除活动 | 6 | 时间窗口及子调度表 ID 列表 |
| 时间转移 | 8 | 时间偏移、时间窗口及子调度表 ID 列表 |
| 摘要请求 | 14 | 最多 5 个子调度表 ID |

时间标签和活动释放时间采用从 **2020-01-01 00:00:00 UTC** 起算的秒数。时间窗口类型支持全部时间、起止时间、从指定时间起、至指定时间止。页面会按活动或 ID 数量自动填写协议中的计数字段。

所有多字节字段按大端序编码。输出是**未加扰、未做信道编码、不含 CLTU** 的原始 USLP 帧；页面提供 HEX 预览、复制和二进制下载。

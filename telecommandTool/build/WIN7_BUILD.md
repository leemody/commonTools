# Windows 7 x64 构建与运行

目标：Windows 7 SP1 64位；构建解释器采用Python 3.8 x64，打包器固定PyInstaller 5.13.2。32位Windows不能运行此EXE。

```powershell
.\build\build-win7.ps1 -PythonPath 'C:\Python38\python.exe'
```

若项目内已配置构建环境，可从工程根目录运行：

```powershell
.\build\build-win7.ps1 -PythonPath '.\.build-env-py38\python.exe'
```

不传参数时依次使用环境变量`TELECOMMAND_WIN7_PYTHON`、工程内`.build-env-py38\python.exe`、本机已验证的`D:\PythonLandControl\telecommandTool\.build-env-py38\python.exe`、`py -3.8`、PATH中的`python`。如找到的解释器不是Windows Python 3.8 x64，构建会拒绝继续，不会生成误标为Win7的新版Python产物。

构建会检查应用导入、运行src/tests中的回归测试，随后将最新frontend/index.html和所有生成模块打包。输出：

- `dist\TelecommandTool-Win7-x64-V<version>.exe`：单文件程序，目标机无需安装Python。
The build script increments the final version component before packaging and uses the new version in both output filenames.
- `dist\TelecommandTool-Win7-x64-V<version>.build.json`：构建版本、源码哈希和EXE SHA256，便于确认是否拿到了最新文件。

把EXE复制到Win7电脑后运行，浏览器访问`http://127.0.0.1:8000`；关闭服务窗口即可退出。端口8000应未被其他版本占用。页面使用现代JavaScript，请使用支持该页面语法/API的浏览器，不支持Win7自带IE。EXE兼容性和浏览器兼容性需分别确认。

本次使用Python 3.8.10 x64 / PyInstaller 5.13.2在当前Windows主机构建。目标系统需具备Python 3.8运行所需的系统更新及运行库；本机启动和API检查不能替代Win7实机验收。

参考：[Python Windows支持说明](https://docs.python.org/3/using/windows.html)、[PyInstaller 5.13.2平台说明](https://pypi.org/project/pyinstaller/5.13.2/)。后者说明Win7预期可用，但其正式支持范围为Windows 8及以上，因此发布前仍应在实际Win7环境确认。

当前机器可以从工程根目录直接执行 `.\build\build-win7.ps1`；从 commonTools 工作区根目录执行 `.\telecommandTool\build\build-win7.ps1`。手动传入 `-PythonPath` 仍优先。

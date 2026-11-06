OpenAgentCU 1.0.0
==================

一、安装版
  双击 OpenAgentCU-1.0.0-Setup.exe
  - 默认安装到 C:\Program Files\OpenAgentCU，需要管理员权限（UAC 确认一次）
  - 安装完成后可从开始菜单启动（可选创建桌面快捷方式）
  - 卸载：Windows 设置 → 应用 → OpenAgentCU
  - 如果提示“无法创建目录”，请改双击同目录下的 install.bat
    （它会把临时目录指到 C:\Users\Public 后再启动安装器）
  - 仍然失败时，请直接使用下面的便携版

二、便携版
  解压 OpenAgentCU-1.0.0-portable.zip 到任意目录
  双击 OpenAgentCU.exe 启动
  不要删除同目录下的 _internal 文件夹

三、命令行
  安装目录下自带 oacu.exe，例如：
    oacu.exe doctor
    oacu.exe scan
    oacu.exe plan "点击记事本"
    oacu.exe act "点击七" --inproc

四、数据位置
  默认：%APPDATA%\OpenAgentCU
  如果该目录不可写，程序会自动回退到 %LOCALAPPDATA%\OpenAgentCU、
  C:\Users\Public\OpenAgentCU、用户目录下的 .opencu 或当前目录下的 .opencu。
  数据库为 oacu.db，IR 文件在 ir\ 子目录。

五、MCP
  打开 GUI 的「MCP / 设置」页，点击「复制配置」粘贴到 MCP 客户端。
  命令行等价方式：
    oacu.exe mcp serve

六、系统要求
  Windows 10/11 x64，PowerShell 5.1（系统自带）。
  不需要单独安装 Python。

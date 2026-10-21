# AutoStep

在后台潜伏，到点自动在你指定的应用里按录制好的顺序点击 / 输入 / 发送按键。内置 **ChatGPT 桌面应用的 Codex 界面**，也能换成别的应用——每个动作序列各挂一条「应用档案」，写着怎么认窗口、怎么输入、按什么键发送。

简体中文 | [English](README.en.md)

---

## 一、安装

### 方式 A：直接下载 exe（不用装 Python）

到 [Releases](https://github.com/rightevil/AutoStep/releases) 下载 `AutoStep-*-win64.zip`，解压到任意**可写**目录（别放 `C:\Program Files` 下），双击 `AutoStep.exe` 即可。

- 单文件、无控制台窗口，不依赖 Python 环境；
- 首次运行会在 exe 同级生成 `data/` 存序列、计划和日志；该目录不可写时自动改用 `%APPDATA%\AutoStep`；
- 升级时用新 exe 覆盖旧的即可，`data/` 不动。

### 方式 B：从源码运行

```bash
git clone https://github.com/rightevil/AutoStep.git
cd AutoStep
mise install        # 装 Python 3.13（已在 mise.toml 里锁版本）
mise run install    # 建 .venv + 装依赖
```

依赖只有 5 个：mss、Pillow、pywin32、pyperclip、pystray，总共十几 MB。界面用 Python 自带的 tkinter，无需额外安装；打包用 PyInstaller（只有出包时需要，见 `.github/workflows/release.yml`）。

## 二、启动

在项目目录下执行：

```bash
mise run start
```

没有 mise 的话，直接用 venv 里的解释器（`pythonw` 不带控制台窗口，适合常驻后台）：

```bash
.venv\Scripts\pythonw.exe main.py
```

调试想看到 traceback 就把 `pythonw` 换成 `python`：

```bash
.venv\Scripts\python.exe main.py
```

程序启动后是普通窗口，关闭窗口默认缩到右下角托盘继续待命；托盘图标右键可「显示主窗口 / 试运行当前序列 / 退出」。想让命令行一执行就进后台，可以给它建个快捷方式（目标填 `pythonw.exe main.py` 的完整路径）或勾上界面里的「开机自动启动」。

## 三、目标应用与录制动作

**先选档案。** 每个动作序列各挂一条「应用档案」，档案里写着：怎么认出这个应用、怎么输入、按什么键发送。所以同一个程序可以同时伺候多个应用，互不干扰。

| 档案字段 | 说明 |
|---|---|
| 档案名称 | 给你看的标签，随便起 |
| 进程名 | 包含匹配，填 `ChatGPT` 就能匹配 `ChatGPT.exe` |
| 标题含（可空） | 同名进程多开时用来区分 |
| 输入方式 | `auto` 含中文走剪贴板 / `keys` 一律逐键 / `paste` 一律粘贴 |
| 输入前 Ctrl+A 清空 | 防止在旧内容后面接着打 |
| 发送键 | `enter` / `ctrl+enter` 等，供「+ 发送」动作使用 |

- **新建档案**：点「新建档案」填表；或先把应用切到前台，再从「从窗口列表选择」里挑一个，程序会把该窗口的进程名写进当前档案。
- **切换档案**：顶部「档案」下拉，只改**当前选中的这条序列**，别的序列不受影响。
- 档案存在 `data/profiles.json`，是普通 JSON，可以手改、备份、跟别人交换。

**再录动作：**

1. **+ 点击**：程序会先激活目标窗口并抓一张客户区截图，铺一层覆盖层；用鼠标**拖拽框选**要点的区域，松开即记录。框选时 Esc 或右键取消。
2. **+ 输入**：同样先框选输入框位置，再在弹窗里填要打的文本（中英混排、多行都支持）。确定后自动带上「Ctrl+A 先清空」。
3. **+ 发送**：按当前档案里设置的发送键发出去（默认 `enter`）。**这一步别忘**，光输入不发出去等于没执行。
4. **+ 按键**：需要更特殊的键（`tab`、`ctrl+a` 之类）时用它。
5. 列表里可双击编辑、上移下移调整顺序，顺序就是执行顺序。
6. 一个「动作序列」就是一套完整动作，可新建多套、可重命名、可删除。计划引用序列，多条计划可以共用同一套动作。

坐标存的是**相对窗口客户区的百分比**，所以窗口移动、最大化/还原、改分辨率都不会错位。

> 从旧版本升级：原来那个全局目标会自动变成一条「原设置」档案挂到已有序列上，动作不用重录。

## 四、设计划

点「+ 新计划」：名称、日期（点「📅 选择」用月历挑，不用手打）、时间（小时/分钟下拉，也可直接改）、重复方式、用哪个动作序列。

**只由你决定这一条计划怎么跑**，程序不自作主张：

- 「只跑一次」：到点执行一次，之后状态变「已完成」，**计划记录保留不删**，可以手动再启用。
- 「每天同一时间」：每天到点执行一次，跨过的日期不补跑，不会一次连打好几遍。
- **计划随时可编辑**：选中 → 「编辑」（或双击行），能改名称、日期、时间、重复方式、用哪套动作；改完自动重新排期，新时间在未来就恢复待执行。
- 动作序列名称也可重命名（序列那行的「重命名」）。
- 计划表里能看到用的是哪套动作、状态（待执行 / 已完成 / 已停用 / 已过期）、下次触发时间、上次结果。

## 五、执行设置

| 项 | 说明 |
|---|---|
| 步间固定延时 | 每两步之间等待多少秒。日志里查询这类操作建议 ≥1.5 |
| 激活后等待 | 窗口切前台后额外等多久 |
| 输入方式 | **跟着档案走**，这里只显示当前档案用的哪一种 |
| 执行后截图存证 | 存到 `data/shots/` |
| 执行前唤醒系统 | 到点前 90 秒用可等待定时器把系统从睡眠唤醒 |
| 关闭窗口时缩到托盘 | 关窗后调度器仍活着 |
| 开机自动启动 | 写 `HKCU\...\CurrentVersion\Run` |

输入方式、清空、发送键这些「跟应用相关」的项已经搬进档案，全局设置里只留「跟节奏和系统相关」的项。

## 六、必须知道的限制

1. **锁屏就没法执行。** 系统睡眠唤醒后如果停在锁屏界面，鼠标点击会打在锁屏上。程序会检测并记日志"当前处于锁屏状态"，不会假装成功。
   → 想让它稳定跑，把「电源选项 → 唤醒时需要登录」设为**从不**。
2. **执行期间别动鼠标键盘**，会抢焦点导致后续步骤错位。程序每步都会校验前台窗口，被抢走会尝试抢回，抢不回就中止并记日志。
3. **框选时目标窗口必须在最前面**，程序会自己激活它，但如果有别的窗口置顶遮挡，截到的是遮挡物。
4. 托盘程序必须保持运行，退出即不再执行。
5. 仅支持 Windows：`core/winsys.py` 与 `core/executor.py` 里的 Win32 调用没有跨平台兜底。

## 七、日志与文件

```
data/store.json     所有序列 / 计划 / 设置
data/profiles.json   应用档案（可手改）
data/logs/*.log     每日运行日志
data/shots/*.png    执行后截图
```

源码运行时这些文件在项目目录下；用打包的 exe 时在 **exe 同级**（不可写则退回 `%APPDATA%\AutoStep`，实际路径写在当天日志第一行）。这些都已被 `.gitignore` 忽略——里面是你的提示词和计划。

## 八、自测

```bash
.venv/Scripts/python.exe tests/smoke.py        # 核心逻辑 + 档案迁移 + 系统层（45 项）
.venv/Scripts/python.exe tests/integration.py  # 真实点击/中文输入，含档案驱动模式（9 项，接管鼠标约 12 秒）
.venv/Scripts/python.exe tests/schedule_e2e.py # 定时自动触发全链路（6 项，接管鼠标约 10 秒）
```

`tests/ui_shot.py`、`tests/ui_profile_shot.py`、`tests/dialog_shot.py` 会把主界面和对话框渲染成 PNG 存到 `data/shots/`，用于核对布局；`ui_profile_shot.py` 用的是临时数据，不会碰你的 `data/store.json`。

## 九、结构

```
main.py              入口：DPI 声明、单实例、启动 UI
core/config.py       路径、默认设置、应用标识（APP_NAME / APP_ID 唯一来源）
core/profile.py      应用档案：认窗口 / 输入方式 / 发送键 / 预留的 verify
core/winsys.py       窗口枚举/激活、坐标换算、防休眠、系统唤醒、锁屏检测
core/capture.py      客户区截图 + 拖拽框选覆盖层
core/executor.py     动作回放（点击 / Unicode 逐字符 / 剪贴板粘贴 / 组合键）
core/scheduler.py    定时循环 + 唤醒布防
core/store.py        JSON 持久化与下次触发时间计算
core/ui.py           主界面、对话框、托盘图标
core/icon.py         图标绘制（托盘与 exe 图标共用）
tools/make_icon.py   生成 assets/autostep.ico
AutoStep.spec        PyInstaller 打包配置
```

## 十、打包与发版

推一个 `v*` tag 就会自动出包并发 Release：

```bash
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` 在 `windows-latest` 上依次做：装依赖 → 语法与导入检查 → 按 `AutoStep.spec` 打单文件 exe → 压成 `AutoStep-<版本>-win64.zip` → 建 Release 上传。也可以在 Actions 页面手动触发 `release` 工作流并填版本号。

> 托管 runner 上没有交互式桌面，所以 `tests/integration.py`、`tests/schedule_e2e.py` 这类会接管鼠标的测试不在 CI 里跑，只做编译与导入检查。

本地出包（一般不需要，发版交给 Actions）：

```bash
.venv/Scripts/python.exe -m pip install "pyinstaller>=6.6"
.venv/Scripts/python.exe tools/make_icon.py   # 重新生成 assets/autostep.ico
.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean AutoStep.spec
# 产物：dist/AutoStep.exe
```

## 许可证

MIT

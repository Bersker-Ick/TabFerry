# TabFerry

[English](README.md) | **简体中文**

> 把桌面浏览器的标签页"摆渡"到手机上 —— 离线可用、可逐条处理、自托管。

TabFerry 读取桌面浏览器里已经打开的标签页，生成一个单文件手机页面并在局域网里
提供服务。手机打开后可以搜索、点开、把处理完的条目移出列表。下载离线副本后，
电脑关机也能继续用；服务器会把"已移除"状态写入磁盘，重启不丢。

```
浏览器会话  ──导入──▶  tabs.json  ──serve──▶  手机（搜索 / 打开 / 移除）
                              │
                              └──导出──▶  单文件 HTML（离线）
```

## 特性

- **一条命令导入** —— 支持 Firefox 会话存储、Chromium 系（Chrome / Edge /
  Brave / Chromium）的 SNSS 会话文件，也支持纯文本和 JSON。
- **移动端优先的页面** —— 搜索、点标题打开、点 `×` 移除。
- **中英文界面** —— 根据浏览器语言自动选择，也可用 `?lang=zh` / `?lang=en`
  强制指定。
- **离线副本** —— 单个自包含 HTML，不需要服务器。
- **状态持久化** —— 移除记录原子写入 `state.json`。
- **零运行时依赖** —— 只用 Python 标准库。
- **自托管** —— 一个小 HTTP 服务，适合 Docker / systemd。
- **可扩展** —— 新增浏览器只需实现一个类。

## 快速开始

```bash
pipx install git+https://github.com/Bersker-Ick/TabFerry.git
tabferry import     # 自动探测 Firefox
tabferry serve      # 打印局域网地址
```

Chrome / Edge / Brave 用户：

```bash
tabferry import --source chromium
```

手机和电脑在同一 Wi-Fi 下，打开打印出来的地址即可。不用 pipx 的话：

```bash
git clone https://github.com/Bersker-Ick/TabFerry.git
cd TabFerry
python -m pip install .
tabferry import
tabferry serve --host 0.0.0.0 --port 8123
```

需要 Python 3.9 或更高版本。

## 用法

### 导入

```bash
tabferry import                                      # 最新的 Firefox 会话
tabferry import --profile ~/.mozilla/firefox/abc.default
tabferry import --source chromium                   # 最新的 Chrome/Edge/Brave
tabferry import --source chromium --browser edge
tabferry import --source chromium --profile "C:\Users\me\AppData\Local\Google\Chrome\User Data\Default"
tabferry import --source text --from urls.txt
tabferry import --source json --from tabs.json
tabferry import --dedupe url                        # 只忽略 #锚点
tabferry import --dedupe none                       # 全部保留
```

- **Firefox** —— 读取 `sessionstore.jsonlz4`（以及
  `sessionstore-backups/recovery.jsonlz4`），通过 `profiles.ini` 在 Windows、
  macOS、Linux、Flatpak、Snap 上自动发现配置。
- **Chromium 系** —— 读取 Chrome / Edge / Brave / Chromium 的
  `Sessions/Session_*`（SNSS 日志）。`--browser auto` 会选择会话最新的配置。
  浏览器运行时可能独占该文件；关掉浏览器，或用 `--profile` 指向复制出来的配置。
- **文本** —— 一行一个 URL，或 `标题<TAB>URL`。
- **JSON** —— TabFerry 快照，或 `{"url": "...", "title": "..."}` 数组。

默认使用 `normalized` 策略去重；见下文。

### 去重

导入时默认去重，策略如下：

| `--dedupe` | 合并规则 |
| --- | --- |
| `normalized`（默认） | 同一个页面：忽略 `#锚点`、`utm_*` / `fbclid` / `gclid` 等跟踪参数、`www.`、默认端口、末尾斜杠，以及查询参数顺序 |
| `url` | 只忽略 `#锚点` |
| `none` | 不去重（`--keep-duplicates` 是它的别名） |

不想重新导入、只想去重已有快照：

```bash
tabferry dedupe --mode normalized
```

快照里会记录去重策略和合并数量；页面顶部会显示"合并了 N 个重复"，
`tabferry status` 也会打印。

页面「已移除」抽屉里的 **去重** 按钮会对当前列表应用同样的归一化比较，
被合并的条目会进入「已移除」，可以单独恢复。

### 提供服务

```bash
tabferry serve                     # 0.0.0.0:8123
tabferry serve --port 9000
tabferry serve --open              # 同时打开本机浏览器
```

| 路由 | 用途 |
| --- | --- |
| `GET /` | 手机页面 |
| `GET /api/state` | 已移除的 URL |
| `POST /api/remove` | 请求体 `{"url": "..."}` |
| `POST /api/restore` | 请求体 `{"url": "..."}` |
| `POST /api/restore_all` | 清空已移除 |
| `GET /download` | 带当前状态的单文件 HTML |
| `GET /health` | 健康检查 |

### 导出

```bash
tabferry export --format html -o tabferry.html
tabferry export --format txt -o urls.txt
tabferry export --format json
```

### 状态

```bash
tabferry status
```

```
Data dir: /home/me/.local/share/tabferry
Created:  2025-01-02T03:04:05+00:00
Source:   chromium:edge
Tabs:     128
Dedupe:   normalized (12 merged)
Removed:  3
```

## 数据目录

| 平台 | 目录 |
| --- | --- |
| Windows | `%APPDATA%\TabFerry` |
| macOS | `~/Library/Application Support/TabFerry` |
| Linux | `$XDG_DATA_HOME/tabferry` 或 `~/.local/share/tabferry` |

可以用 `--data-dir` 或 `TABFERRY_DATA_DIR` 覆盖。目录里有两个文件：

```
tabs.json    快照：标签页、创建时间、来源
state.json   已移除的 URL 及时间
```

## 离线模式

点页面顶部的 **保存离线副本**，或运行 `tabferry export --format html`。文件是
自包含的：标签页数据内嵌，移除状态存在浏览器的 `localStorage` 里。

- 用 `file://` 打开即可，不需要任何服务器。
- 在「已移除」抽屉里用 **导出 / 导入** 在离线副本和其他设备之间搬状态。
- 如果页面由 TabFerry 提供，移除状态会存在服务器的 `state.json` 里。

## 支持的来源

| 来源 | 参数 | 说明 |
| --- | --- | --- |
| Firefox | `--source firefox` | 会话存储，`profiles.ini` 自动发现 |
| Chromium 系 | `--source chromium` | Chrome / Edge / Brave / Chromium，SNSS `Session_*` |
| 文本 | `--source text` | 一行一个 URL，可选 `标题<TAB>URL` |
| JSON | `--source json` | 快照或标签页数组 |

新增来源：继承 `tabferry.sources.base.TabSource`，实现 `load()`，然后在
`tabferry/sources/__init__.py` 注册。`TabSource` 的契约很小，浏览器相关的
格式都留在 `sources/` 里。

### Chromium 会话说明

Chromium 写的是 SNSS 日志：`SNSS` 魔数、版本号，然后是一串带长度前缀的命令。
TabFerry 解析 `kCommandUpdateTabNavigation`（6）拿到 `tab_id / index / url /
title`，再用 `kCommandSetSelectedNavigationIndex`（7）选出当前真正打开的那条。
`Tabs_*` 是"最近关闭"列表，只作为兜底。Windows 上浏览器可能独占这些文件，
导入器会给出明确报错而不是堆栈；关掉浏览器，或用 `--profile` 指向复制出来的配置。

## 部署

### Docker

```bash
tabferry import --data-dir ./data      # 在宿主机运行，因为浏览器数据在宿主机
docker compose up -d --build
```

`docker-compose.yml` 把 `./data` 挂到 `/data`，并配置失败重启。

### systemd

```ini
[Unit]
Description=TabFerry
After=network-online.target

[Service]
ExecStart=/usr/local/bin/tabferry serve --host 0.0.0.0 --port 8123
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### 反向代理

TabFerry 只说 HTTP。如果要暴露到局域网之外，请在 Caddy/Nginx 上做 TLS 和认证
—— 内置服务器没有认证。

## 安全

服务器**没有认证**，状态 API 对能访问端口的人开放。请只在可信网络里运行，或放在
带认证的反向代理后面。标签页列表很敏感：它就是你的全部打开页面。

## 开发

```bash
git clone https://github.com/Bersker-Ick/TabFerry.git
cd TabFerry
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
ruff check .
```

```
tabferry/
  cli.py          import / serve / export / status / sources
  config.py       数据目录与路径
  models.py       Tab、Snapshot
  snapshot.py     快照读写
  state.py        已移除集合（原子 JSON）
  util.py         URL 归一化、去重、原子写入
  mozlz4.py       纯 Python mozLz40/LZ4 解压
  render.py       模板 + 数据 -> 单文件页面
  server.py       HTTP 服务 + JSON API
  sources/        chromium.py、firefox.py、text.py、json_source.py
  templates/      app.html（英文 + 简体中文）
tests/            unittest，无第三方依赖
docs/             架构说明
```

请求流程和扩展点见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 路线图

- HTTP API 的可选访问令牌。
- 让离线副本自动对账的同步端点。
- 更多界面语言。
- Firefox / Chromium 快照差异对比。

## 许可证

MIT © 2025 Bersker-Ick

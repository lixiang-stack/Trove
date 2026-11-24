# YouTube cookie 获取与续期方案（待定）

> 状态：待决定（2026-11-24）
>
> 范围：Trove Host 的 YouTube 下载鉴权；不涉及视频号。
>
> 结论：记录方案 1（专用浏览器 profile + `--cookies-from-browser`）和方案 2（CookieCloud + 定时导出），暂不改代码。

## 背景

YouTube 对部分视频或出口 IP 返回：

```text
ERROR: [youtube] ...: Sign in to confirm you're not a bot.
Use --cookies-from-browser or --cookies for the authentication.
```

Trove 当前通过 `TROVE_YTDLP_COOKIES` 指定一个 Netscape 格式的 cookie 文件，yt-dlp 下载和链接检查都会带 `--cookies`。这个方案能用，但文件是某一时刻的快照：Google 会轮换 cookie，文件过期后必须重新导出。

目标不是“自动填 Google 账号密码”，而是：

- 人工登录一次；
- 之后尽量自动读取或续期 cookie；
- Google 要求重新验证时，给用户一个明确的重新登录入口；
- 不把 Google 密码、2FA 种子或长期 cookie 交给第三方服务。

不建议用 Selenium/Playwright 自动填写账号密码：Google 登录有 2FA、Passkey、设备验证和风控，自动化登录经常遇到 “This browser or app may not be secure”，也可能导致账号被要求验证。登录这一步保留人工操作，其余步骤自动化。

## 现状

- `src/trove/config.py` 已有 `ytdlp_cookies`，读取 `TROVE_YTDLP_COOKIES`。
- `src/trove/adapters/downloader.py` 和 `src/trove/adapters/video_inspect.py` 已有 `--cookies` 分支。
- 目前没有 `--cookies-from-browser` 配置，也没有 `trove youtube ...` 命令。
- 本文中的 Trove 命令、环境变量和目录都是提案，尚未实现。

---

## 方案 1：专用浏览器 profile + `--cookies-from-browser`

### 原理

准备一个**专用的浏览器 profile**，只在里面登录 YouTube。yt-dlp 每次运行时直接读取该 profile 的实时 cookie 数据库：

```bash
yt-dlp --cookies-from-browser "firefox:/path/to/profile" ...
```

浏览器在正常使用时自动轮换、续期 cookie；yt-dlp 不需要导出 `cookies.txt`，也不存在“导出后冻结快照”的问题。cookie 始终留在本机，不经过额外服务。

### 手动配置：Firefox（推荐）

Firefox 在 macOS 上的 `cookies.sqlite` 不加密，不依赖 Keychain，浏览器运行中也能读取，最适合后台 worker。

```bash
brew install --cask firefox

mkdir -p "$HOME/Trove/browser/youtube"
chmod 700 "$HOME/Trove/browser/youtube"

/Applications/Firefox.app/Contents/MacOS/firefox \
  -CreateProfile "trove $HOME/Trove/browser/youtube"

/Applications/Firefox.app/Contents/MacOS/firefox \
  -profile "$HOME/Trove/browser/youtube" \
  -no-remote \
  "https://accounts.google.com/ServiceLogin?service=youtube"
```

在弹出的 Firefox 中正常登录（需要 2FA 就完成 2FA），然后关闭浏览器。之后验证：

```bash
yt-dlp \
  --cookies-from-browser "firefox:$HOME/Trove/browser/youtube" \
  --simulate --no-playlist \
  "https://www.youtube.com/watch?v=9mnx5M1s7As"
```

如果 profile 已经存在，`-CreateProfile` 可能提示重复；直接跳到带 `-profile` 的启动命令即可。

### 手动配置：Chrome（备选）

不想安装 Firefox 时，可以用独立的 Chrome 用户数据目录：

```bash
mkdir -p "$HOME/Trove/browser/chrome"

open -na "Google Chrome" --args \
  --user-data-dir="$HOME/Trove/browser/chrome" \
  --profile-directory="Default" \
  --no-first-run \
  --no-default-browser-check \
  "https://accounts.google.com/ServiceLogin?service=youtube"
```

登录后验证：

```bash
yt-dlp \
  --cookies-from-browser "chrome:$HOME/Trove/browser/chrome/Default" \
  --simulate --no-playlist \
  "https://www.youtube.com/watch?v=9mnx5M1s7As"
```

Chrome 的注意点：

- macOS 上 Chrome cookie 由 Keychain 的 “Chrome Safe Storage” 加密，第一次读取可能弹 Keychain 授权。
- Trove 作为 launchd 后台服务运行时可能看不到 Keychain 弹窗；这种场景优先用 Firefox，或改用方案 2。
- Chrome 运行时会锁 cookie 数据库；yt-dlp 会复制数据库，但偶尔仍可能失败。失败时关闭 Chrome 再试。
- 专用 profile 建议关闭 Chrome 同步，避免和个人账号数据混在一起。

### 保持 cookie 新鲜

不需要每天操作。让这个 profile **每周至少打开一次 YouTube** 即可，浏览器会刷新会话；可以手动，也可以加一个可选的 launchd 任务，打开几秒后关闭：

```bash
/Applications/Firefox.app/Contents/MacOS/firefox \
  -profile "$HOME/Trove/browser/youtube" \
  -no-remote \
  "https://www.youtube.com/"
```

如果 Google 主动使会话失效（例如要求重新验证），只能重新执行登录流程。任何方案都无法绕开这一步。

### Trove 接入（待实现）

建议增加一个配置项，和现有 `--cookies` 文件互斥、浏览器 profile 优先：

```bash
TROVE_YTDLP_COOKIES_FROM_BROWSER="firefox:/Users/you/Trove/browser/youtube"  # 示例路径
```

在 `downloader.py` 和 `video_inspect.py` 中：

```python
if config.ytdlp_cookies_from_browser:
    command += ["--cookies-from-browser", config.ytdlp_cookies_from_browser]
elif config.ytdlp_cookies and config.ytdlp_cookies.exists():
    command += ["--cookies", str(config.ytdlp_cookies)]
```

建议同时增加 CLI：

```bash
trove youtube login     # 打开专用 profile 的 Google 登录页
trove youtube status    # 检查认证 cookie 是否存在/是否过期
trove youtube logout    # 删除专用 profile
```

`trove youtube login` 可以做得比“打开浏览器后等用户按 Enter”更自动：

1. 创建/确认 profile 目录，权限 `0700`；
2. 启动浏览器到 Google 登录页；
3. 轮询 profile 的 cookie 数据库，检测 `SID`、`SAPISID`、`__Secure-3PSID` 等认证 cookie；
4. 检测到后返回成功；超时（例如 10 分钟）则提示重试。

Firefox 可以直接用标准库 `sqlite3` 轮询 `cookies.sqlite`；Chrome 需要 `rookie-cookies` 之类的库解密，或者只做“等待用户确认”。为了少一个依赖，建议优先支持 Firefox 的自动检测。

`trove youtube status` 可以只检查本地 cookie，不必每次发网络请求：

- 认证 cookie 是否存在；
- 最早/最晚过期时间；
- profile 目录和数据库是否可读。

如果要做真实的可用性探测，再用一个已知公开视频执行 `yt-dlp --simulate`，但不要高频调用，避免触发 YouTube 限流。

`trove doctor` 可以增加：

- profile 目录是否存在且权限为 `0700`；
- cookie 数据库是否可读；
- 认证 cookie 是否存在；
- 可选的 `yt-dlp-ejs` / JS runtime 检查（YouTube 抓取还需要 EJS，见 [yt-dlp EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS)）。

错误处理建议：

- 下载失败且归类为 `download.login_required` 时，UI 显示“YouTube 登录已过期，点击重新登录”，调用 `trove youtube login`。
- 不要自动重试 `login_required`；重试只会增加风控。
- 如果后续增加 `429` 分类，使用独立的 `download.rate_limited`，并做退避。

### 安全要求

- 专用 profile 等同于账号密码：目录 `0700`，不要放 iCloud/Dropbox，不要提交到 git。
- 使用专用 Google 账号，不要用主账号；开启 2FA，保留恢复方式。
- 不要保存 Google 密码或 2FA 种子到 Trove。
- 不要记录 cookie 值；错误日志只记录“cookie 缺失/过期”状态。
- 如果账号或 profile 泄露，立即退出所有会话、改密码、删除 profile。

### 优缺点

优点：

- 没有额外服务；cookie 不离开本机。
- 不产生静态 `cookies.txt`，浏览器自动续期。
- 实现成本低：Trove 只需增加一个配置项和一个登录命令。
- 和 ADR-0006 的原生 launchd 部署方式一致。

缺点：

- 要求浏览器和 Trove 在同一台 Mac 上。
- Chrome 在 launchd/Keychain 场景下可能不稳定；Firefox 更稳，但需要额外安装。
- 浏览器长期不打开时，cookie 仍可能过期。
- Google 可能随时要求重新验证，无法完全无人值守。

---

## 方案 2：CookieCloud + 定时导出

### 原理

[CookieCloud](https://github.com/easychen/CookieCloud) 是一个开源自托管的浏览器 cookie 同步工具：

- 浏览器扩展按固定间隔，把 cookie 加密上传到自建服务器；
- 服务端只保存密文，端到端加密；
- 另一端通过 `/get/:uuid` 拉取密文，用 UUID + 密码解密；
- 一个定时脚本把 YouTube/Google cookie 转成 Netscape `cookies.txt`，供 Trove 现有 `--cookies` 使用。

它解决的是“跨机器/无头环境无法读取浏览器 profile”的问题；登录仍然是在浏览器里人工完成。

### 服务端

官方推荐 Docker。注意这与 [ADR-0006](adr/0006-native-launchd-tailscale.md) 的“不使用 Docker”部署选择冲突；这里只作为可选辅助服务，不进入 Trove 的 Host 部署链路。如果不想在 Mac 上引入 Docker，可以在 NAS/另一台机器上用 Node 运行，或改用社区 Cloudflare Worker 版本。

```bash
docker run -d --name cookiecloud --restart unless-stopped \
  -p 127.0.0.1:8088:8088 \
  -v "$HOME/Trove/cookiecloud:/data/api/data" \
  easychen/cookiecloud:latest
```

只绑定 `127.0.0.1`；如果服务在另一台机器上，用 Tailscale/WireGuard 之类的私有网络访问，不要直接暴露公网。

### 浏览器扩展

在登录 YouTube 的浏览器里安装 CookieCloud 扩展（Chrome/Edge 官方商店；Firefox 需要自行构建），配置：

- 服务器：`http://127.0.0.1:8088`；
- UUID、密码：自己生成并保存；
- 同步间隔：例如 30 分钟。

扩展会同步该 profile 的全部 cookie；建议装在专用浏览器 profile 里，减少无关 cookie 的暴露。浏览器不打开时不会同步；但 cookie 通常也只在浏览器使用时才轮换，所以实际够用。

### 导出脚本

`GET http://127.0.0.1:8088/get/<uuid>` 返回：

```json
{"encrypted": "..."}
```

解密逻辑（CookieCloud README）：

1. `md5(uuid + "-" + password)` 取前 16 位作为 AES key；
2. 按 CryptoJS/OpenSSL 兼容格式 AES 解密；
3. 得到 `{"cookie_data": {...}, "local_storage_data": {...}}`。

可以直接用 [PyCookieCloud](https://github.com/lupohan44/PyCookieCloud)，或写一个约 30 行的 Python 脚本。导出时：

- 过滤域名：`.youtube.com`、`.google.com`、`accounts.google.com`；
- HttpOnly cookie 在 Netscape 行首加 `#HttpOnly_`；
- 保留 `domain`、`path`、`secure`、`expiry`、`name`、`value`；
- 原子写入 `~/Trove/youtube-cookies.txt`，权限 `0600`；
- 解密失败或同步失败时保留上一份可用文件，并记录告警。

Trove 继续使用现有配置：

```bash
export TROVE_YTDLP_COOKIES="$HOME/Trove/youtube-cookies.txt"
```

### Trove 接入（待实现）

两种方式：

1. **外部脚本 + launchd 定时器**：`scripts/youtube/cookiecloud-sync.py` 每 15–30 分钟同步一次，Trove 不感知 CookieCloud。
2. **Trove 子命令**：`trove youtube sync-cookiecloud`，读取 `COOKIE_CLOUD_HOST`、`COOKIE_CLOUD_UUID`、`COOKIE_CLOUD_PASSWORD`，写入同一个 cookie 文件。

建议先做外部脚本，保持 Trove 核心依赖干净；确认方案后再决定是否收进 CLI。

`trove doctor` 可以检查：

- cookie 文件是否存在、权限是否为 `0600`；
- 文件最后更新时间是否过旧；
- 是否包含 `SID`/`SAPISID` 等认证 cookie；
- CookieCloud 服务是否可达（可选，不应阻塞 doctor）。

### 安全要求

- CookieCloud 服务端只绑定本机或私有网络；不要暴露公网。
- UUID/密码是解密凭证，按 secret 管理，不要提交到仓库。
- 扩展能读取浏览器全部 cookie；装在专用 profile，不使用主浏览器。
- 服务端只保存密文，但仍应使用强密码和磁盘加密。
- 导出的 `cookies.txt` 是 bearer credential：`0600`，不提交、不云同步。
- 定期清理旧的 cookie 文件和历史备份。

### 优缺点

优点：

- 支持跨机器、无头 Host；Trove 不需要和浏览器同机。
- 浏览器扩展自动同步，不需要用户手动导出。
- 自托管 + 端到端加密，不依赖第三方 cookie 服务。
- 可以继续复用 Trove 现有的 `--cookies` 文件路径，核心改动小。

缺点：

- 多一个常驻服务（Docker/Node）和一个浏览器扩展，运维面更大。
- 与 ADR-0006 的“不使用 Docker”冲突，需要额外决策。
- 扩展能访问全部 cookie，安全评审成本更高。
- 同步链路长：扩展 → 服务端 → 解密脚本 → 文件 → yt-dlp；任何一环失败都可能导致旧 cookie。
- 依赖 CookieCloud 的数据格式；升级扩展/服务端时要固定版本并测试。
- Firefox 扩展不是官方商店版本，需要自行构建。

---

## 方案对比

| 维度 | 方案 1：浏览器 profile | 方案 2：CookieCloud |
| --- | --- | --- |
| 登录方式 | 人工登录一次 | 人工登录一次 |
| cookie 刷新 | 浏览器自动；yt-dlp 直读 | 扩展定时同步；脚本导出 |
| 是否同机 | 必须同机 | 可跨机/无头 |
| 额外依赖 | 无（Firefox 可选） | Docker/Node + 浏览器扩展 |
| Trove 改动 | 配置项 + `trove youtube login/status` | 配置项 + 同步脚本/定时器 |
| 安全面 | 本地 profile | 本地 profile + 同步服务 + 扩展 |
| 主要故障点 | Keychain、DB 锁、浏览器未使用 | 服务挂、扩展未开、解密/格式变更 |
| 与 ADR-0006 一致性 | 一致（原生 launchd） | 需要例外或外部主机 |
| 实现成本 | 低 | 中 |
| 适用结论 | 单机默认 | 迁移无头/远程后 |

## 决策标准（待定）

- Host 继续是这台 Mac，且浏览器同机：优先方案 1。
- Host 迁移到无头/远程，或需要在多台设备间共享登录态：方案 2。
- 安全评审不接受常驻同步服务或全量 cookie 扩展：方案 1。
- Chrome Keychain 在 launchd 下不可用，且不想安装 Firefox：方案 2。
- 不想在 Mac 上引入 Docker/Node：方案 1。
- 如果最终选择方案 2，需要先解决与 ADR-0006 的冲突：是允许一个辅助 Docker 服务，还是在 NAS/另一台机器上运行 CookieCloud。

## 未决问题

- [ ] 在 launchd 运行的 worker 中，Firefox `--cookies-from-browser` 是否能稳定读取 profile？
- [ ] Chrome 的 Keychain 授权在 launchd 下是否可用？是否会每次弹窗？
- [ ] Google 会话在每周打开一次 profile 的情况下能维持多久？
- [ ] 是否接受使用专用 Google 账号？账号恢复方式如何保存？
- [ ] 是否为 `trove youtube login` 引入 `rookie-cookies`，还是只支持 Firefox + 标准库 `sqlite3`？
- [ ] 方案 2 的 CookieCloud 服务放在哪里？本机 Node、NAS，还是允许 Docker？
- [ ] 方案 2 的同步脚本是否收进 Trove CLI，还是保持为独立脚本？
- [ ] 是否需要在 `trove doctor` 中把“YouTube 登录态”作为可操作警告？
- [ ] `download.login_required` 的 UI 文案和重新登录入口怎么设计？

## 非目标

- 自动填写 Google 账号密码、自动完成 2FA/Passkey。
- 绕过 Google 的账号风控或验证。
- 视频号下载；视频号仍走外部抓包/解密工具 + Trove 本地上传。
- 把 cookie 上传到第三方在线服务。
- 在仓库、日志或错误信息中记录 cookie 值。

## 参考资料

- [yt-dlp FAQ: How do I pass cookies to yt-dlp?](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
- [yt-dlp EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- [CookieCloud](https://github.com/easychen/CookieCloud)
- [PyCookieCloud](https://github.com/lupohan44/PyCookieCloud)
- [rookie-cookies](https://github.com/teng-lin/rookie-cookies)
- [ADR-0006: 原生 launchd 部署](adr/0006-native-launchd-tailscale.md)

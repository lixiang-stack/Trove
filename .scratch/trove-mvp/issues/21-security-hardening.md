# 21 — 安全加固与攻击面测试

Status: resolved
Disposition: closed 2026-11-13 — 12/12 manual checks PASS; automated suite PASS.
Type: task
Milestone: M3
Blocked by: 03, 05, 07, 08, 09, 11
Spec: [spec.md](../spec.md)
Requirements: FR-17, FR-80, FR-85, NFR-12
ADRs: [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

Host 会绑定局域网/VPN，接收用户提供的 URL、文件和 EPUB。需要在功能完成后做一次系统性安全加固，验证 SSRF、上传、文件服务、HTML 注入、认证和依赖版本。

## Scope

- SSRF：播客 feed/enclosure 的私网/回环/链路本地/元数据/CGNAT/重定向校验；视频平台白名单；无通用下载代理。
- 上传：流式大小限制、MIME/扩展名/内容校验、SHA-256、失败清理、临时目录权限。
- 文件服务：只允许 artifact 路径、防路径穿越、Range/ETag、`nosniff`、私有缓存。
- HTML：EPUB 章节 `nh3` 白名单、Jinja 自动转义、CSP 禁止远程脚本/图片、Cookie/CSRF 防护。
- 认证：限速、会话过期、Secure Cookie、密钥/session secret 权限、日志脱敏。
- 依赖：Starlette ≥0.49.1（Range DoS CVE）、其他依赖安全版本；记录许可证。
- 安全回归测试与检查清单。

## Acceptance Criteria

- [x] 私网/元数据/回环/重定向到私网的 feed/enclosure URL 全部被拒绝。
- [x] 超大/错误类型/损坏上传被拒绝并清理；临时目录不残留。
- [x] 路径穿越、未知 artifact、未认证文件访问全部被拒绝。
- [x] 恶意 EPUB HTML 的脚本/远程资源被移除；CSP 生效。
- [x] 登录限速/会话/Cookie 属性符合 spec；日志不含密码/Cookie/Key。
- [x] Starlette 版本不受 CVE-2025-62727 影响；依赖检查通过。

## Testing

自动化覆盖由 Host seam 测试和回归脚本承担，不单独维护验收结果表：

- `uv run pytest -q tests/test_security.py`：SSRF、上传清理、路径穿越、恶意 HTML、CSP。
- `uv run pytest -q tests/test_auth.py tests/test_local_intake.py tests/test_playback.py`：认证、会话、上传和音频响应。
- `uv run pytest -q -m browser tests/test_browser.py`：浏览器行为和页面安全。
- `./scripts/check.sh`：ruff、mypy、完整测试和文档检查。
- 不做渗透测试/公网扫描。

## Manual Acceptance (真实 Host)

以下表格是本票的真实 Host 验收标准；所有项目 PASS 才通过。自动化测试作为支持证据，不能替代手工抽查。

### 准备

```bash
BASE=http://127.0.0.1:8765
COOKIE=/tmp/trove.cookies
read -rs TROVE_PASSWORD
```

如使用 HTTPS/Tailscale，把 `BASE` 换成对应的 `https://...` 地址。测试前先准备至少一条已处理完成、`has_audio=true` 的 Item。

### 手工验收表

| # | 测试项 | 测试方法（最简单） | 期望结果 | 实际结果 |
| -: | ------ | ------------------ | -------- | -------- |
| 1 | 登录并保存会话 | `curl -sD - -o /dev/null -c "$COOKIE" --data-urlencode "password=$TROVE_PASSWORD" "$BASE/login"` | `303`；响应含 `Set-Cookie: trove_session=...; HttpOnly; SameSite=lax` | ✅ |
| 2 | 未认证访问 API | `curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/items"` | `401` | ✅ |
| 3 | 查找 Item ID | `curl -s -b "$COOKIE" "$BASE/api/items" -o /tmp/trove-items.json; python3 -c 'import json; [print(i["id"], i["title"], i["has_audio"]) for i in json.load(open("/tmp/trove-items.json"))["items"]]'` | 输出 UUID、标题、`has_audio` | ✅ |
| 4 | 选择音频 Item | `ITEM_ID=$(python3 -c 'import json; print(next(i["id"] for i in json.load(open("/tmp/trove-items.json"))["items"] if i["has_audio"]))'); echo "$ITEM_ID"` | 输出一个 UUID | ✅ |
| 5 | 未认证访问音频 | `curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/items/$ITEM_ID/audio"` | `401` | ✅ |
| 6 | 认证访问音频 | `curl -sD - -o /dev/null -b "$COOKIE" "$BASE/api/items/$ITEM_ID/audio"` | `200`；含 `ETag`、`Accept-Ranges: bytes`、`Cache-Control: private`、`X-Content-Type-Options: nosniff` | ✅ |
| 7 | 音频 Range | `curl -sD - -o /dev/null -b "$COOKIE" -H 'Range: bytes=0-99' "$BASE/api/items/$ITEM_ID/audio"` | `206`；含 `Content-Range: bytes 0-99/...`、`ETag`、`Accept-Ranges: bytes` | ✅ |
| 8 | 未知 Item 音频 | `curl -s -o /dev/null -w '%{http_code}\n' -b "$COOKIE" "$BASE/api/items/00000000-0000-0000-0000-000000000000/audio"` | `404` | ✅ |
| 9 | 页面 CSP | `curl -sD - -o /dev/null -b "$COOKIE" "$BASE/items/$ITEM_ID"` | `200`；CSP 含 `default-src 'self'`、`script-src 'self'`、`img-src 'self' data:`、`frame-ancestors 'none'` | ✅ |
| 10 | 日志脱敏 | `grep -Ei -e password -e cookie -e session_secret -e trove_session -e api_key ~/Trove/logs/trove.log` | 不出现密码、Cookie、session secret 或 API key 的实际值 | ✅ |
| 11 | 数据目录权限 | `stat -f '%Sp %N' ~/Trove ~/Trove/config.toml ~/Trove/.env ~/Trove/cache/uploads` | 数据目录/上传目录 `drwx------`；配置文件 `-rw-------` | ✅ |
| 12 | 改密码后旧会话失效 | 先执行 `uv run trove auth set-password`，再执行 `curl -s -o /dev/null -w '%{http_code}\n' -b "$COOKIE" "$BASE/library"` | 改密码后旧 Cookie 访问返回 `303` 跳转登录页 | ✅ |

登录后执行一次 `unset TROVE_PASSWORD`。第 12 项会改掉当前密码，放在最后执行。

## Acceptance Record

| 字段 | 值 |
| ---- | -- |
| 执行日期 | 2026-11-13 |
| Host 版本 | `trove 0.1.0` |
| macOS / 浏览器 | macOS 14.6.1 (M1 Pro) / curl |
| 自动化证据 | 本地 `./scripts/check.sh --full` PASS（323 tests） |
| 手工表结果 | 12/12 PASS |
| 结论 | PASS |
| 失败项与 follow-up issue | 无 |

任一项目 FAIL 即不通过；修复后必须重跑对应项目。不要用“其他项通过”替代失败项。

## Out of Scope

- 多用户/权限模型、WAF、云端合规；不做。
- 物理设备安全、macOS 系统加固；由部署文档提示。

## Comments

2026-11-10 — Implemented the agent-side hardening: multipart uploads now validate
EPUB structure and FFprobe media streams before creating an Item; upload metadata
paths are confined to the upload directory; SSRF checks cover reserved/CGNAT/
IPv4-mapped addresses and re-validate redirects; security headers include CSP,
nosniff, frame denial, and a same-origin referrer policy. Added
`tests/test_security.py`, `docs/security.md`, and `docs/licenses.md`; pinned
Starlette `>=0.49.1`. Manual clean-Mac deployment checks remain for ticket 24/29.

2026-11-13 — 用户在真实 Host（`http://127.0.0.1:8765`）完成手工验收表，12/12 PASS；旧的未提交结果已合并到本票。自动化 `./scripts/check.sh --full` 通过（323 tests）。本票关闭并归档。

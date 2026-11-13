# 22 — JSON API、OpenAPI 与 Range/ETag 契约

Status: ready-for-agent  
Type: task  
Milestone: M3  
Blocked by: 05, 06, 11, 13, 14, 16, 17, 20  
Spec: [spec.md](../spec.md)  
Requirements: FR-82, FR-73, NFR-08  
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

未来 Android 必须复用同一套 API/数据，不能另建库。功能完成后需要一次 API 契约审计：所有页面能力都有 JSON API、OpenAPI 完整、错误一致、媒体 Range/ETag 可用于 V1 可续传下载。

## Scope

- 审计 spec 第 5 节的端点是否全部实现；HTML 独有的数据不得只存在于模板。
- OpenAPI 文档完整：请求/响应 schema、错误形状、认证要求。
- 统一错误 `{code, message, details?}`；稳定错误码；404/401/409/422/429 语义。
- 认证：Cookie 会话可用于 API；Android 可复用 cookie jar；不新增 bearer（V1 再加）。
- 媒体：`GET audio` 支持 Range/ETag/Accept-Ranges；artifact 元数据 sha256/size/mime 可查询。
- 分页/过滤/排序参数一致性；不要泄漏内部路径。
- API 契约测试与文档示例。

## Acceptance Criteria

- [ ] OpenAPI 包含 spec 列出的全部 MVP 端点，schema 与实现一致。
- [ ] 未认证、未知 Item、重复添加、校验失败、限速返回稳定状态码/错误形状。
- [ ] 音频/文件响应带 ETag/Accept-Ranges，Range 请求返回 206；V1 manifest 所需元数据可通过 API 获取。
- [ ] HTML 页面所需数据均可通过 API 获取；没有 web-only 的数据模型。
- [ ] API 不返回服务器绝对路径/密钥/内部堆栈。
- [ ] 契约测试在 Host seam 上通过。

## Testing

- Host seam：端点覆盖/错误/认证/Range/ETag/分页/过滤。
- OpenAPI schema 快照或关键字段断言；不追求全量快照。
- 与 11/20 的媒体/导出测试共用 fixture。
- 不做 Android 客户端或代码生成。

## Manual Acceptance (真实 Host)

这里只列不能由自动化完全替代的项目。以下项目已由
`tests/test_api_contract.py`、`tests/test_playback.py`、`tests/test_reading.py`
和 `tests/test_export.py` 覆盖，不再列入人工表：

- 401/404/422/429 错误形状、重复添加返回 `deduplicated`
- 音频 `ETag`、`Accept-Ranges`、Range `206`
- artifact 的 sha256/size/mime 元数据
- Item 分页、过滤、排序
- OpenAPI 路径和关键 schema 的自动断言

### 准备

```bash
BASE=http://127.0.0.1:8765
COOKIE=/tmp/trove.cookies
read -rs TROVE_PASSWORD
curl -sD - -o /dev/null -c "$COOKIE" --data-urlencode "password=$TROVE_PASSWORD" "$BASE/login"
unset TROVE_PASSWORD
curl -s -b "$COOKIE" "$BASE/api/items" -o /tmp/trove-items.json
ITEM_ID=$(python3 -c 'import json; print(next(i["id"] for i in json.load(open("/tmp/trove-items.json"))["items"] if i["has_audio"]))')
echo "$ITEM_ID"
```

测试前准备至少一条已处理完成、`has_audio=true` 的 Item。

### 人工验收表

| # | 测试项 | 测试方法（最简单） | 期望结果 | 实际结果 |
| -: | ------ | ------------------ | -------- | -------- |
| 1 | OpenAPI 端点、schema、认证要求 | 浏览器打开 `$BASE/api/openapi.json`，对照 [spec.md](../spec.md) 第 5 节端点表检查路径、请求/响应 schema、Cookie 认证标记 | 所有 MVP 端点存在；受保护端点显示 Cookie 认证；登录/health 不需要认证；schema 字段与真实响应一致 | 待填 |
| 2 | 409 冲突错误形状 | `curl -s -o - -w '\nHTTP %{http_code}\n' -b "$COOKIE" -X POST "$BASE/api/items/$ITEM_ID/retry"` | `409`；响应体为 `{"code":"item.conflict","message":"The current Processing Run does not need a retry","details":null}` | 待填 |
| 3 | HTML 与 JSON API 数据对齐 | 按下方“HTML ↔ API 对照表”逐页检查；页面能看到的数据必须能从对应 API 获取 | 所有页面数据均有 API 来源；无只存在于模板的数据模型 | 待填 |
| 4 | 真实响应不泄漏绝对路径/密钥/堆栈 | `curl -s -b "$COOKIE" "$BASE/api/items/$ITEM_ID" -o /tmp/trove-item.json; curl -s -b "$COOKIE" "$BASE/api/search?q=test" -o /tmp/trove-search.json; grep -Ei -e '/Users/' -e '/Volumes/' -e 'sk-' -e 'Traceback' -e 'session_secret' -e 'DEEPSEEK_API_KEY' -e 'api_key' /tmp/trove-item.json /tmp/trove-search.json` | 无任何匹配输出 | 待填 |

注意：`ai.model`（例如 `deepseek-flash`）是 AI 结果的模型元数据，不是密钥；泄漏扫描不应把 `deepseek` 单词本身当作失败。

第 2 项只对已经完成的 Run 返回 409；失败/取消的 Run 会返回 200 并重新排队。`-D -` 只显示响应头，响应体在 `-o` 指定的文件里；上表命令用 `-o -` 直接显示 body。

### HTML ↔ API 对照表

| 页面 | 浏览器路径 | 对应 API | 检查点 | 实际结果 |
| ---- | ---------- | -------- | ------ | -------- |
| Library / Inbox | `/library`、`/library?state=processing,failed` | `GET /api/items?state=...` | Item 列表、状态、排序、过滤结果一致 | 待填 |
| Continue | `/continue` | `GET /api/continue` | 续听/续读 Item、kind、进度一致 | 待填 |
| Item 详情 / Run 状态 | `/items/{id}` | `GET /api/items/{id}`、`GET /api/runs/{run_id}` | 来源、Tag、Processing State、失败原因、日志 tail 可获取 | 待填 |
| Listen / transcript | `/items/{id}/listen` | `GET /api/items/{id}/transcript` | 分段、时间戳、文本一致 | 待填 |
| Read / book | `/items/{id}/read?chapter=n` | `GET /api/items/{id}/book/chapters/n` | 章节、段落、已净化 HTML 一致 | 待填 |
| Search | `/search?q=...` | `GET /api/search?q=...` | 按 Item 聚合、证据段落、过滤参数一致 | 待填 |
| Add feed preview | `/add` | `POST /api/feeds/preview` | feed 标题、作者、单集列表一致 | 待填 |
| Export | `/export` | `GET /api/export` | 导出范围、zip 内容一致 | 待填 |

## Acceptance Record

| 字段 | 值 |
| ---- | -- |
| 执行日期 | |
| Host 版本 | `uv run trove --version` |
| macOS / 浏览器 | |
| 自动化证据 | `./scripts/check.sh` PASS；CI: <run url> |
| 人工表结果 | 全部 PASS / 有失败项 |
| 结论 | PASS / FAIL |
| 失败项与 follow-up issue | |

任一项目 FAIL 即不通过；修复后必须重跑对应项目。不要用“其他项通过”替代失败项。

## Out of Scope

- Android 客户端、代码生成、API 版本前缀/迁移策略；V1 再定。
- 同步 manifest/cursor/tombstone；V1。

## Comments

2026-11-10 — Completed the API contract audit: typed response schemas and OpenAPI
error/auth components, `GET /api/continue`, Item pagination (`limit`/`offset`),
artifact metadata without server paths, run-error/log path redaction, stable
`run.not_found`, and contract tests in `tests/test_api_contract.py`. Range/ETag
behavior is covered together with ticket 11 playback tests.

# 08 — Android Core 骨架与 App seam 测试

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 01
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Android 功能需要统一的网络、数据库、DI 和测试替身。这个 issue 建立 `:core` 的骨架、Room schema、DTO/contract fixture、fake API 和 `AppContainer`，让后续 feature 通过公开 ViewModel/UI seam 测试，而不是各自搭测试设施。

## Scope

- `:app`/`:core`/`:playback`/`:reader` 的依赖方向与 `AppContainer` 手工 DI。
- OkHttp/Retrofit + Kotlinx Serialization DTO；Bearer 拦截器接口；统一 `ApiError`。
- Room 数据库：Item/Artifact/TranscriptSegment/BookChapter/BookParagraph/Tag/SyncCursor/PendingMutation；schema 导出与 migration 测试。
- TokenStore 接口（Keystore + DataStore 实现由 09 接入）。
- `FakeTroveApi` + `TestAppContainer` + `FakeTokenStore`；Compose UI test/Robolectric 基础。
- 共享 contract fixture：manifest/state/error 的 JSON fixture；Android DTO 测试消费。
- Compose 空 shell + 底部导航占位；不实现真实页面。

## Acceptance Criteria

- [ ] 4 个 module 依赖方向正确；`AppContainer` 可组装 fake/real 依赖。
- [ ] Room 空库迁移成功；关键表/索引存在；schema 可测试。
- [ ] DTO 能解析共享 fixture；错误形状 `{code,message,details?}` 正确。
- [ ] App seam 能通过 fake API 驱动一个最小 Compose 流程并断言可见状态。
- [ ] 不包含真实登录/Library/播放/阅读业务逻辑。
- [ ] JVM/Robolectric 测试和 lint 在 CI 通过。

## Testing

- Android App seam：fake API + 真 Room + Compose/Robolectric。
- DTO/contract fixture 测试；Room migration 测试；token store 接口 fake 测试。
- 不测 ExoPlayer/Readium 内部；由 11/14 负责。

## Out of Scope

- 真实认证、Library、播放、下载、阅读、搜索；由 09–18 实现。
- instrumented 平台测试；由 11/14/20 补充。

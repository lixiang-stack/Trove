# Q10 phone playback spike log

Ticket: [25 — Q10 一周手机播放 Spike](25-q10-phone-spike.md)
Status: closed — not accepted (desktop MVP)
HTTPS setup: [deployment guide](../../../docs/deployment.md) · Tailscale acceptance SKIPPED; use Caddy

Use this file for the raw week-long observations. Do not replace it with a summary
until the week is complete. Record the real device, browser, OS, Tailscale/Caddy
HTTPS method, and network on each day.

## Environment

| Field           | Value |
| --------------- | ----- |
| Phone model     |       |
| iOS/Android     |       |
| Browser/version |       |
| HTTPS method    | Caddy internal CA (Tailscale acceptance skipped) |
| Host version    | `trove --version` |
| Library items   | at least 5, including one ≥60 min |

## Daily log

| Date | Item | Play/pause | Seek | Speed | Lock/background | Media notification | Nav keeps audio | Resume position | Network | Result / notes |
| ---- | ---- | ---------- | ---- | ----- | --------------- | ------------------ | --------------- | --------------- | ------- | -------------- |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |
|      |      |            |      |       |                 |                    |                 |                 |         |                |

## Search and transcript on the phone

| Date | Search query | Opened result | Transcript readable | Highlight/search | Notes |
| ---- | ------------ | ------------- | ------------------- | ---------------- | ----- |
|      |              |               |                     |                  |       |
|      |              |               |                     |                  |       |
|      |              |               |                     |                  |       |

## Failure cases

| Date | Reproduction steps | Browser/OS | Expected | Actual | Screenshot/log |
| ---- | ------------------ | ---------- | -------- | ------ | -------------- |
|      |                    |            |          |        |                |

## Decision

- [ ] PASS — phone browser is the listening acceptance device.
- [ ] FAIL — consumption shrinks to desktop; native player goes to the next
      milestone (or only the Consumer Shell becomes React).

Evidence for the decision:

```text

```

If FAIL, also confirm that Host Console intake, management, and search still pass
their own acceptance; a Q10 failure is not a Host Console failure.

> 2026-11-13: Tailscale Serve acceptance is skipped; record the Caddy HTTPS URL instead.

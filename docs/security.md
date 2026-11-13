# Security checklist

This checklist covers the MVP attack surface: URL intake, uploads, artifact
serving, EPUB HTML, authentication, and dependencies. It is a regression checklist,
not a penetration-test report.

## URL intake and SSRF

- [x] Only `http`/`https` URLs; credentials in URLs are rejected.
- [x] Feed and enclosure URLs resolve to public addresses only. Private, loopback,
      link-local, metadata, CGNAT, reserved, and IPv4-mapped addresses are rejected.
- [x] Every redirect target is validated again; redirects are capped and responses
      are size-limited (feed 10 MB, podcast media 1 GB).
- [x] Video URLs are restricted to the Bilibili/YouTube single-video allowlist.
      There is no generic download proxy.
- [ ] Residual: DNS rebinding between validation and the HTTP client connection is
      not pinned. Keep the Host on loopback/Tailscale and treat feed URLs as
      untrusted. Revisit if the intake surface becomes multi-user.

## Uploads and local paths

- [x] Streaming writes with per-kind byte limits; filenames are reduced to a safe
      basename and stored in a per-upload `0700` directory with `0600` files.
- [x] Extension and MIME allowlists, SHA-256 computed while writing, EPUB structure
      validation, and FFprobe stream validation before an Item is created.
- [x] Failed validation and failed intake remove the temporary upload directory.
- [x] Local paths must be absolute, readable regular files with a supported suffix.
- [x] Video source files stay at their original path; only derived audio is stored.

## File serving and paths

- [x] Audio and cover responses resolve through `ContentPackage.artifact_path`,
      which rejects paths escaping the Item directory.
- [x] No generic file endpoint; unknown or missing artifacts return `404`.
- [x] `ETag` from SHA-256, `Accept-Ranges: bytes`, `Cache-Control: private`,
      `X-Content-Type-Options: nosniff`.
- [x] Unauthenticated media/file requests return `401` before path resolution.

## HTML and EPUB

- [x] Jinja2 autoescaping is enabled; user titles/authors are never marked safe.
- [x] EPUB chapters are parsed into text paragraphs and cleaned with an `nh3`
      tag allowlist (no attributes, scripts, styles, remote images, or links).
- [x] CSP: `default-src 'self'`, `script-src 'self'`, `img-src 'self' data:`,
      `media-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`.
- [x] `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `nosniff`.

## Authentication and headers

- [x] Argon2id password hash in `config.toml` (`0600`); session secret generated
      with `secrets.token_urlsafe` and stored in the same `0600` file.
- [x] Signed HttpOnly, `SameSite=Lax` cookie with a 30-day expiry; `Secure` under
      HTTPS or when `TROVE_SECURE_COOKIES=1`.
- [x] Login failures are rate-limited per client IP (`429` + `Retry-After`).
- [x] Unsafe methods reject cross-site `Origin`/`Sec-Fetch-Site`; no GET mutations.
- [x] Logs contain request method/path/status but not passwords, cookies, session
      secrets, API keys, or request bodies.
- [x] Default bind is `127.0.0.1`; `--lan` prints a trusted-LAN warning.

## Dependencies and deployment

- [x] Starlette is pinned to `>=0.49.1`, which includes the Range DoS fix
      (CVE-2025-62727). `tests/test_security.py` asserts the installed version.
- [x] Core dependencies stay MIT/BSD/Apache; see [licenses](licenses.md).
- [x] Data directory `0700`; config and `.env` `0600`; DeepSeek key stored outside
      the data directory in `~/.config/trove/llm_api_key` (`0600`).
- [x] launchd agents bind loopback; phones use Tailscale Serve or Caddy HTTPS.
- [x] Uploads, content packages, and temporary Run workspaces use `0700`/`0600`.

Run the security tests with:

```bash
uv run pytest -q tests/test_security.py
uv run pytest -q tests/test_security.py -m ffmpeg
```

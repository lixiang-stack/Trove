# Android app

The Android client lives in `android/` and is side-loaded for personal use. It is
not published to the Play Store and does not use Play App Signing.

## Build variants

| Variant | Cleartext | Purpose |
|---|---|---|
| `prodDebug` | localhost/emulator only | Normal debug builds and JVM tests |
| `lanDebug` | trusted private LAN hosts | LAN-only debugging; keeps a persistent warning banner |
| `prodRelease` | never | Signed side-load build |

```bash
cd android
./gradlew :app:assembleProdDebug
./gradlew :app:assembleLanDebug
./gradlew :app:assembleProdRelease
```

`lanRelease` is intentionally disabled: the LAN cleartext build must not become a
distribution artifact. The `lan` build uses a separate application id
(`dev.trove.app.lan`) so it can coexist with the normal app.

## Release signing

The release build reads signing values from environment variables or Gradle
properties. Never commit a keystore.

```bash
keytool -genkeypair -v \
  -keystore "$HOME/.trove-release.jks" \
  -storetype PKCS12 -alias trove-release \
  -keyalg RSA -keysize 4096 -validity 10000

export TROVE_RELEASE_STORE_FILE="$HOME/.trove-release.jks"
export TROVE_RELEASE_STORE_PASSWORD='...'
export TROVE_RELEASE_KEY_ALIAS=trove-release
export TROVE_RELEASE_KEY_PASSWORD='...'
(cd android && ./gradlew :app:assembleProdRelease)
```

Without those variables the release APK is unsigned; it still exercises R8 and
resource shrinking but cannot be installed. Bump `versionCode` for every
side-loaded update. A debug install must be uninstalled before installing the
release build because the signatures differ.

Verify the artifact before installing:

```bash
scripts/android/release-check.sh
# checks: signed, not debuggable, permissions allowlist, <= 35 MiB target
```

## CI

- `android` workflow: `assembleProdDebug`, JVM/Compose tests, lint, and the LAN
  flavor smoke. It runs on PRs that touch Android inputs, the contract fixtures,
  `tests/fixtures`, or `scripts/android`.
- `android-release` workflow: signed `prodRelease` plus
  `scripts/android/release-check.sh` (R8/resource shrink, signature, permissions,
  35 MiB target). It runs on `main`, manual dispatch, and PRs that touch release
  configuration (R8 rules, manifest, network security, build/version files).

## HTTPS and Caddy

Release builds reject `http://` in both the Android network security config and
the app-side Host URL validation. The main network security config trusts system
and user-installed CAs so a Caddy internal CA can be used:

1. Generate and trust Caddy's local root (`caddy trust` on the Mac).
2. Copy the root certificate to the phone and install it under
   Settings → Security → Encryption & credentials → Install a certificate → CA
   certificate.
3. Open `https://trove.local` (or the Caddy hostname) in the app.

Tailscale with a public certificate is the recommended path and needs no user CA.
The app never bypasses certificate validation and does not pin certificates.

## Xiaomi / OEM background limits

Settings → Platform opens the system battery-optimization page. On Xiaomi/Redmi
also allow autostart and set the battery saver policy to “No restrictions”;
otherwise the system may stop background playback, downloads, or periodic sync.
This is an OEM behavior, not something the app can override.

## Device checks

```bash
scripts/android/check.sh             # build + JVM/Compose tests + lint (all modules)
scripts/android/device-check.sh      # bundled SQLite/FTS5 + platform manifest
scripts/android/acceptance-host.sh   # throwaway Host + prodDebug app + adb reverse
scripts/android/acceptance-playback.sh --seconds 30   # short playback smoke
scripts/android/acceptance-playback.sh                # 5-minute background run
scripts/android/diagnostics.sh       # media session, notification, doze, logcat
scripts/android/ui-dump.py           # dump screen; supports --wait/tap text/desc
```

`acceptance-playback.sh` clones the current Host DB/config into a throwaway home,
adds a silent audio Item, drives the app over `adb reverse`, locks the screen, and
verifies MediaSession plus Host canonical progress. It assumes the debug app's Host
URL is `http://127.0.0.1:8765` and that the phone is connected over USB and Wi-Fi.
It restores the previous reverse mapping when it exits.

Real-device acceptance still requires manual playback, download, reader, and sync
checks. Emulator passes do not replace background playback/media notification
verification.

## USB: latest debug app against the real Host

Use this when you want to try a worktree build against the real `~/Trove` data.
It does not create a temporary Host, copy the database, or seed acceptance data.

1. Start the real Host in one terminal:

   ```bash
   cd ~/src/Trove   # or the checkout that owns ~/Trove
   uv run trove serve
   ```

2. Connect the phone over USB and run:

   ```bash
   scripts/android/use-real-host.sh
   ```

3. Log in with the real Host password at `http://127.0.0.1:8765`.

The script starts no Host by itself; it expects `/api/health` on
`127.0.0.1:8765`. It builds and installs the current worktree's `prodDebug` APK,
sets `adb reverse`, and launches the app.

Useful options:

```bash
scripts/android/use-real-host.sh --no-build    # install existing APK
scripts/android/use-real-host.sh --clear-data  # remove old token and downloads
scripts/android/use-real-host.sh --port 9876   # non-default Host port
```

If the app still shows a token from an acceptance Host, `--clear-data` gives a
clean login but deletes local downloads. Do not use `acceptance-host.sh` when you
want the real Library.

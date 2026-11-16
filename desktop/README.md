# Demel desktop

A small tray app for Windows, macOS and Linux. When Demel says a sip is due, it covers every monitor with Demel's reminder page (`/?overlay=1`) until you choose **Done**, **In 5 min** or **Skip**. Answering on any device clears the reminder everywhere. While you use the computer, Demel skips the phone push. This app started as Drinky.

## Install

Download the installer from the repository's releases:

| Platform | File |
|---|---|
| Windows | `Demel_x.y.z_x64-setup.exe` (or the portable `.exe`) |
| macOS (Intel + Apple Silicon) | `Demel_x.y.z_universal.dmg` |
| Linux | `Demel_x.y.z_amd64.AppImage` or `.deb` |

The builds are unsigned:
- **macOS:** after copying the app to Applications, run `xattr -cr /Applications/Demel.app` once.
- **Windows:** SmartScreen may warn you. Click *More info → Run anyway*.
- **Linux:** the tray icon needs `libayatana-appindicator3`.

On first launch, enter your Demel address and password. The password is exchanged once for a device token (a 365-day session that changing the password revokes). The token is stored in `connection.txt` in the app's config directory. The app starts at login, which you can turn off in the tray menu.

Tray menu: *I took a sip*, *+250 ml glass*, *+500 ml bottle*, *Remind everywhere now*, *Open Demel*, *Connect…*, *Start at login*.

Whether you are at the computer is read from the OS on Windows (`GetLastInputInfo`) and macOS (CoreGraphics). On Linux the app never reports activity, so the phone always gets the push.

## How it talks to Demel

| Call | Purpose |
|---|---|
| `POST /api/auth/device` | password → device token (once) |
| `GET /api/hydration/events` | SSE with `due`, `total`, `goal`, `next_at`, `sip_ml`; shows or hides the overlays |
| `POST /api/hydration/presence` | every 30 s while you use the computer |
| `POST /api/hydration/drink` | log a sip, or `{"ml": 250}` |
| `POST /api/hydration/remind` | remind on every device now |

Every call sends `Authorization: Bearer <token>`. Overlay windows open `/?overlay=1&desktop=1#device=<token>`; the page trades the token for the usual cookie, and a URL fragment never reaches the server.

## Build

Builds run on GitHub Actions (`.github/workflows/desktop.yml`): pull requests that touch `desktop/` keep the installers as artifacts, and a `desktop-vX.Y.Z` tag publishes a release. Bump `version` in `src-tauri/tauri.conf.json` and `src-tauri/Cargo.toml` first.

Locally (needs Rust; Linux also needs `libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev`):

```sh
cd desktop
npx @tauri-apps/cli@2 dev
npx @tauri-apps/cli@2 build
```

## License

GPL-3.0-or-later, see [LICENSE.md](LICENSE.md). This folder keeps the Drinky license; it started as a fork of [BreakTimer](https://github.com/tom-james-watson/breaktimer-app) by Tom Watson.

# Subs4Grab

Automatic Greek & English subtitles for your videos — **ALU DEV TEAM**

Drag your videos (or whole folders) in, press **START**, and every video gets its subtitle saved next to it with the same name, so your TV, VLC and Kodi load it automatically.

## Sources
| Source | Used for | How it matches |
|---|---|---|
| [subs4series.com](https://www.subs4series.com) | TV series | name, season/episode, release group + downloads |
| [subs4free.club](https://www.subs4free.club) / subs4free.info | Movies | name, year, release + downloads |
| [OpenSubtitles.com](https://www.opensubtitles.com) *(optional)* | Everything | **file hash** (exact file) + name |

## Install
1. Install [Python 3.10+](https://www.python.org/downloads/) (tick *Add Python to PATH*).
2. Download **Subs4Grab.pyw** from the [latest release](../../releases/latest).
3. Double-click it. The first start installs everything it needs (1–3 minutes, once).

## Use
1. **Add your videos**: drag & drop files or folders (sub-folders are scanned too).
2. **Choose language**: Greek (English if there's none) is the default.
3. **Press START.**

Double-click any row to choose a different subtitle yourself.

## Features
- Anti-bot protection is handled by a built-in browser; if a site asks "I'm not a robot", a small window opens.
- Greek characters are fixed automatically (saved as UTF-8).
- Files already done are remembered by file hash and skipped next time.
- OpenSubtitles.com search by file hash (free account + free API key, guided setup).
- One click installs the official VLSub OpenSubtitles.com extension into VLC.
- **Automatic updates** from this repository's Releases.

## Publishing a new version (OTA)
1. Change `APP_VERSION = "x.y.z"` at the top of `Subs4Grab.pyw` and commit.
2. Push a tag with the same number:
   ```
   git tag v1.2.1
   git push origin v1.2.1
   ```
3. GitHub Actions creates the release with `Subs4Grab.pyw` attached. Everyone's app shows **"New version available → Update now"** on its next start.

If you attach a compiled `Subs4Grab.exe` to the release as well, the .exe build updates itself too.

# OnScreenClock

A lightweight, always-on-top floating clock for macOS that stays visible over all windows — including full-screen applications. Built with Python and PyObjC for native macOS integration.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

### Clock
- Always-on-top display that floats over all windows, desktops, and full-screen apps
- Draggable — click and drag to reposition anywhere on screen
- Position is remembered across restarts
- Toggle seconds on/off (HH:MM:SS vs HH:MM)

### Countdown Timer
- Set a countdown via an inline input field in the menu bar (HH:MM:SS or MM:SS format)
- Start, Pause, and Reset controls
- Optionally show the current time as sub-text below the countdown while the timer is running

### System Monitoring
- **Network Stats**: Live upload/download speeds (aggregate across all interfaces), updated every second. Auto-scales units from B/s through GB/s.
- **CPU**: Current CPU utilization percentage via `psutil`, sampled every second.
- **Memory**: Current RAM usage percentage via `psutil`, sampled every second.
- **GPU**: GPU utilization percentage read from macOS IOAccelerator via `ioreg`, sampled every 3 seconds to minimize subprocess overhead. Gracefully omitted if unavailable on the system.

Each monitoring complication is independently togglable from the menu bar.

### Appearance
- **Continuous scaling**: Resize the clock from 0.5x to 4.0x in 0.25 steps via the menu bar
- **Background**: Dark (semi-transparent black), Light (semi-transparent white), or fully Transparent
- **Text color**: Presets (White, Black, Red, Green, Yellow, Cyan) or any custom color via the native macOS color picker
- Sub-text and complication lines render at 35% of the main font size and 60% opacity for visual hierarchy
- Menu bar icon is a programmatically drawn clock face (template image — adapts to light/dark menu bar automatically)

### System Integration
- Runs as a macOS accessory app — no dock icon, no cmd-tab entry
- **Start at Login** toggle in the menu bar (manages a LaunchAgent plist)
- Right-click the clock for a context menu with all the same options
- Ctrl+C in the terminal cleanly quits the app (SIGINT handler + run loop nudge timer)
- All settings persisted to `~/.config/floating-clock/config.json`

## Install

### Homebrew (recommended)

```bash
brew tap surya-prakash-susarla/tap
brew install --cask floating-clock
```

### curl

```bash
curl -fsSL https://raw.githubusercontent.com/surya-prakash-susarla/OnScreenClock/main/install.sh | bash
```

The install script downloads the latest release to `/Applications`, optionally sets up start-at-login, and launches the app.

### Manual

1. Download `FloatingClock.zip` from the [latest release](https://github.com/surya-prakash-susarla/OnScreenClock/releases/latest)
2. Extract and move `FloatingClock.app` to `/Applications`
3. Open it — look for the clock icon in your menu bar

## Development

### Prerequisites

- macOS 12+
- Python 3.10+

### Setup

```bash
git clone https://github.com/surya-prakash-susarla/OnScreenClock.git
cd OnScreenClock
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python clock.py
```

### Project Structure

```
.
├── clock.py                    # Entire application (single file)
├── requirements.txt            # pyobjc-framework-Cocoa, psutil
├── setup.py                    # py2app build configuration
├── VERSION                     # Single source of truth for version number
├── build.sh                    # Build standalone .app (auto-bumps patch version)
├── release.sh                  # Create GitHub release + update cask formula
├── install.sh                  # curl-installable installer script
├── homebrew/floating-clock.rb  # Homebrew cask formula template
├── FEATURES.md                 # Feature request tracking
├── LICENSE                     # MIT License
└── README.md
```

### Architecture

The app is a single Python file (`clock.py`) using PyObjC to interface with native macOS APIs:

- **NSApplication** in accessory mode (no dock icon)
- **NSWindow** with `NSBorderlessWindowMask`, window level 1050 (above screen saver level), and `canJoinAllSpaces | fullScreenAuxiliary` collection behavior
- **DraggableView** (custom `NSView` subclass) handles mouse events for repositioning
- **NSStatusItem** provides the menu bar icon and dropdown menu
- **NSTimer** fires every 1 second for the main tick (clock update, timer countdown, network/CPU/memory sampling). A secondary 0.5-second timer nudges the Cocoa run loop so Python signal handlers can fire.
- **NSColorPanel** integration via `NSNotificationCenter` observation for live custom color picking
- **LaunchAgent plist** management via `plistlib` for start-at-login functionality
- **GPU monitoring** shells out to `ioreg -c IOAccelerator` every 3 ticks (3 seconds) and parses utilization via regex
- **Config persistence** via a simple JSON file at `~/.config/floating-clock/config.json`

### Configuration File

Stored at `~/.config/floating-clock/config.json`:

```json
{
  "scale": 1.0,
  "bg_color": [0.0, 0.0, 0.0, 0.55],
  "fg_color": [1.0, 1.0, 1.0, 1.0],
  "position": null,
  "show_seconds": true,
  "show_time_subtext": true,
  "show_network_stats": false,
  "show_cpu": false,
  "show_mem": false,
  "show_gpu": false
}
```

Color values are RGBA arrays (0.0–1.0). Position is `[x, y]` in screen coordinates or `null` for the default top-right corner.

## Release Process

### Building

```bash
bash build.sh
```

This will:
1. Auto-increment the patch version in `VERSION` (e.g., 0.0.1 → 0.0.2)
2. Create an isolated build virtualenv
3. Run `py2app` to produce a standalone `dist/FloatingClock.app`
4. Zip it to `dist/FloatingClock.zip`
5. Print the SHA-256 hash (needed for the Homebrew cask)

### Releasing

```bash
bash release.sh
```

This will:
1. Commit the version bump and create a git tag (`v0.0.2`)
2. Push the tag to GitHub
3. Create a GitHub release with the zip attached (using the `gh` CLI)
4. Update `homebrew/floating-clock.rb` with the new version and SHA-256

After running `release.sh`, copy the updated `homebrew/floating-clock.rb` to the [homebrew-tap](https://github.com/surya-prakash-susarla/homebrew-tap) repo at `Casks/floating-clock.rb` and push.

### Version Scheme

The project uses semantic versioning (`MAJOR.MINOR.PATCH`). The `build.sh` script auto-increments the patch number on every build. For minor or major bumps, edit the `VERSION` file manually before building.

## Contributing

Contributions are welcome! Here's how:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes — the entire app is in `clock.py`, so most changes are single-file edits
4. Test locally with `python clock.py`
5. Build and verify the .app with `bash build.sh && open dist/FloatingClock.app`
6. Commit with a clear message describing what and why
7. Open a Pull Request

### Guidelines

- Keep it single-file — `clock.py` should remain self-contained
- PyObjC quirks: all methods on `NSObject` subclasses become ObjC selectors. Use `@staticmethod` for pure Python helpers, or move them to module-level functions.
- Test on both Intel and Apple Silicon if possible
- GPU monitoring is best-effort — don't assume `ioreg` output format is stable across hardware

## License

[MIT](LICENSE)

import datetime
import json
import math
import os
import plistlib
import re
import signal
import subprocess
import sys

import objc
import psutil
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBorderlessWindowMask,
    NSButton,
    NSColor,
    NSColorPanel,
    NSFont,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSOnState,
    NSScreen,
    NSStatusBar,
    NSTextField,
    NSTimer,
    NSVariableStatusItemLength,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSBundle, NSNotificationCenter, NSObject

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUNDLE_ID = "com.suryaprakash.floatingclock"
CONFIG_DIR = os.path.expanduser("~/.config/floating-clock")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LAUNCHAGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
LAUNCHAGENT_PATH = os.path.join(LAUNCHAGENT_DIR, f"{BUNDLE_ID}.plist")

# Base dimensions at scale 1.0
BASE_FONT = 48
BASE_WIDTH = 380
BASE_HEIGHT = 80
BASE_RADIUS = 12
SUBTEXT_FONT_RATIO = 0.35
PADDING = 20

MIN_SCALE = 0.5
MAX_SCALE = 4.0
SCALE_STEP = 0.25

DEFAULT_CONFIG = {
    "scale": 1.0,
    "bg_color": [0.0, 0.0, 0.0, 0.55],
    "fg_color": [1.0, 1.0, 1.0, 1.0],
    "position": None,
    "show_seconds": True,
    "show_time_subtext": True,
    "show_network_stats": False,
    "show_cpu": False,
    "show_mem": False,
    "show_gpu": False,
}

BG_PRESETS = {
    "Dark":        [0.0, 0.0, 0.0, 0.55],
    "Light":       [1.0, 1.0, 1.0, 0.55],
    "Transparent": [0.0, 0.0, 0.0, 0.0],
}

FG_PRESETS = {
    "White":  [1.0, 1.0, 1.0, 1.0],
    "Black":  [0.0, 0.0, 0.0, 1.0],
    "Red":    [1.0, 0.0, 0.0, 1.0],
    "Green":  [0.0, 1.0, 0.0, 1.0],
    "Yellow": [1.0, 1.0, 0.0, 1.0],
    "Cyan":   [0.0, 1.0, 1.0, 1.0],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    if "size" in cfg and "scale" not in cfg:
        mapping = {"small": 0.5, "medium": 1.0, "large": 1.5}
        cfg["scale"] = mapping.get(cfg.pop("size"), 1.0)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def rgba_to_nscolor(rgba):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        rgba[0], rgba[1], rgba[2], rgba[3]
    )


def nscolor_to_rgba(color):
    c = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
    if c is None:
        return [1.0, 1.0, 1.0, 1.0]
    return [
        round(c.redComponent(), 3),
        round(c.greenComponent(), 3),
        round(c.blueComponent(), 3),
        round(c.alphaComponent(), 3),
    ]


def format_speed(bps):
    """Format bytes-per-second into a human-readable string."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    elif bps < 1024 * 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bps / (1024 * 1024 * 1024):.2f} GB/s"


def read_gpu_utilization():
    """Best-effort GPU utilization % via ioreg. Returns int or None."""
    try:
        out = subprocess.check_output(
            ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
            timeout=2,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        # Look for keys like "Device Utilization %" or "GPU Activity(%)"
        for m in re.finditer(
            r'"[^"]*[Uu]tilization[^"]*%?[^"]*"\s*=\s*(\d+)', out
        ):
            return int(m.group(1))
    except Exception:
        pass
    return None


def create_menu_bar_icon():
    """Draw a minimal black-and-white clock icon (template image)."""
    s = 18
    img = NSImage.alloc().initWithSize_((s, s))
    img.lockFocus()

    NSColor.blackColor().setStroke()
    NSColor.blackColor().setFill()

    cx, cy = s / 2, s / 2
    r = (s - 2) / 2

    circle = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(1, 1, s - 2, s - 2)
    )
    circle.setLineWidth_(1.5)
    circle.stroke()

    # Hour hand → 10 o'clock
    ha = math.radians(300)
    hl = r * 0.48
    hp = NSBezierPath.bezierPath()
    hp.moveToPoint_((cx, cy))
    hp.lineToPoint_((cx + hl * math.sin(ha), cy + hl * math.cos(ha)))
    hp.setLineWidth_(2.0)
    hp.stroke()

    # Minute hand → 2 o'clock
    ma = math.radians(60)
    ml = r * 0.72
    mp = NSBezierPath.bezierPath()
    mp.moveToPoint_((cx, cy))
    mp.lineToPoint_((cx + ml * math.sin(ma), cy + ml * math.cos(ma)))
    mp.setLineWidth_(1.3)
    mp.stroke()

    dot = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(cx - 1.2, cy - 1.2, 2.4, 2.4)
    )
    dot.fill()

    img.unlockFocus()
    img.setTemplate_(True)
    return img


def _get_app_executable():
    """Return the path to use in the LaunchAgent."""
    bundle = NSBundle.mainBundle()
    exe = bundle.executablePath()
    # When running as a .app bundle, executablePath points inside the .app
    if exe and ".app/Contents/MacOS/" in exe:
        return exe
    # Dev mode: fall back to the current Python + script
    return sys.executable + " " + os.path.abspath(__file__)


def is_start_at_login():
    return os.path.isfile(LAUNCHAGENT_PATH)


def enable_start_at_login():
    exe = _get_app_executable()
    # If it's a single executable (app bundle), use as-is; otherwise split
    if " " in exe:
        parts = exe.split(" ", 1)
        program_args = [parts[0], parts[1]]
    else:
        program_args = [exe]

    plist = {
        "Label": BUNDLE_ID,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
    }
    os.makedirs(LAUNCHAGENT_DIR, exist_ok=True)
    with open(LAUNCHAGENT_PATH, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(
        ["launchctl", "load", LAUNCHAGENT_PATH],
        capture_output=True,
    )


def disable_start_at_login():
    if os.path.isfile(LAUNCHAGENT_PATH):
        subprocess.run(
            ["launchctl", "unload", LAUNCHAGENT_PATH],
            capture_output=True,
        )
        os.remove(LAUNCHAGENT_PATH)


# ---------------------------------------------------------------------------
# Draggable View
# ---------------------------------------------------------------------------


class DraggableView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(DraggableView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._dragOffset = None
        return self

    def mouseDown_(self, event):
        self._dragOffset = event.locationInWindow()

    def mouseDragged_(self, event):
        if self._dragOffset is None:
            return
        window = self.window()
        loc = event.locationInWindow()
        origin = window.frame().origin
        window.setFrameOrigin_((
            origin.x + (loc.x - self._dragOffset.x),
            origin.y + (loc.y - self._dragOffset.y),
        ))

    def mouseUp_(self, event):
        window = self.window()
        if window is None:
            return
        delegate = NSApplication.sharedApplication().delegate()
        if delegate is not None:
            delegate.savePosition_(window.frame().origin)

    def rightMouseDown_(self, event):
        delegate = NSApplication.sharedApplication().delegate()
        if delegate is not None:
            menu = delegate.buildContextMenu()
            NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class ClockController(NSObject):

    def init(self):
        self = objc.super(ClockController, self).init()
        if self is None:
            return None
        self._window = None
        self._contentView = None
        self._mainLabel = None
        self._subLabel = None
        self._netLabel = None
        self._sysLabel = None
        self._statusItem = None
        self._config = load_config()

        # Timer state (runtime only)
        self._timer_total = 0
        self._timer_remaining = 0
        self._timer_running = False
        self._timer_active = False
        self._timer_finished = False
        self._flash_on = True
        self._timerInputField = None

        # Network stats state
        counters = psutil.net_io_counters()
        self._last_bytes_sent = counters.bytes_sent
        self._last_bytes_recv = counters.bytes_recv
        self._net_up_speed = 0.0
        self._net_down_speed = 0.0

        # System stats state
        psutil.cpu_percent(interval=None)  # prime the first reading
        self._gpu_pct = None
        self._tick_count = 0
        return self

    # -- dimensions ---------------------------------------------------------

    def _fontSize(self):
        return max(8, int(BASE_FONT * self._config["scale"]))

    def _subFontSize(self):
        return max(6, int(self._fontSize() * SUBTEXT_FONT_RATIO))

    def _showSubtext(self):
        return (
            self._timer_active
            and self._config.get("show_time_subtext", True)
        )

    def _showNetStats(self):
        return self._config.get("show_network_stats", False)

    def _showSysStats(self):
        return (
            self._config.get("show_cpu", False)
            or self._config.get("show_mem", False)
            or self._config.get("show_gpu", False)
        )

    def _extraLineCount(self):
        n = 0
        if self._showSubtext():
            n += 1
        if self._showNetStats():
            n += 1
        if self._showSysStats():
            n += 1
        return n

    def _windowSize(self):
        s = self._config["scale"]
        w = int(BASE_WIDTH * s)
        h = int(BASE_HEIGHT * s)
        extra = self._extraLineCount()
        if extra > 0:
            h = int(h * (1 + extra * 0.42))
        return w, h

    def _cornerRadius(self):
        return max(4, int(BASE_RADIUS * self._config["scale"]))

    # -- window setup -------------------------------------------------------

    def setupWindow(self):
        w, h = self._windowSize()

        pos = self._config.get("position")
        if pos:
            x, y = pos
        else:
            screen = NSScreen.mainScreen().frame()
            x = screen.size.width - w - PADDING
            y = screen.size.height - h - PADDING

        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False,
        )
        window.setLevel_(1050)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setIgnoresMouseEvents_(False)
        window.setHasShadow_(False)

        contentView = DraggableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, w, h)
        )
        contentView.setWantsLayer_(True)

        mainLabel = self._makeLabel()
        subLabel = self._makeLabel()
        subLabel.setHidden_(True)
        netLabel = self._makeLabel()
        netLabel.setHidden_(True)
        sysLabel = self._makeLabel()
        sysLabel.setHidden_(True)

        contentView.addSubview_(mainLabel)
        contentView.addSubview_(subLabel)
        contentView.addSubview_(netLabel)
        contentView.addSubview_(sysLabel)

        window.setContentView_(contentView)
        window.orderFrontRegardless()

        self._window = window
        self._contentView = contentView
        self._mainLabel = mainLabel
        self._subLabel = subLabel
        self._netLabel = netLabel
        self._sysLabel = sysLabel

        self._relayout()
        self.applyColors()
        self.tick()

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "tick", None, True,
        )

    @staticmethod
    def _makeLabel():
        label = NSTextField.labelWithString_("")
        label.setBackgroundColor_(NSColor.clearColor())
        label.setBezeled_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setAlignment_(1)
        return label

    # -- layout -------------------------------------------------------------

    def _relayout(self):
        w, h = self._windowSize()
        font_size = self._fontSize()
        sub_font_size = self._subFontSize()
        radius = self._cornerRadius()

        self._contentView.setFrame_(NSMakeRect(0, 0, w, h))
        self._contentView.layer().setCornerRadius_(radius)

        main_font = NSFont.fontWithName_size_("Menlo", font_size)
        sub_font = NSFont.fontWithName_size_("Menlo", sub_font_size)

        self._mainLabel.setFont_(main_font)
        self._subLabel.setFont_(sub_font)
        self._netLabel.setFont_(sub_font)
        self._sysLabel.setFont_(sub_font)

        show_sub = self._showSubtext()
        show_net = self._showNetStats()
        show_sys = self._showSysStats()
        self._subLabel.setHidden_(not show_sub)
        self._netLabel.setHidden_(not show_net)
        self._sysLabel.setHidden_(not show_sys)

        main_line_h = main_font.ascender() - main_font.descender() + main_font.leading()
        sub_line_h = sub_font.ascender() - sub_font.descender() + sub_font.leading()
        gap = max(2, int(font_size * 0.08))

        # Build list of (line_height, label) from visual top to bottom
        lines = [(main_line_h, self._mainLabel)]
        if show_sub:
            lines.append((sub_line_h, self._subLabel))
        if show_net:
            lines.append((sub_line_h, self._netLabel))
        if show_sys:
            lines.append((sub_line_h, self._sysLabel))

        total_h = sum(lh for lh, _ in lines) + gap * (len(lines) - 1)
        # In Cocoa, y=0 is bottom. Position stack from top down.
        cursor_y = (h + total_h) / 2  # top of the first line

        for line_h, label in lines:
            cursor_y -= line_h
            label.setFrame_(NSMakeRect(0, cursor_y, w, line_h))
            cursor_y -= gap

    def _resizeWindowKeepCenter(self):
        w, h = self._windowSize()
        frame = self._window.frame()
        cx = frame.origin.x + frame.size.width / 2
        cy = frame.origin.y + frame.size.height / 2
        new_x = cx - w / 2
        new_y = cy - h / 2
        self._window.setFrame_display_(NSMakeRect(new_x, new_y, w, h), True)
        self._relayout()
        self.applyColors()

    # -- menu bar -----------------------------------------------------------

    def setupMenuBar(self):
        statusBar = NSStatusBar.systemStatusBar()
        self._statusItem = statusBar.statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._statusItem.button().setImage_(create_menu_bar_icon())
        self._statusItem.setMenu_(self.buildContextMenu())

        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "colorPanelChanged:", "NSColorPanelColorDidChangeNotification", None,
        )

    def buildContextMenu(self):
        menu = NSMenu.alloc().initWithTitle_("FloatingClock")

        # -- Size -----------------------------------------------------------
        scale = self._config["scale"]
        sizeMenu = NSMenu.alloc().initWithTitle_("Size")

        incItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Increase (+)", "scaleUp:", "+",
        )
        incItem.setTarget_(self)
        if scale >= MAX_SCALE:
            incItem.setEnabled_(False)
        sizeMenu.addItem_(incItem)

        decItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Decrease (\u2212)", "scaleDown:", "-",
        )
        decItem.setTarget_(self)
        if scale <= MIN_SCALE:
            decItem.setEnabled_(False)
        sizeMenu.addItem_(decItem)

        sizeItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Size ({scale:.2f}x)", None, "",
        )
        sizeItem.setSubmenu_(sizeMenu)
        menu.addItem_(sizeItem)

        # -- Background -----------------------------------------------------
        bgMenu = NSMenu.alloc().initWithTitle_("Background")
        for name, rgba in BG_PRESETS.items():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, "changeBgColor:", "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(name)
            if self._config["bg_color"] == rgba:
                item.setState_(NSOnState)
            bgMenu.addItem_(item)

        bgItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Background", None, "",
        )
        bgItem.setSubmenu_(bgMenu)
        menu.addItem_(bgItem)

        # -- Text color -----------------------------------------------------
        fgMenu = NSMenu.alloc().initWithTitle_("Text Color")
        current_fg = self._config["fg_color"]
        for name, rgba in FG_PRESETS.items():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, "changeFgColor:", "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(name)
            if current_fg == rgba:
                item.setState_(NSOnState)
            fgMenu.addItem_(item)

        fgMenu.addItem_(NSMenuItem.separatorItem())
        customItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Custom\u2026", "openColorPicker:", "",
        )
        customItem.setTarget_(self)
        if current_fg not in FG_PRESETS.values():
            customItem.setState_(NSOnState)
        fgMenu.addItem_(customItem)

        fgItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Text Color", None, "",
        )
        fgItem.setSubmenu_(fgMenu)
        menu.addItem_(fgItem)

        # -- Show Seconds ---------------------------------------------------
        menu.addItem_(NSMenuItem.separatorItem())
        secItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Show Seconds", "toggleSeconds:", "",
        )
        secItem.setTarget_(self)
        if self._config["show_seconds"]:
            secItem.setState_(NSOnState)
        menu.addItem_(secItem)

        # -- Network Stats --------------------------------------------------
        netItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Network Stats", "toggleNetStats:", "",
        )
        netItem.setTarget_(self)
        if self._config.get("show_network_stats", False):
            netItem.setState_(NSOnState)
        menu.addItem_(netItem)

        # -- System Stats submenu -------------------------------------------
        sysMenu = NSMenu.alloc().initWithTitle_("System Stats")

        cpuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "CPU", "toggleCpu:", "",
        )
        cpuItem.setTarget_(self)
        if self._config.get("show_cpu", False):
            cpuItem.setState_(NSOnState)
        sysMenu.addItem_(cpuItem)

        memItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Memory", "toggleMem:", "",
        )
        memItem.setTarget_(self)
        if self._config.get("show_mem", False):
            memItem.setState_(NSOnState)
        sysMenu.addItem_(memItem)

        gpuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "GPU", "toggleGpu:", "",
        )
        gpuItem.setTarget_(self)
        if self._config.get("show_gpu", False):
            gpuItem.setState_(NSOnState)
        sysMenu.addItem_(gpuItem)

        sysItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "System Stats", None, "",
        )
        sysItem.setSubmenu_(sysMenu)
        menu.addItem_(sysItem)

        # -- Timer ----------------------------------------------------------
        menu.addItem_(NSMenuItem.separatorItem())
        timerMenu = NSMenu.alloc().initWithTitle_("Timer")

        # Quick presets
        presets = [("15 min", 15 * 60), ("30 min", 30 * 60),
                   ("1 hour", 3600), ("2 hours", 7200), ("3 hours", 10800)]
        for label, secs in presets:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "timerStartPreset:", "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(secs)
            timerMenu.addItem_(item)
        timerMenu.addItem_(NSMenuItem.separatorItem())

        # Inline input row
        inputView = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 220, 28))
        timerField = NSTextField.alloc().initWithFrame_(
            NSMakeRect(12, 4, 130, 22)
        )
        timerField.setFont_(NSFont.fontWithName_size_("Menlo", 13))
        timerField.setPlaceholderString_("HH:MM:SS")
        if self._timerInputField is not None:
            timerField.setStringValue_(self._timerInputField.stringValue())
        else:
            timerField.setStringValue_("00:05:00")
        inputView.addSubview_(timerField)
        self._timerInputField = timerField

        startBtn = NSButton.alloc().initWithFrame_(NSMakeRect(148, 3, 60, 24))
        startBtn.setTitle_("Start")
        startBtn.setBezelStyle_(1)
        startBtn.setFont_(NSFont.systemFontOfSize_(12))
        startBtn.setTarget_(self)
        startBtn.setAction_("timerStartFromInput:")
        inputView.addSubview_(startBtn)

        inputItem = NSMenuItem.alloc().init()
        inputItem.setView_(inputView)
        timerMenu.addItem_(inputItem)

        timerMenu.addItem_(NSMenuItem.separatorItem())

        pauseItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause", "timerPause:", "",
        )
        pauseItem.setTarget_(self)
        pauseItem.setEnabled_(self._timer_running)
        timerMenu.addItem_(pauseItem)

        resetItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reset", "timerReset:", "",
        )
        resetItem.setTarget_(self)
        resetItem.setEnabled_(self._timer_active)
        timerMenu.addItem_(resetItem)

        if self._timer_active:
            timerMenu.addItem_(NSMenuItem.separatorItem())
            subTextItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Show Current Time", "toggleSubtext:", "",
            )
            subTextItem.setTarget_(self)
            if self._config.get("show_time_subtext", True):
                subTextItem.setState_(NSOnState)
            timerMenu.addItem_(subTextItem)

        timerItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Timer", None, "",
        )
        timerItem.setSubmenu_(timerMenu)
        menu.addItem_(timerItem)

        # -- Reset position / Quit -----------------------------------------
        menu.addItem_(NSMenuItem.separatorItem())

        rpItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reset Position", "resetPosition:", "",
        )
        rpItem.setTarget_(self)
        menu.addItem_(rpItem)

        loginItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start at Login", "toggleStartAtLogin:", "",
        )
        loginItem.setTarget_(self)
        if is_start_at_login():
            loginItem.setState_(NSOnState)
        menu.addItem_(loginItem)

        menu.addItem_(NSMenuItem.separatorItem())

        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q",
        )
        menu.addItem_(quitItem)

        return menu

    # -- actions: scale -----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def scaleUp_(self, sender):
        s = min(MAX_SCALE, round(self._config["scale"] + SCALE_STEP, 2))
        self._config["scale"] = s
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def scaleDown_(self, sender):
        s = max(MIN_SCALE, round(self._config["scale"] - SCALE_STEP, 2))
        self._config["scale"] = s
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    # -- actions: colors ----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def changeBgColor_(self, sender):
        self._config["bg_color"] = list(BG_PRESETS[sender.representedObject()])
        save_config(self._config)
        self.applyColors()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def changeFgColor_(self, sender):
        self._config["fg_color"] = list(FG_PRESETS[sender.representedObject()])
        save_config(self._config)
        self.applyColors()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def openColorPicker_(self, sender):
        panel = NSColorPanel.sharedColorPanel()
        panel.setColor_(rgba_to_nscolor(self._config["fg_color"]))
        panel.setShowsAlpha_(True)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel.orderFront_(None)

    @objc.typedSelector(b"v@:@")
    def colorPanelChanged_(self, notification):
        rgba = nscolor_to_rgba(notification.object().color())
        self._config["fg_color"] = rgba
        save_config(self._config)
        self.applyColors()
        self.refreshMenus()

    # -- actions: toggles ---------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def toggleSeconds_(self, sender):
        self._config["show_seconds"] = not self._config["show_seconds"]
        save_config(self._config)
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleNetStats_(self, sender):
        self._config["show_network_stats"] = not self._config.get(
            "show_network_stats", False
        )
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleCpu_(self, sender):
        self._config["show_cpu"] = not self._config.get("show_cpu", False)
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleMem_(self, sender):
        self._config["show_mem"] = not self._config.get("show_mem", False)
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleGpu_(self, sender):
        self._config["show_gpu"] = not self._config.get("show_gpu", False)
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    # -- actions: timer -----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def timerStartFromInput_(self, sender):
        if self._timerInputField is None:
            return
        text = self._timerInputField.stringValue().strip()
        seconds = self._parseTimerInput(text)
        if seconds is None or seconds <= 0:
            return
        self._timer_total = seconds
        self._timer_remaining = seconds
        self._timer_active = True
        self._timer_running = True
        self._timer_finished = False
        self._flash_on = True
        self._mainLabel.setAlphaValue_(1.0)
        if self._statusItem and self._statusItem.menu():
            self._statusItem.menu().cancelTracking()
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def timerStartPreset_(self, sender):
        seconds = sender.representedObject()
        self._timer_total = seconds
        self._timer_remaining = seconds
        self._timer_active = True
        self._timer_running = True
        self._timer_finished = False
        self._flash_on = True
        self._mainLabel.setAlphaValue_(1.0)
        if self._statusItem and self._statusItem.menu():
            self._statusItem.menu().cancelTracking()
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @staticmethod
    def _parseTimerInput(text):
        parts = text.split(":")
        try:
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = int(parts[0]), int(parts[1])
                return m * 60 + s
            elif len(parts) == 1:
                return int(parts[0])
        except ValueError:
            pass
        return None

    @objc.typedSelector(b"v@:@")
    def timerPause_(self, sender):
        self._timer_running = False
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def timerReset_(self, sender):
        self._timer_running = False
        self._timer_active = False
        self._timer_finished = False
        self._timer_remaining = 0
        self._timer_total = 0
        self._flash_on = True
        self._mainLabel.setAlphaValue_(1.0)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleSubtext_(self, sender):
        self._config["show_time_subtext"] = not self._config.get(
            "show_time_subtext", True
        )
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    # -- actions: start at login --------------------------------------------

    @objc.typedSelector(b"v@:@")
    def toggleStartAtLogin_(self, sender):
        if is_start_at_login():
            disable_start_at_login()
        else:
            enable_start_at_login()
        self.refreshMenus()

    # -- actions: position --------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def resetPosition_(self, sender):
        w, h = self._windowSize()
        screen = NSScreen.mainScreen().frame()
        x = screen.size.width - w - PADDING
        y = screen.size.height - h - PADDING
        self._window.setFrameOrigin_((x, y))
        self._config["position"] = None
        save_config(self._config)

    def savePosition_(self, origin):
        self._config["position"] = [origin.x, origin.y]
        save_config(self._config)

    # -- apply helpers ------------------------------------------------------

    def applyColors(self):
        bg = self._config["bg_color"]
        fg = self._config["fg_color"]
        self._contentView.layer().setBackgroundColor_(
            rgba_to_nscolor(bg).CGColor()
        )
        fg_color = rgba_to_nscolor(fg)
        self._mainLabel.setTextColor_(fg_color)
        # Secondary labels at 60% opacity
        sub_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            fg[0], fg[1], fg[2], fg[3] * 0.6,
        )
        self._subLabel.setTextColor_(sub_color)
        self._netLabel.setTextColor_(sub_color)
        self._sysLabel.setTextColor_(sub_color)

    def refreshMenus(self):
        if self._statusItem is not None:
            self._statusItem.setMenu_(self.buildContextMenu())

    # -- tick (every second) ------------------------------------------------

    def tick(self):
        self._tick_count += 1
        show_secs = self._config["show_seconds"]
        fmt = "%H:%M:%S" if show_secs else "%H:%M"
        now_str = datetime.datetime.now().strftime(fmt)

        # -- update timer ---------------------------------------------------
        if self._timer_active:
            if self._timer_running and self._timer_remaining > 0:
                self._timer_remaining -= 1
                if self._timer_remaining <= 0:
                    self._timer_remaining = 0
                    self._timer_running = False
                    self._timer_finished = True
                    self.refreshMenus()

            rem = self._timer_remaining
            th, tm, ts = rem // 3600, (rem % 3600) // 60, rem % 60
            if show_secs:
                self._mainLabel.setStringValue_(f"{th:02d}:{tm:02d}:{ts:02d}")
            else:
                self._mainLabel.setStringValue_(f"{th:02d}:{tm:02d}")

            # Flash the display when timer is finished
            if self._timer_finished:
                self._flash_on = not self._flash_on
                alpha = 1.0 if self._flash_on else 0.0
                self._mainLabel.setAlphaValue_(alpha)
            else:
                self._mainLabel.setAlphaValue_(1.0)

            if self._showSubtext():
                self._subLabel.setStringValue_(now_str)
        else:
            self._mainLabel.setStringValue_(now_str)

        # -- update network stats -------------------------------------------
        if self._showNetStats():
            counters = psutil.net_io_counters()
            up = counters.bytes_sent - self._last_bytes_sent
            down = counters.bytes_recv - self._last_bytes_recv
            self._last_bytes_sent = counters.bytes_sent
            self._last_bytes_recv = counters.bytes_recv
            self._net_up_speed = up
            self._net_down_speed = down
            self._netLabel.setStringValue_(
                f"\u2191 {format_speed(up)}  \u2193 {format_speed(down)}"
            )

        # -- update system stats --------------------------------------------
        if self._showSysStats():
            parts = []
            if self._config.get("show_cpu", False):
                parts.append(f"CPU {psutil.cpu_percent(interval=None):.0f}%")
            if self._config.get("show_mem", False):
                parts.append(f"MEM {psutil.virtual_memory().percent:.0f}%")
            if self._config.get("show_gpu", False):
                if self._tick_count % 3 == 0:
                    self._gpu_pct = read_gpu_utilization()
                if self._gpu_pct is not None:
                    parts.append(f"GPU {self._gpu_pct}%")
            self._sysLabel.setStringValue_("  ".join(parts))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = ClockController.alloc().init()
    controller.setupWindow()
    controller.setupMenuBar()
    app.setDelegate_(controller)

    def handle_sigint(sig, frame):
        NSApplication.sharedApplication().terminate_(None)

    signal.signal(signal.SIGINT, handle_sigint)

    # Nudge the run loop so Python signal handlers fire
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.5, controller, "tick", None, True,
    )

    app.run()


if __name__ == "__main__":
    main()

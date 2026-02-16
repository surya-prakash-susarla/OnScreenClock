import datetime
import json
import os
import signal

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSColor,
    NSColorPanel,
    NSFont,
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
from Foundation import NSNotificationCenter, NSObject

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = os.path.expanduser("~/.config/floating-clock")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Base dimensions at scale 1.0
BASE_FONT = 48
BASE_WIDTH = 380
BASE_HEIGHT = 80
BASE_RADIUS = 12
SUBTEXT_FONT_RATIO = 0.35
SUBTEXT_HEIGHT_EXTRA = 1.5  # height multiplier when sub-text is visible
PADDING = 20

MIN_SCALE = 0.5
MAX_SCALE = 4.0
SCALE_STEP = 0.5

DEFAULT_CONFIG = {
    "scale": 1.0,
    "bg_color": [0.0, 0.0, 0.0, 0.55],
    "fg_color": [1.0, 1.0, 1.0, 1.0],
    "position": None,
    "show_seconds": True,
    "show_time_subtext": True,
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
# Config helpers
# ---------------------------------------------------------------------------


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    # Migrate old "size" key to "scale"
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
        self._statusItem = None
        self._config = load_config()

        # Timer state (runtime only, not persisted)
        self._timer_total = 0       # total seconds set by user
        self._timer_remaining = 0   # seconds left
        self._timer_running = False  # actively counting down
        self._timer_active = False   # timer mode engaged (even if paused)
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

    def _windowSize(self):
        s = self._config["scale"]
        w = int(BASE_WIDTH * s)
        h = int(BASE_HEIGHT * s)
        if self._showSubtext():
            h = int(h * SUBTEXT_HEIGHT_EXTRA)
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

        # Main time label
        mainLabel = NSTextField.labelWithString_("")
        mainLabel.setBackgroundColor_(NSColor.clearColor())
        mainLabel.setBezeled_(False)
        mainLabel.setEditable_(False)
        mainLabel.setSelectable_(False)
        mainLabel.setAlignment_(1)  # NSTextAlignmentCenter
        contentView.addSubview_(mainLabel)

        # Sub label (current time shown below timer)
        subLabel = NSTextField.labelWithString_("")
        subLabel.setBackgroundColor_(NSColor.clearColor())
        subLabel.setBezeled_(False)
        subLabel.setEditable_(False)
        subLabel.setSelectable_(False)
        subLabel.setAlignment_(1)
        subLabel.setHidden_(True)
        contentView.addSubview_(subLabel)

        window.setContentView_(contentView)
        window.orderFrontRegardless()

        self._window = window
        self._contentView = contentView
        self._mainLabel = mainLabel
        self._subLabel = subLabel

        self._relayout()
        self.applyColors()
        self.tick()

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "tick", None, True,
        )

    # -- layout -------------------------------------------------------------

    def _relayout(self):
        w, h = self._windowSize()
        font_size = self._fontSize()
        sub_font_size = self._subFontSize()
        radius = self._cornerRadius()

        self._contentView.setFrame_(NSMakeRect(0, 0, w, h))
        self._contentView.layer().setCornerRadius_(radius)

        font = NSFont.fontWithName_size_("Menlo", font_size)
        self._mainLabel.setFont_(font)

        show_sub = self._showSubtext()
        self._subLabel.setHidden_(not show_sub)

        if show_sub:
            sub_font = NSFont.fontWithName_size_("Menlo", sub_font_size)
            self._subLabel.setFont_(sub_font)

            sub_line_h = sub_font.ascender() - sub_font.descender() + sub_font.leading()
            main_line_h = font.ascender() - font.descender() + font.leading()
            gap = max(2, int(font_size * 0.08))
            total_text_h = main_line_h + gap + sub_line_h
            top_pad = (h - total_text_h) / 2

            main_y = top_pad + sub_line_h + gap
            self._mainLabel.setFrame_(NSMakeRect(0, 0, w, main_y + main_line_h))
            sub_y = top_pad
            self._subLabel.setFrame_(NSMakeRect(0, 0, w, sub_y + sub_line_h))
        else:
            # Vertically center the main label
            line_h = font.ascender() - font.descender() + font.leading()
            y_offset = (h - line_h) / 2
            self._mainLabel.setFrame_(NSMakeRect(0, y_offset, w, line_h))

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
        self._statusItem.button().setTitle_("\u23f0")
        self._statusItem.setMenu_(self.buildContextMenu())

        # Observe color panel changes
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "colorPanelChanged:", "NSColorPanelColorDidChangeNotification", None,
        )

    def buildContextMenu(self):
        menu = NSMenu.alloc().initWithTitle_("FloatingClock")

        # -- Size controls --------------------------------------------------
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
            f"Size ({scale:.1f}x)", None, "",
        )
        sizeItem.setSubmenu_(sizeMenu)
        menu.addItem_(sizeItem)

        # -- Background submenu ---------------------------------------------
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

        # -- Text color submenu ---------------------------------------------
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
        # Mark custom if current fg doesn't match any preset
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

        # -- Timer submenu --------------------------------------------------
        menu.addItem_(NSMenuItem.separatorItem())
        timerMenu = NSMenu.alloc().initWithTitle_("Timer")

        setItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Set Timer\u2026", "showTimerInput:", "",
        )
        setItem.setTarget_(self)
        timerMenu.addItem_(setItem)

        timerMenu.addItem_(NSMenuItem.separatorItem())

        startItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start", "timerStart:", "",
        )
        startItem.setTarget_(self)
        startItem.setEnabled_(self._timer_active and not self._timer_running)
        timerMenu.addItem_(startItem)

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

        menu.addItem_(NSMenuItem.separatorItem())

        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q",
        )
        menu.addItem_(quitItem)

        return menu

    # -- actions: scale -----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def scaleUp_(self, sender):
        s = self._config["scale"]
        s = min(MAX_SCALE, round(s + SCALE_STEP, 1))
        self._config["scale"] = s
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def scaleDown_(self, sender):
        s = self._config["scale"]
        s = max(MIN_SCALE, round(s - SCALE_STEP, 1))
        self._config["scale"] = s
        save_config(self._config)
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    # -- actions: colors ----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def changeBgColor_(self, sender):
        name = sender.representedObject()
        self._config["bg_color"] = list(BG_PRESETS[name])
        save_config(self._config)
        self.applyColors()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def changeFgColor_(self, sender):
        name = sender.representedObject()
        self._config["fg_color"] = list(FG_PRESETS[name])
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
        panel = notification.object()
        rgba = nscolor_to_rgba(panel.color())
        self._config["fg_color"] = rgba
        save_config(self._config)
        self.applyColors()
        self.refreshMenus()

    # -- actions: seconds toggle --------------------------------------------

    @objc.typedSelector(b"v@:@")
    def toggleSeconds_(self, sender):
        self._config["show_seconds"] = not self._config["show_seconds"]
        save_config(self._config)
        self.refreshMenus()

    # -- actions: timer -----------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def showTimerInput_(self, sender):
        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Set Timer")
        alert.setInformativeText_("Enter duration (HH:MM:SS or MM:SS):")
        alert.addButtonWithTitle_("Start")
        alert.addButtonWithTitle_("Cancel")

        inputField = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        inputField.setStringValue_("00:05:00")
        alert.setAccessoryView_(inputField)

        response = alert.runModal()
        if response != NSAlertFirstButtonReturn:
            return

        text = inputField.stringValue().strip()
        seconds = self._parseTimerInput(text)
        if seconds is None or seconds <= 0:
            return

        self._timer_total = seconds
        self._timer_remaining = seconds
        self._timer_active = True
        self._timer_running = True
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
    def timerStart_(self, sender):
        if self._timer_active and self._timer_remaining > 0:
            self._timer_running = True
            self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def timerPause_(self, sender):
        self._timer_running = False
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def timerReset_(self, sender):
        self._timer_running = False
        self._timer_active = False
        self._timer_remaining = 0
        self._timer_total = 0
        self._resizeWindowKeepCenter()
        self.refreshMenus()

    @objc.typedSelector(b"v@:@")
    def toggleSubtext_(self, sender):
        cur = self._config.get("show_time_subtext", True)
        self._config["show_time_subtext"] = not cur
        save_config(self._config)
        self._resizeWindowKeepCenter()
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
        # Sub-text at 60% opacity of the main color
        sub_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            fg[0], fg[1], fg[2], fg[3] * 0.6,
        )
        self._subLabel.setTextColor_(sub_color)

    def refreshMenus(self):
        newMenu = self.buildContextMenu()
        if self._statusItem is not None:
            self._statusItem.setMenu_(newMenu)

    # -- tick (every second) ------------------------------------------------

    def tick(self):
        show_secs = self._config["show_seconds"]
        fmt = "%H:%M:%S" if show_secs else "%H:%M"
        now_str = datetime.datetime.now().strftime(fmt)

        if self._timer_active:
            if self._timer_running and self._timer_remaining > 0:
                self._timer_remaining -= 1
                if self._timer_remaining <= 0:
                    self._timer_remaining = 0
                    self._timer_running = False
                    self.refreshMenus()

            rem = self._timer_remaining
            th = rem // 3600
            tm = (rem % 3600) // 60
            ts = rem % 60
            if show_secs:
                timer_str = f"{th:02d}:{tm:02d}:{ts:02d}"
            else:
                timer_str = f"{th:02d}:{tm:02d}"
            self._mainLabel.setStringValue_(timer_str)

            if self._showSubtext():
                self._subLabel.setStringValue_(now_str)
        else:
            self._mainLabel.setStringValue_(now_str)


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

    # Ctrl+C support
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

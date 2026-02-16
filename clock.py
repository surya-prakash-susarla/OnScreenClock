import datetime
import json
import os
import signal

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSOffState,
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
from Foundation import NSObject

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = os.path.expanduser("~/.config/floating-clock")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "size": "medium",
    "bg_color": [0.0, 0.0, 0.0, 0.55],
    "fg_color": [1.0, 1.0, 1.0, 1.0],
    "position": None,  # None means default top-right
}

SIZE_PRESETS = {
    "small":  {"font": 16, "width": 140, "height": 32, "radius": 7},
    "medium": {"font": 24, "width": 200, "height": 44, "radius": 10},
    "large":  {"font": 36, "width": 300, "height": 64, "radius": 14},
}

BG_PRESETS = {
    "Dark":        [0.0, 0.0, 0.0, 0.55],
    "Light":       [1.0, 1.0, 1.0, 0.55],
    "Transparent": [0.0, 0.0, 0.0, 0.0],
}

FG_PRESETS = {
    "White":  [1.0, 1.0, 1.0, 1.0],
    "Black":  [0.0, 0.0, 0.0, 1.0],
    "Green":  [0.0, 1.0, 0.0, 1.0],
    "Yellow": [1.0, 1.0, 0.0, 1.0],
    "Cyan":   [0.0, 1.0, 1.0, 1.0],
}

PADDING = 20


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        # Merge with defaults for any missing keys
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def rgba_to_nscolor(rgba):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        rgba[0], rgba[1], rgba[2], rgba[3]
    )


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
        # Persist position after drag
        window = self.window()
        if window is None:
            return
        origin = window.frame().origin
        app = NSApplication.sharedApplication()
        delegate = app.delegate()
        if delegate is not None:
            delegate.savePosition_(origin)

    def rightMouseDown_(self, event):
        app = NSApplication.sharedApplication()
        delegate = app.delegate()
        if delegate is not None:
            menu = delegate.buildContextMenu()
            NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)


# ---------------------------------------------------------------------------
# App Delegate / Controller
# ---------------------------------------------------------------------------

class ClockController(NSObject):

    def init(self):
        self = objc.super(ClockController, self).init()
        if self is None:
            return None
        self._label = None
        self._window = None
        self._contentView = None
        self._statusItem = None
        self._config = load_config()
        return self

    # -- window setup -------------------------------------------------------

    def setupWindow(self):
        preset = SIZE_PRESETS[self._config["size"]]
        w, h = preset["width"], preset["height"]

        pos = self._config.get("position")
        if pos:
            x, y = pos
        else:
            screen = NSScreen.mainScreen().frame()
            x = screen.size.width - w - PADDING
            y = screen.size.height - h - PADDING

        rect = NSMakeRect(x, y, w, h)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSBorderlessWindowMask, NSBackingStoreBuffered, False,
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

        label = NSTextField.labelWithString_("")
        label.setFrame_(NSMakeRect(0, 0, w, h))
        label.setFont_(NSFont.fontWithName_size_("Menlo", preset["font"]))
        label.setBackgroundColor_(NSColor.clearColor())
        label.setBezeled_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setAlignment_(1)  # center
        contentView.addSubview_(label)

        window.setContentView_(contentView)
        window.orderFrontRegardless()

        self._window = window
        self._contentView = contentView
        self._label = label

        self.applyColors()
        self.updateTime()

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "updateTime", None, True,
        )

    # -- menu bar -----------------------------------------------------------

    def setupMenuBar(self):
        statusBar = NSStatusBar.systemStatusBar()
        self._statusItem = statusBar.statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._statusItem.button().setTitle_("\u23f0")  # alarm clock emoji
        self._statusItem.setMenu_(self.buildContextMenu())

    def buildContextMenu(self):
        menu = NSMenu.alloc().initWithTitle_("FloatingClock")

        # -- Size submenu ---------------------------------------------------
        sizeMenu = NSMenu.alloc().initWithTitle_("Size")
        for name in ("small", "medium", "large"):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name.capitalize(), "changeSize:", "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(name)
            if self._config["size"] == name:
                item.setState_(NSOnState)
            sizeMenu.addItem_(item)

        sizeItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Size", None, "",
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
        for name, rgba in FG_PRESETS.items():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, "changeFgColor:", "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(name)
            if self._config["fg_color"] == rgba:
                item.setState_(NSOnState)
            fgMenu.addItem_(item)

        fgItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Text Color", None, "",
        )
        fgItem.setSubmenu_(fgMenu)
        menu.addItem_(fgItem)

        # -- Reset / Quit ---------------------------------------------------
        menu.addItem_(NSMenuItem.separatorItem())

        resetItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reset Position", "resetPosition:", "",
        )
        resetItem.setTarget_(self)
        menu.addItem_(resetItem)

        menu.addItem_(NSMenuItem.separatorItem())

        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q",
        )
        menu.addItem_(quitItem)

        return menu

    # -- actions ------------------------------------------------------------

    @objc.typedSelector(b"v@:@")
    def changeSize_(self, sender):
        name = sender.representedObject()
        self._config["size"] = name
        save_config(self._config)
        self.applySize()
        self.refreshMenus()

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
    def resetPosition_(self, sender):
        preset = SIZE_PRESETS[self._config["size"]]
        screen = NSScreen.mainScreen().frame()
        x = screen.size.width - preset["width"] - PADDING
        y = screen.size.height - preset["height"] - PADDING
        self._window.setFrameOrigin_((x, y))
        self._config["position"] = None
        save_config(self._config)

    def savePosition_(self, origin):
        self._config["position"] = [origin.x, origin.y]
        save_config(self._config)

    # -- apply helpers ------------------------------------------------------

    def applySize(self):
        preset = SIZE_PRESETS[self._config["size"]]
        w, h = preset["width"], preset["height"]

        # Keep current center position
        frame = self._window.frame()
        cx = frame.origin.x + frame.size.width / 2
        cy = frame.origin.y + frame.size.height / 2
        newX = cx - w / 2
        newY = cy - h / 2

        self._window.setFrame_display_(NSMakeRect(newX, newY, w, h), True)
        self._contentView.setFrame_(NSMakeRect(0, 0, w, h))
        self._contentView.layer().setCornerRadius_(preset["radius"])
        self._label.setFrame_(NSMakeRect(0, 0, w, h))
        self._label.setFont_(NSFont.fontWithName_size_("Menlo", preset["font"]))

        self._config["position"] = [newX, newY]
        save_config(self._config)

    def applyColors(self):
        bg = self._config["bg_color"]
        fg = self._config["fg_color"]
        self._contentView.layer().setBackgroundColor_(
            rgba_to_nscolor(bg).CGColor()
        )
        self._label.setTextColor_(rgba_to_nscolor(fg))

    def refreshMenus(self):
        newMenu = self.buildContextMenu()
        if self._statusItem is not None:
            self._statusItem.setMenu_(newMenu)

    # -- timer --------------------------------------------------------------

    def updateTime(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        if self._label is not None:
            self._label.setStringValue_(now)


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

    # SIGINT handler so Ctrl+C works
    def handle_sigint(sig, frame):
        NSApplication.sharedApplication().terminate_(None)

    signal.signal(signal.SIGINT, handle_sigint)

    # Keepalive timer — nudges the run loop so Python signal handlers fire
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.5, controller, "updateTime", None, True,
    )

    app.run()


if __name__ == "__main__":
    main()

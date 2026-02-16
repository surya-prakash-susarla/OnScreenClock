import datetime

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBorderlessWindowMask,
    NSColor,
    NSEvent,
    NSFont,
    NSMenu,
    NSMenuItem,
    NSMakeRect,
    NSRightMouseDown,
    NSScreen,
    NSTextField,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSObject


CLOCK_WIDTH = 200
CLOCK_HEIGHT = 44
PADDING = 20
FONT_SIZE = 24
CORNER_RADIUS = 10


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
        screenLoc = event.locationInWindow()
        currentOrigin = window.frame().origin
        newX = currentOrigin.x + (screenLoc.x - self._dragOffset.x)
        newY = currentOrigin.y + (screenLoc.y - self._dragOffset.y)
        window.setFrameOrigin_((newX, newY))

    def rightMouseDown_(self, event):
        menu = NSMenu.alloc().initWithTitle_("Context")
        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", ""
        )
        menu.addItem_(quitItem)
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)


class ClockController(NSObject):
    def init(self):
        self = objc.super(ClockController, self).init()
        if self is None:
            return None
        self._label = None
        self._window = None
        return self

    def setupWindow(self):
        screen = NSScreen.mainScreen()
        screenFrame = screen.frame()
        x = screenFrame.size.width - CLOCK_WIDTH - PADDING
        y = screenFrame.size.height - CLOCK_HEIGHT - PADDING

        rect = NSMakeRect(x, y, CLOCK_WIDTH, CLOCK_HEIGHT)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSBorderlessWindowMask,
            NSBackingStoreBuffered,
            False,
        )

        # Screen-saver level + 1 to float above full-screen apps
        window.setLevel_(1050)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setIgnoresMouseEvents_(False)
        window.setHasShadow_(False)

        # Draggable content view with rounded dark background
        contentView = DraggableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, CLOCK_WIDTH, CLOCK_HEIGHT)
        )
        contentView.setWantsLayer_(True)
        layer = contentView.layer()
        layer.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.55).CGColor()
        )
        layer.setCornerRadius_(CORNER_RADIUS)

        # Clock label
        label = NSTextField.labelWithString_("")
        label.setFrame_(NSMakeRect(0, 0, CLOCK_WIDTH, CLOCK_HEIGHT))
        label.setFont_(NSFont.fontWithName_size_("Menlo", FONT_SIZE))
        label.setTextColor_(NSColor.whiteColor())
        label.setBackgroundColor_(NSColor.clearColor())
        label.setBezeled_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setAlignment_(1)  # NSTextAlignmentCenter
        contentView.addSubview_(label)

        window.setContentView_(contentView)
        window.orderFrontRegardless()

        self._label = label
        self._window = window

        # Update immediately, then every second
        self.updateTime()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "updateTime", None, True
        )

    def updateTime(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._label.setStringValue_(now)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = ClockController.alloc().init()
    controller.setupWindow()

    app.run()


if __name__ == "__main__":
    main()

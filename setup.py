import os
from setuptools import setup

VERSION = open(os.path.join(os.path.dirname(__file__), "VERSION")).read().strip()

APP = ["clock.py"]

OPTIONS = {
    "argv_emulation": False,
    "packages": ["psutil"],
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "FloatingClock",
        "CFBundleDisplayName": "Floating Clock",
        "CFBundleIdentifier": "com.suryaprakash.floatingclock",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
    },
}

setup(
    name="FloatingClock",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

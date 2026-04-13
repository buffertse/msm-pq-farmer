"""
Interactive template creator — capture template images from the running emulator.

Usage:
    python -m tools.template_creator [--port 5555] [--output templates]

Controls:
    Left-click + drag  = select region
    Right-click        = tap in game (navigate menus)
    C                  = capture fresh screenshot
    S                  = save selection as template
    Q / Esc            = quit
"""

import sys
import argparse
import numpy as np
from pathlib import Path

try:
    import cv2
except ImportError:
    print("OpenCV is required: pip install opencv-python")
    sys.exit(1)

from core.adb_controller import ADBController
from core.screen_capture import ScreenCapture


class TemplateCreator:

    def __init__(self, adb: ADBController, capture: ScreenCapture, output_dir: str = "templates"):
        self.adb = adb
        self.capture = capture
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self._screenshot = None
        self._display = None
        self._selecting = False
        self._start = (0, 0)
        self._end = (0, 0)
        self._selection = None
        self.window_name = "MSM Template Creator"

    def _refresh(self):
        print("Capturing screenshot...")
        img = self.capture.capture(use_cache=False)
        if img is None:
            print("ERROR: Could not capture screenshot")
            return False
        self._screenshot = img.copy()
        self._display = img.copy()
        self._selection = None
        return True

    def _draw_selection(self):
        if self._screenshot is None:
            return
        self._display = self._screenshot.copy()
        if self._selecting or self._selection:
            x1, y1 = self._start
            x2, y2 = self._end
            cv2.rectangle(self._display, (x1, y1), (x2, y2), (0, 255, 0), 2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            text = f"{w}x{h}"
            cv2.putText(self._display, text, (min(x1, x2), min(y1, y2) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self._selecting = True
            self._start = (x, y)
            self._end = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self._selecting:
            self._end = (x, y)
            self._draw_selection()
        elif event == cv2.EVENT_LBUTTONUP:
            self._selecting = False
            self._end = (x, y)
            x1, y1 = min(self._start[0], x), min(self._start[1], y)
            x2, y2 = max(self._start[0], x), max(self._start[1], y)
            if x2 - x1 > 5 and y2 - y1 > 5:
                self._selection = (x1, y1, x2, y2)
                self._start = (x1, y1)
                self._end = (x2, y2)
                self._draw_selection()
                print(f"Selected region: ({x1},{y1}) to ({x2},{y2}) = {x2-x1}x{y2-y1}")
        elif event == cv2.EVENT_RBUTTONDOWN:
            print(f"Tapping at ({x},{y})...")
            self.adb.tap(x, y)

    def _save_selection(self):
        if self._selection is None or self._screenshot is None:
            print("No region selected — click and drag to select")
            return
        x1, y1, x2, y2 = self._selection
        region = self._screenshot[y1:y2, x1:x2]

        name = input("Template name (no extension): ").strip()
        if not name:
            print("Cancelled")
            return

        path = self.output_dir / f"{name}.png"
        cv2.imwrite(str(path), region)
        print(f"Saved: {path} ({x2-x1}x{y2-y1})")

    def run(self):
        if not self.adb.connected:
            if not self.adb.auto_connect():
                print("Could not connect to BlueStacks via ADB")
                return

        if not self._refresh():
            print("Could not capture the emulator screen")
            return

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._on_mouse)

        print()
        print("=== Template Creator ===")
        print("  Left-click + drag = select region")
        print("  Right-click       = tap in game")
        print("  C = capture new screenshot")
        print("  S = save selected region as template")
        print("  F = save full screenshot")
        print("  Q / Esc = quit")
        print()

        while True:
            if self._display is not None:
                cv2.imshow(self.window_name, self._display)

            key = cv2.waitKey(50) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("c"):
                self._refresh()
            elif key == ord("s"):
                self._save_selection()
            elif key == ord("f"):
                if self._screenshot is not None:
                    path = self.output_dir / "full_screenshot.png"
                    cv2.imwrite(str(path), self._screenshot)
                    print(f"Full screenshot saved: {path}")

        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Capture template images from BlueStacks")
    ap.add_argument("--port", type=int, default=5555, help="ADB port (default 5555)")
    ap.add_argument("--output", default="templates", help="Output directory")
    args = ap.parse_args()

    adb = ADBController(serial=f"127.0.0.1:{args.port}")
    capture = ScreenCapture(adb)
    creator = TemplateCreator(adb, capture, args.output)
    creator.run()


if __name__ == "__main__":
    main()

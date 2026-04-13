"""
OpenCV template matching engine with caching, confidence thresholds,
and a wait-for-match polling helper.
"""

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Tuple

log = logging.getLogger("msm-pq-farmer")

# Lazy-loaded to avoid 15-20s startup delay
cv2 = None
np = None


def _ensure_cv2():
    global cv2, np
    if cv2 is None:
        import cv2 as _cv2
        import numpy as _np
        cv2 = _cv2
        np = _np

TEMPLATES_DIR = Path("templates")


@dataclass
class MatchResult:
    """Result of a template match."""
    x: int
    y: int
    w: int
    h: int
    confidence: float
    name: str = ""

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


class TemplateMatcher:
    """OpenCV-based template matching with caching."""

    def __init__(self, templates_dir: str = "templates", confidence: float = 0.85):
        self.templates_dir = Path(templates_dir)
        self.default_confidence = confidence
        self._cache_color: Dict[str, object] = {}
        self._cache_gray: Dict[str, object] = {}

    # ── template loading ───────────────────────────────────────────────

    def load_template(self, name: str):
        """Load a template image by name, returning BGR array. Cached."""
        _ensure_cv2()
        if name in self._cache_color:
            return self._cache_color[name]

        path = self.templates_dir / f"{name}.png"
        if not path.exists():
            path = self.templates_dir / name
        if not path.exists():
            return None

        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            log.warning("Failed to load template: %s", path)
            return None

        self._cache_color[name] = img
        self._cache_gray[name] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def load_template_gray(self, name: str):
        if name not in self._cache_gray:
            self.load_template(name)
        return self._cache_gray.get(name)

    def preload(self, names: List[str]):
        """Preload a batch of templates into cache."""
        for n in names:
            self.load_template(n)

    def list_templates(self) -> List[str]:
        """Return names of all available template files."""
        if not self.templates_dir.exists():
            return []
        return [p.stem for p in self.templates_dir.glob("*.png")]

    # ── matching ───────────────────────────────────────────────────────

    def find(
        self,
        screen,
        template_name: str,
        confidence: Optional[float] = None,
        grayscale: bool = True,
    ) -> Optional[MatchResult]:
        """Find best match of a template in the screen image."""
        conf = confidence or self.default_confidence
        tmpl = self.load_template_gray(template_name) if grayscale else self.load_template(template_name)
        if tmpl is None:
            return None

        if grayscale:
            if len(screen.shape) == 3:
                haystack = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            else:
                haystack = screen
        else:
            haystack = screen

        if haystack.shape[0] < tmpl.shape[0] or haystack.shape[1] < tmpl.shape[1]:
            return None

        result = cv2.matchTemplate(haystack, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= conf:
            h, w = tmpl.shape[:2]
            return MatchResult(
                x=max_loc[0], y=max_loc[1],
                w=w, h=h,
                confidence=max_val,
                name=template_name,
            )
        return None

    def find_all(
        self,
        screen,
        template_name: str,
        confidence: Optional[float] = None,
        min_distance: int = 20,
        grayscale: bool = True,
    ) -> List[MatchResult]:
        """Find all occurrences of a template (filtering duplicates)."""
        conf = confidence or self.default_confidence
        tmpl = self.load_template_gray(template_name) if grayscale else self.load_template(template_name)
        if tmpl is None:
            return []

        if grayscale:
            haystack = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if len(screen.shape) == 3 else screen
        else:
            haystack = screen

        if haystack.shape[0] < tmpl.shape[0] or haystack.shape[1] < tmpl.shape[1]:
            return []

        result = cv2.matchTemplate(haystack, tmpl, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= conf)
        h, w = tmpl.shape[:2]

        matches: List[MatchResult] = []
        for pt in zip(*locations[::-1]):
            too_close = False
            for m in matches:
                if abs(m.x - pt[0]) < min_distance and abs(m.y - pt[1]) < min_distance:
                    too_close = True
                    break
            if not too_close:
                matches.append(MatchResult(
                    x=pt[0], y=pt[1], w=w, h=h,
                    confidence=float(result[pt[1], pt[0]]),
                    name=template_name,
                ))
        return matches

    def find_any(
        self,
        screen,
        template_names: List[str],
        confidence: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """Return the first matching template from the list."""
        for name in template_names:
            m = self.find(screen, name, confidence)
            if m is not None:
                return m
        return None

    def find_best(
        self,
        screen,
        template_names: List[str],
        confidence: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """Return the best (highest confidence) match from the list."""
        best: Optional[MatchResult] = None
        for name in template_names:
            m = self.find(screen, name, confidence)
            if m is not None and (best is None or m.confidence > best.confidence):
                best = m
        return best

    def wait_for(
        self,
        capture_fn,
        template_name: str,
        timeout: float = 30,
        interval: float = 0.5,
        confidence: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """Poll until template appears or timeout."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            screen = capture_fn()
            if screen is not None:
                m = self.find(screen, template_name, confidence)
                if m is not None:
                    return m
            time.sleep(interval)
        return None

    # ── pixel color matching (legacy fallback) ─────────────────────────

    @staticmethod
    def color_match(pixel: Tuple[int, int, int], target: list, tolerance: int) -> bool:
        return all(abs(int(a) - int(b)) <= tolerance for a, b in zip(pixel[:3], target))

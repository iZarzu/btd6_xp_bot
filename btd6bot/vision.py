"""Finding small template images (e.g. the "Victory" text) in game frames.

PL: Wyszukiwanie małych obrazków-szablonów (np. napisu „Victory”) w klatkach gry.

Resolution independence / Niezależność od rozdzielczości:
each template remembers the game width it was captured at (templates/templates.json).
On a different resolution the template is rescaled, so templates captured on a 1080p
screen also work on 4K and vice versa.
PL: każdy szablon pamięta szerokość gry, przy której go wycięto (templates/templates.json).
Przy innej rozdzielczości szablon jest skalowany, więc wycięty na 1080p działa też na 4K.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

META_FILE = "templates.json"
# Small extra scales cover windowed mode borders / rounding. / PL: Drobne odchyłki rozmiaru.
SCALE_STEPS = (1.0, 0.96, 1.04)


class TemplateLibrary:
    def __init__(self, directory: Path, threshold: float = 0.8, default_width: int = 1920):
        self.directory = directory
        self.threshold = threshold
        self.default_width = default_width
        self._images: dict[str, np.ndarray | None] = {}
        self._scaled: dict[tuple[str, int], list[np.ndarray]] = {}
        self._meta = self._load_meta()

    # ------------------------------------------------------------------ storage / zapis
    def _load_meta(self) -> dict:
        path = self.directory / META_FILE
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def names(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.png"))

    def exists(self, name: str) -> bool:
        return (self.directory / f"{name}.png").exists()

    def info(self, name: str) -> str:
        meta = self._meta.get(name)
        return f"{meta['width']}x{meta['height']}" if meta else ""

    def save(self, name: str, image_bgr: np.ndarray, game_width: int, game_height: int) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{name}.png"
        cv2.imwrite(str(path), image_bgr)
        self._meta[name] = {"width": game_width, "height": game_height}
        (self.directory / META_FILE).write_text(json.dumps(self._meta, indent=2, sort_keys=True), encoding="utf-8")
        self._images.pop(name, None)
        self._scaled = {k: v for k, v in self._scaled.items() if k[0] != name}
        return path

    def delete(self, name: str) -> None:
        (self.directory / f"{name}.png").unlink(missing_ok=True)
        self._meta.pop(name, None)
        (self.directory / META_FILE).write_text(json.dumps(self._meta, indent=2, sort_keys=True), encoding="utf-8")
        self._images.pop(name, None)
        self._scaled = {k: v for k, v in self._scaled.items() if k[0] != name}

    # ------------------------------------------------------------------ matching / dopasowanie
    def _image(self, name: str) -> np.ndarray | None:
        if name not in self._images:
            path = self.directory / f"{name}.png"
            self._images[name] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if path.exists() else None
        return self._images[name]

    def _variants(self, name: str, frame_width: int) -> list[np.ndarray]:
        key = (name, frame_width)
        if key not in self._scaled:
            image = self._image(name)
            variants = []
            if image is not None:
                source_width = self._meta.get(name, {}).get("width", self.default_width)
                base = frame_width / source_width
                for step in SCALE_STEPS:
                    scale = base * step
                    if abs(scale - 1.0) < 0.005:
                        variants.append(image)
                    else:
                        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                        variants.append(cv2.resize(image, None, fx=scale, fy=scale, interpolation=interp))
            self._scaled[key] = variants
        return self._scaled[key]

    def find(self, name: str, frame_gray: np.ndarray) -> tuple[float, float] | None:
        """Relative centre of the best match, or None. / PL: Względny środek dopasowania albo None."""
        best_score, best_pos = 0.0, None
        fh, fw = frame_gray.shape[:2]
        for template in self._variants(name, fw):
            th, tw = template.shape[:2]
            if th > fh or tw > fw or th < 4 or tw < 4:
                continue
            result = cv2.matchTemplate(frame_gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(result)
            if score > best_score:
                best_score, best_pos = score, ((loc[0] + tw / 2) / fw, (loc[1] + th / 2) / fh)
            if score >= 0.95:
                break  # good enough, skip other scales / PL: wystarczy, pomijamy inne skale
        return best_pos if best_score >= self.threshold else None


# Frames are matched at this width at most: 1080p is ~2x and 4K ~10x faster, with the same result
# (positions are relative and templates are rescaled to the frame anyway).
# PL: Klatki są dopasowywane najwyżej w tej szerokości: 1080p ~2x, a 4K ~10x szybciej, z tym samym
# wynikiem (pozycje są względne, a szablony i tak są skalowane do klatki).
WORK_WIDTH = 1280


def to_gray(frame_bgr: np.ndarray) -> np.ndarray:
    """Grayscale frame, downscaled to WORK_WIDTH for fast matching. / PL: Szara klatka zmniejszona do WORK_WIDTH."""
    gray = cv2.cvtColor(np.ascontiguousarray(frame_bgr), cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w > WORK_WIDTH:
        gray = cv2.resize(gray, (WORK_WIDTH, round(h * WORK_WIDTH / w)), interpolation=cv2.INTER_AREA)
    return gray

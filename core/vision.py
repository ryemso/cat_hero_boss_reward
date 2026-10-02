from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import math
import cv2
import numpy as np
from PIL import Image

@dataclass
class CardDetection:
    x: int
    y: int
    w: int
    h: int
    crop: np.ndarray
    rarity: str


def _dedupe_boxes(boxes, iou_thr=0.70):
    def iou(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0

    kept = []
    for b in sorted(boxes, key=lambda z: z[2] * z[3], reverse=True):
        if all(iou(b, k) < iou_thr for k in kept):
            kept.append(b)
    return sorted(kept, key=lambda z: (z[1], z[0]))


def detect_reward_cards(image_bgr: np.ndarray) -> list[CardDetection]:
    """정형화된 게임 보상 카드(정사각형)에 맞춘 contour 검출.
    443x960, 1080x1123 등 해상도 차이를 폭 비율로 흡수한다.
    """
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if not (0.065 * W <= w <= 0.155 * W):
            continue
        if not (0.065 * W <= h <= 0.165 * W):
            continue
        if not (0.80 <= (w / max(h, 1)) <= 1.20):
            continue
        if not (0.06 * W <= x <= 0.94 * W and 0.28 * H <= y <= 0.61 * H):
            continue
        area = cv2.contourArea(c)
        if area < 0.62 * w * h:
            continue
        candidates.append((x, y, w, h))

    boxes = _dedupe_boxes(candidates)
    if not boxes:
        return []

    # 카드가 여러 장이면 가장 흔한 크기대를 남겨 UI의 닫기 버튼 같은 오검출을 제거한다.
    sizes = np.array([b[2] for b in boxes], dtype=float)
    med = float(np.median(sizes))
    boxes = [b for b in boxes if 0.78 * med <= b[2] <= 1.22 * med and 0.78 * med <= b[3] <= 1.22 * med]

    out = []
    for x, y, w, h in boxes:
        crop = image_bgr[y:y+h, x:x+w].copy()
        out.append(CardDetection(x, y, w, h, crop, classify_rarity(crop)))
    return out


def classify_rarity(card_bgr: np.ndarray) -> str:
    hsv = cv2.cvtColor(card_bgr, cv2.COLOR_BGR2HSV)
    h, w = hsv.shape[:2]
    # 아이콘/숫자를 피하고 테두리 안쪽 배경에서 샘플링
    strips = np.concatenate([
        hsv[int(.12*h):int(.24*h), int(.08*w):int(.22*w)].reshape(-1, 3),
        hsv[int(.12*h):int(.24*h), int(.78*w):int(.92*w)].reshape(-1, 3),
    ], axis=0)
    strips = strips[(strips[:,1] > 35) & (strips[:,2] > 45)]
    if len(strips) == 0:
        return "GRAY"
    hue = float(np.median(strips[:,0]))
    sat = float(np.median(strips[:,1]))
    if sat < 70:
        return "GRAY"
    if hue < 8 or hue >= 170:
        return "RED"
    if 8 <= hue < 25:
        return "YELLOW"
    if 25 <= hue < 85:
        return "GREEN"
    if 85 <= hue < 125:
        return "BLUE"
    if 125 <= hue < 170:
        return "PURPLE"
    return "UNKNOWN"


def _icon_feature(card_bgr: np.ndarray) -> np.ndarray:
    h, w = card_bgr.shape[:2]
    # 숫자 영역을 제외한 중앙 아이콘 영역
    icon = card_bgr[int(.12*h):int(.72*h), int(.12*w):int(.88*w)]
    icon = cv2.resize(icon, (48, 48), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(icon, cv2.COLOR_BGR2LAB).astype(np.float32)
    # 밝기/색차를 함께 보되 크기 차이에 덜 민감하게 정규화
    vec = lab.reshape(-1)
    vec -= vec.mean()
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 1e-8 else vec


def compare_cards(card_a: np.ndarray, card_b: np.ndarray) -> float:
    a = _icon_feature(card_a)
    b = _icon_feature(card_b)
    n = min(len(a), len(b))
    corr = float(np.dot(a[:n], b[:n]))
    corr01 = max(0.0, min(1.0, (corr + 1.0) / 2.0))
    rarity_bonus = 1.0 if classify_rarity(card_a) == classify_rarity(card_b) else 0.0
    return 0.82 * corr01 + 0.18 * rarity_bonus


def load_template(path: str | Path):
    # imread fails on Korean Windows paths; Python reads bytes with Unicode support.
    try:
        return cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    except (OSError, ValueError, cv2.error):
        return None


def match_reward(card_bgr: np.ndarray, templates: list[dict], threshold: float = 0.78):
    best = None
    for t in templates:
        p = t.get("template_path")
        if not p or not Path(p).exists():
            continue
        templ = load_template(p)
        if templ is None:
            continue
        score = compare_cards(card_bgr, templ)
        if best is None or score > best["score"]:
            best = {**t, "score": score}
    if best is None:
        return None
    best["accepted"] = best["score"] >= threshold
    return best


_EASY_READER = None

def _easy_reader():
    global _EASY_READER
    if _EASY_READER is None:
        import easyocr
        _EASY_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _EASY_READER


def read_quantity(card_bgr: np.ndarray, default_one=True):
    """카드 하단 숫자만 OCR. 실패하면 default_one=True일 때 1을 반환."""
    h, w = card_bgr.shape[:2]
    roi = card_bgr[int(.60*h):int(.98*h), int(.05*w):int(.95*w)]
    roi = cv2.resize(roi, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # 흰 숫자 + 검은 외곽선 대응: 대비 강화 후 원본/이진화 둘 다 시도
    eq = cv2.equalizeHist(gray)
    _, bw = cv2.threshold(eq, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        reader = _easy_reader()
        results = []
        for img in (eq, bw):
            results.extend(reader.readtext(img, detail=1, allowlist="0123456789", paragraph=False))
        candidates = []
        for _, txt, conf in results:
            digits = "".join(ch for ch in txt if ch.isdigit())
            if digits:
                candidates.append((int(digits), float(conf)))
        if candidates:
            # 높은 신뢰도 우선, 동일 신뢰도면 더 긴 숫자 우선
            candidates.sort(key=lambda z: (z[1], len(str(z[0]))), reverse=True)
            return candidates[0][0], candidates[0][1]
    except Exception:
        pass
    return (1, 0.0) if default_one else (None, 0.0)


def pil_to_bgr(pil_image: Image.Image) -> np.ndarray:
    arr = np.array(pil_image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def bgr_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))

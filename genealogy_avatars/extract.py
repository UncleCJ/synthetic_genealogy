"""Turn real photos into vectors. Runs locally; nothing is uploaded.

Folder layout:  photos/<person_id>/<anything>.jpg   (one face per photo works best)

    pip install insightface onnxruntime mediapipe==0.10.14 opencv-python

insightface 'buffalo_l' gives a 512-d ArcFace identity embedding plus age and sex estimates.
mediapipe FaceMesh gives 478 landmarks; we turn a handful of them into the drawable TRAITS.
Results are cached in faces.npz, which is biometric data: keep it out of public git repos.

NOTE: written against these libraries' documented APIs but not run in the sandbox that made it.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .traits import TRAITS

# mediapipe FaceMesh landmark indices
FOREHEAD, CHIN, CHEEK_R, CHEEK_L = 10, 152, 234, 454
IRIS_R, IRIS_L = 468, 473
BROW_R, BROW_L, LID_R, LID_L = 105, 334, 159, 386
EYE_R_OUT, EYE_R_IN, EYE_L_IN, EYE_L_OUT = 33, 133, 362, 263
NASION, NOSE_TIP, MOUTH_R, MOUTH_L = 168, 1, 61, 291
CHEEK_PATCH = (50, 280)


def _measure(img_rgb: np.ndarray, pts: np.ndarray) -> dict[str, float]:
    dist = lambda a, b: float(np.linalg.norm(pts[a] - pts[b]))
    fh, fw = dist(FOREHEAD, CHIN), dist(CHEEK_R, CHEEK_L)
    gray_photo = np.allclose(img_rgb[..., 0], img_rgb[..., 1], atol=6)
    def lum(xy, r):
        x, y = map(int, xy)
        patch = img_rgb[max(y - r, 0):y + r, max(x - r, 0):x + r].reshape(-1, 3)
        return float(patch.mean()) if len(patch) else np.nan
    r = max(int(fw * 0.04), 2)
    hair_xy = pts[FOREHEAD] + (pts[FOREHEAD] - pts[CHIN]) * 0.33  # into the hair above the hairline (crude)
    return {
        "face_width": fw / fh,
        "face_length": fh / fw,
        "eye_spacing": dist(IRIS_R, IRIS_L) / fw,
        "eye_size": (dist(EYE_R_OUT, EYE_R_IN) + dist(EYE_L_IN, EYE_L_OUT)) / (2 * fw),
        "brow_height": (dist(BROW_R, LID_R) + dist(BROW_L, LID_L)) / (2 * fh),
        "nose_length": dist(NASION, NOSE_TIP) / fh,
        "mouth_width": dist(MOUTH_R, MOUTH_L) / fw,
        # colours are meaningless in black-and-white or sepia photos: leave them unmeasured
        "skin_tone": np.nan if gray_photo else -np.mean([lum(pts[i], r) for i in CHEEK_PATCH]),
        "hair_tone": np.nan if gray_photo else lum(hair_xy, r * 2),
    }


def extract_folder(root: str | Path = "photos", min_age: int = 16) -> dict[str, list[dict]]:
    import cv2
    import mediapipe as mp
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1)

    out: dict[str, list[dict]] = {}
    for person_dir in sorted(Path(root).iterdir()):
        if not person_dir.is_dir():
            continue
        for img_path in sorted(person_dir.glob("*")):
            bgr = cv2.imread(str(img_path))
            if bgr is None:
                continue
            faces = app.get(bgr)
            if not faces:
                continue
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            if face.age is not None and face.age < min_age:   # children's faces drift a lot
                continue
            x0, y0, x1, y1 = map(int, face.bbox)
            pad = int((x1 - x0) * 0.4)
            crop = cv2.cvtColor(bgr[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad], cv2.COLOR_BGR2RGB)
            res = mesh.process(crop)
            traits = {t: np.nan for t in TRAITS}
            if res.multi_face_landmarks:
                h, w = crop.shape[:2]
                pts = np.array([(lm.x * w, lm.y * h) for lm in res.multi_face_landmarks[0].landmark])
                traits = _measure(crop, pts)
            out.setdefault(person_dir.name, []).append({
                "file": img_path.name,
                "embedding": face.normed_embedding.astype(np.float32),
                "raw": np.array([traits[t] for t in TRAITS], dtype=float),
                "age": float(face.age), "sex": "M" if face.gender == 1 else "F",
            })
    return out


def standardise(records: dict[str, list[dict]]) -> dict[str, np.ndarray]:
    """Raw measurements -> z-scores across your whole photo collection."""
    allraw = np.vstack([r["raw"] for recs in records.values() for r in recs])
    m, s = np.nanmean(allraw, 0), np.nanstd(allraw, 0) + 1e-9
    return {pid: np.vstack([(r["raw"] - m) / s for r in recs]) for pid, recs in records.items()}

"""
1-BOSQICH: Barcha videolardan freym olib, yuzlarni topib, embedding (raqamli imzo) chiqarish.
Mahalliy papka yoki ZIP arxivini qo'llab-quvvatlaydi. Har bir video ichida yuzlarni kuzatib (tracking), 
faqat eng tiniq va sifatli yuz embeddingini saqlaydi.

Ishlatish:
    python loyha.py --videos_dir /path/to/videos --out faces_data.pkl
    yoki
    python loyha.py --zip_path /path/to/videos.zip --out faces_data.pkl
"""

import argparse
import os
import sys
import site
import pickle
import uuid
import zipfile
import tempfile
import shutil
import warnings
from pathlib import Path

# Windows'da pip orqali o'rnatilgan cuDNN/CUDA DLL fayllarini yuklash (Python 3.8+ uchun)
if sys.platform == "win32":
    paths_to_check = site.getsitepackages() if hasattr(site, 'getsitepackages') else []
    for p in sys.path:
        if 'site-packages' in p and p not in paths_to_check:
            paths_to_check.append(p)
    extra_paths = []
    for path in paths_to_check:
        nvidia_dir = os.path.join(path, "nvidia")
        if os.path.exists(nvidia_dir):
            for sub in os.listdir(nvidia_dir):
                bin_path = os.path.join(nvidia_dir, sub, "bin")
                if os.path.exists(bin_path):
                    extra_paths.append(bin_path)
                    try:
                        os.add_dll_directory(bin_path)
                    except Exception:
                        pass
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if "NVIDIA GPU Computing Toolkit" in p and os.path.exists(p):
            extra_paths.append(p)
            try:
                os.add_dll_directory(p)
            except Exception:
                pass
    # Tizim PATHi yangilanmagan bo'lsa, to'g'ridan-to'g'ri standart CUDA yo'lini tekshiramiz
    cuda_base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.exists(cuda_base):
        for sub in os.listdir(cuda_base):
            bin_path = os.path.join(cuda_base, sub, "bin")
            if os.path.exists(bin_path):
                extra_paths.append(bin_path)
                try:
                    os.add_dll_directory(bin_path)
                except Exception:
                    pass
    if extra_paths:
        os.environ["PATH"] = ";".join(extra_paths) + ";" + os.environ.get("PATH", "")

import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis
from tqdm import tqdm

# Scikit-image/InsightFace warninglarni yashirish (tqdm progress-barni chiroyli ko'rsatish uchun)
warnings.filterwarnings("ignore", category=FutureWarning)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv"}


def find_videos(root):
    root = Path(root)
    return [p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXTS]


def main():
    # CUDA mavjudligini tekshirish
    cuda_available = "CUDAExecutionProvider" in ort.get_available_providers()
    default_device = "gpu" if cuda_available else "cpu"

    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--videos_dir", help="Mahalliy videolar joylashgan papka")
    group.add_argument("--zip_path", help="Videolar joylashgan ZIP fayl yo'li")
    
    ap.add_argument("--out", default="faces_data.pkl", help="Chiqish fayli (pickle)")
    ap.add_argument("--every_sec", type=float, default=2.0, help="Necha soniyada bitta freym olish (tahlil boshlanishi)")
    ap.add_argument("--min_face_size", type=int, default=40, help="Minimal yuz o'lchami (piksellarda)")
    ap.add_argument("--det_score_thresh", type=float, default=0.55, help="Yuz aniqlash chegarasi")
    ap.add_argument("--save_thumbs", action="store_true", help="Har bir insonning eng tiniq yuz rasmini saqlash")
    ap.add_argument("--thumbs_dir", default="face_thumbs", help="Thumbnail rasmlar papkasi")
    ap.add_argument("--device", choices=["cpu", "gpu"], default=default_device, help="Hisoblash qurilmasi (cpu yoki gpu)")
    ap.add_argument("--track_thresh", type=float, default=0.60, help="Video ichida yuzlarni bir-biriga moslashtirish chegarasi (cosine similarity)")
    ap.add_argument("--no_dense", action="store_true", help="Yuz topilganda zich tahlil qilishni o'chirish (tezlikni oshirish uchun)")
    ap.add_argument("--max_size_mb", type=float, default=None, help="Maksimal video hajmi (MB). Bundan katta videolar o'tkazib yuboriladi.")
    args = ap.parse_args()

    if args.save_thumbs:
        os.makedirs(args.thumbs_dir, exist_ok=True)

    print(f"Tanlangan qurilma: {args.device.upper()}")
    if args.device == "gpu":
        print("InsightFace modelini GPU (CUDA) rejimida yuklamoqda...")
        app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
    else:
        print("InsightFace modelini CPU rejimida yuklamoqda...")
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))

    # Video ro'yxatini shakllantirish
    videos_to_process = []  # list of tuples: (display_path, temp_or_local_path, zip_inner_path, size_mb)
    
    if args.zip_path:
        zip_abs_path = os.path.abspath(args.zip_path)
        if not os.path.exists(zip_abs_path):
            print(f"XATO: ZIP fayl topilmadi -> {zip_abs_path}")
            return
        print(f"ZIP fayl o'qilmoqda: {zip_abs_path}")
        with zipfile.ZipFile(zip_abs_path, "r") as z:
            for info in z.infolist():
                name = info.filename
                if Path(name).suffix.lower() in VIDEO_EXTS:
                    size_mb = info.file_size / (1024 * 1024)
                    videos_to_process.append((zip_abs_path, name, name, size_mb))
        print(f"ZIP ichida {len(videos_to_process)} ta video topildi.")
    else:
        local_dir = os.path.abspath(args.videos_dir)
        if not os.path.exists(local_dir):
            print(f"XATO: Papka topilmadi -> {local_dir}")
            return
        local_videos = find_videos(local_dir)
        for v in local_videos:
            size_mb = os.path.getsize(v) / (1024 * 1024)
            videos_to_process.append((str(v), str(v), None, size_mb))
        print(f"Papka ichida {len(videos_to_process)} ta video topildi.")

    records = []
    processed_videos = set()
    if os.path.exists(args.out):
        try:
            with open(args.out, "rb") as fh:
                records = pickle.load(fh)
                if isinstance(records, list):
                    for r in records:
                        if isinstance(r, dict) and "video_path" in r:
                            processed_videos.add((r["video_path"], r.get("zip_inner_path")))
            print(f"Topildi: Oldingi tahlil faylida ({args.out}) {len(processed_videos)} ta video mavjud. Davom ettirilmoqda...")
        except Exception as e:
            print(f"Oldingi natija faylini yuklashda xatolik: {e}. Tahlil yangidan boshlanadi.")
            records = []
            processed_videos = set()

    # ZIP fayli uchun zipfile obyektini tayyorlash
    z_file = zipfile.ZipFile(args.zip_path, "r") if args.zip_path else None

    try:
        for idx_video, video_info in enumerate(tqdm(videos_to_process, desc="Videolar tahlili")):
            display_path, source_path, zip_inner_path, size_mb = video_info
            
            # Agar video oldingi seansda tahlil qilingan bo'lsa, sakrab o'tamiz
            if (display_path, zip_inner_path) in processed_videos:
                continue
            
            # Agar o'lcham cheklovi bo'lsa va video katta bo'lsa, tahlil qilmasdan o'tkazib yuboramiz
            if args.max_size_mb is not None and size_mb > args.max_size_mb:
                records.append({
                    "video_path": display_path,
                    "zip_inner_path": zip_inner_path,
                    "frame_time_sec": -1.0,
                    "bbox": [],
                    "embedding": None,
                    "det_score": 0.0,
                    "thumb_path": "",
                    "has_face": False,
                    "track_len": 0,
                    "skipped_oversized": True
                })
                continue

            # Agar ZIP bo'lsa, vaqtinchalik papkaga chiqarib olamiz
            if zip_inner_path is not None and z_file is not None:
                temp_dir = tempfile.mkdtemp()
                video_file_path = z_file.extract(zip_inner_path, temp_dir)
            else:
                temp_dir = None
                video_file_path = source_path

            # Videoni o'qish
            cap = cv2.VideoCapture(video_file_path)
            if not cap.isOpened():
                print(f"\nOGOHLANTIRISH: Video ochilmadi -> {display_path}")
                # Hatto ochilmagan videoni ham no_face yoki xatolik sifatida qayd etamiz
                records.append({
                    "video_path": display_path,
                    "zip_inner_path": zip_inner_path,
                    "frame_time_sec": -1.0,
                    "bbox": [],
                    "embedding": None,
                    "det_score": 0.0,
                    "thumb_path": "",
                    "has_face": False,
                    "track_len": 0
                })
                if temp_dir:
                    shutil.rmtree(temp_dir)
                continue

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            
            # Agar freymlar soni aniqlanmasa, ketma-ket o'qiladi
            if total_frames <= 0:
                total_frames = 1000000  # Chegarasiz katta son

            # Smart Adaptive Sampling parametrlar
            normal_step = max(1, int(round(fps * args.every_sec)))
            dense_step = normal_step if args.no_dense else max(1, int(round(fps * 0.2)))  # Yuz topilsa, har 0.2 soniyada tekshiradi
            
            idx_frame = 0
            dense_until = -1
            
            # Intra-video face tracks
            # Har bir track: { "embeddings": [list], "best_quality": float, "best_face": dict, "best_crop": np.ndarray }
            tracks = []

            while idx_frame < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx_frame)
                ok, frame = cap.read()
                if not ok:
                    break

                faces = app.get(frame)
                valid_faces_in_frame = False

                for face in faces:
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    w, h = x2 - x1, y2 - y1
                    if w < args.min_face_size or h < args.min_face_size:
                        continue
                    if face.det_score < args.det_score_thresh:
                        continue
                    
                    valid_faces_in_frame = True
                    f_emb = face.normed_embedding.astype(np.float32)
                    
                    # Tracklar orasidan eng mosini qidirish
                    best_match_idx = -1
                    max_sim = -1.0
                    for t_idx, track in enumerate(tracks):
                        # Trackning eng yaxshi yuzi bilan cosine similarity
                        sim = np.dot(f_emb, track["best_face"]["embedding"])
                        if sim > max_sim:
                            max_sim = sim
                            best_match_idx = t_idx
                    
                    # Sifat koeffitsiyenti (yuz o'lchami va ishonchliligi)
                    quality = float(face.det_score) * (w * h)
                    crop_y1, crop_y2 = max(0, y1), min(frame.shape[0], y2)
                    crop_x1, crop_x2 = max(0, x1), min(frame.shape[1], x2)
                    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()

                    if max_sim >= args.track_thresh and best_match_idx != -1:
                        # Mos keldi, trackni yangilaymiz
                        tracks[best_match_idx]["embeddings"].append(f_emb)
                        if quality > tracks[best_match_idx]["best_quality"] and crop.size > 0:
                            tracks[best_match_idx]["best_quality"] = quality
                            tracks[best_match_idx]["best_face"] = {
                                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                                "det_score": float(face.det_score),
                                "frame_time_sec": idx_frame / fps,
                                "embedding": f_emb
                            }
                            tracks[best_match_idx]["best_crop"] = crop
                    else:
                        # Yangi inson/track boshlash
                        if crop.size > 0:
                            tracks.append({
                                "embeddings": [f_emb],
                                "best_quality": quality,
                                "best_face": {
                                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                                    "det_score": float(face.det_score),
                                    "frame_time_sec": idx_frame / fps,
                                    "embedding": f_emb
                                },
                                "best_crop": crop
                            })

                if valid_faces_in_frame:
                    # Kelgusi 2 soniya davomida zich (dense) tekshirish yoqiladi
                    dense_until = idx_frame + int(fps * 2.0)

                # Qadamni tanlash
                if idx_frame < dense_until:
                    idx_frame += dense_step
                else:
                    idx_frame += normal_step

            cap.release()

            # Natijalarni yozish
            if not tracks:
                # Videoda umuman yuz topilmadi
                records.append({
                    "video_path": display_path,
                    "zip_inner_path": zip_inner_path,
                    "frame_time_sec": -1.0,
                    "bbox": [],
                    "embedding": None,
                    "det_score": 0.0,
                    "thumb_path": "",
                    "has_face": False,
                    "track_len": 0
                })
            else:
                for track in tracks:
                    thumb_path = ""
                    if args.save_thumbs and "best_crop" in track and track["best_crop"] is not None:
                        thumb_id = uuid.uuid4().hex[:12]
                        thumb_path = os.path.join(args.thumbs_dir, f"{thumb_id}.jpg")
                        cv2.imwrite(thumb_path, track["best_crop"])
                    
                    records.append({
                        "video_path": display_path,
                        "zip_inner_path": zip_inner_path,
                        "frame_time_sec": track["best_face"]["frame_time_sec"],
                        "bbox": track["best_face"]["bbox"],
                        "embedding": track["best_face"]["embedding"],
                        "det_score": track["best_face"]["det_score"],
                        "thumb_path": thumb_path,
                        "has_face": True,
                        "track_len": len(track["embeddings"])
                    })

            # Vaqtinchalik fayllarni o'chirish
            if temp_dir:
                shutil.rmtree(temp_dir)

    except KeyboardInterrupt:
        print("\n\nOGOHLANTIRISH: Jarayon foydalanuvchi tomonidan to'xtatildi! Hozirgacha tahlil qilingan natijalar saqlanadi.")
    finally:
        if z_file:
            z_file.close()

    print(f"Jami tahlil qilingan video va yuzlar yozuvi: {len(records)}")
    with open(args.out, "wb") as fh:
        pickle.dump(records, fh)
    print(f"Ma'lumotlar saqlandi -> {args.out}")


if __name__ == "__main__":
    main()
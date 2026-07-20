import os
import zipfile
import tempfile
import pickle
import uuid
import shutil
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
from sklearn.cluster import AgglomerativeClustering
from insightface.app import FaceAnalysis

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv"}

class FacePipeline:
    def __init__(self, use_gpu=False):
        print("InsightFace modeli yuklanmoqda...")
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
        self.app = FaceAnalysis(name="buffalo_l", providers=providers)
        self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=(640, 640))
        print("Model tayyor!")

    def analyze_zip(self, zip_path, work_dir, every_sec=5.0, progress_callback=None):
        """1-BOSQICH: ZIP ichidagi videolarni tahlil qilish va yuz rasmlarini saqlash"""
        thumbs_dir = os.path.join(work_dir, "face_thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)
        
        videos_to_process = []
        with zipfile.ZipFile(zip_path, "r") as z:
            for info in z.infolist():
                if Path(info.filename).suffix.lower() in VIDEO_EXTS:
                    videos_to_process.append(info.filename)
        
        total_videos = len(videos_to_process)
        records = []

        with zipfile.ZipFile(zip_path, "r") as z:
            for idx, zip_inner_path in enumerate(videos_to_process):
                if progress_callback:
                    progress_callback(idx + 1, total_videos, zip_inner_path)
                
                temp_dir = tempfile.mkdtemp()
                try:
                    video_file_path = z.extract(zip_inner_path, temp_dir)
                    cap = cv2.VideoCapture(video_file_path)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    frame_step = int(fps * every_sec)
                    if frame_step < 1:
                        frame_step = 1

                    frame_idx = 0
                    tracks = []

                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        if frame_idx % frame_step == 0:
                            frame_time_sec = frame_idx / fps
                            faces = self.app.get(frame)
                            for face in faces:
                                bbox = face.bbox.astype(int).tolist()
                                emb = face.normed_embedding.astype(np.float32)
                                det_score = float(face.det_score)

                                # Face crop
                                h, w, _ = frame.shape
                                x1, y1, x2, y2 = bbox
                                x1, y1 = max(0, x1), max(0, y1)
                                x2, y2 = min(w, x2), min(h, y2)
                                crop = frame[y1:y2, x1:x2] if (x2 > x1 and y2 > y1) else None

                                # Tracking similarity check
                                matched = False
                                for tr in tracks:
                                    sim = np.dot(emb, tr["best_face"]["embedding"])
                                    if sim > 0.60:
                                        tr["embeddings"].append(emb)
                                        if det_score > tr["best_face"]["det_score"]:
                                            tr["best_face"] = {
                                                "frame_time_sec": frame_time_sec,
                                                "bbox": bbox,
                                                "embedding": emb,
                                                "det_score": det_score,
                                            }
                                            if crop is not None:
                                                tr["best_crop"] = crop
                                        matched = True
                                        break
                                if not matched:
                                    tracks.append({
                                        "best_face": {
                                            "frame_time_sec": frame_time_sec,
                                            "bbox": bbox,
                                            "embedding": emb,
                                            "det_score": det_score,
                                        },
                                        "best_crop": crop,
                                        "embeddings": [emb],
                                    })
                        frame_idx += 1
                    cap.release()

                    if not tracks:
                        records.append({
                            "video_path": zip_path,
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
                        for tr in tracks:
                            thumb_path = ""
                            if tr["best_crop"] is not None:
                                thumb_id = uuid.uuid4().hex[:12]
                                thumb_path = os.path.join(thumbs_dir, f"{thumb_id}.jpg")
                                cv2.imwrite(thumb_path, tr["best_crop"])
                            records.append({
                                "video_path": zip_path,
                                "zip_inner_path": zip_inner_path,
                                "frame_time_sec": tr["best_face"]["frame_time_sec"],
                                "bbox": tr["best_face"]["bbox"],
                                "embedding": tr["best_face"]["embedding"],
                                "det_score": tr["best_face"]["det_score"],
                                "thumb_path": thumb_path,
                                "has_face": True,
                                "track_len": len(tr["embeddings"])
                            })
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)

        data_pkl_path = os.path.join(work_dir, "faces_data.pkl")
        with open(data_pkl_path, "wb") as f:
            pickle.dump(records, f)
        return data_pkl_path

    @staticmethod
    def cluster_faces(data_pkl_path, work_dir, threshold=0.50, min_cluster_size=1):
        """2-BOSQICH: Yuzlarni klasterlash va preview rasmlarini tayyorlash"""
        with open(data_pkl_path, "rb") as f:
            records = pickle.load(f)

        valid_records = [r for r in records if r.get("has_face", False) and r.get("embedding") is not None]
        preview_dir = os.path.join(work_dir, "clusters_preview")
        os.makedirs(preview_dir, exist_ok=True)

        if len(valid_records) >= 2:
            X = np.stack([r["embedding"] for r in valid_records])
            clusterer = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=threshold,
                metric="cosine",
                linkage="average",
            )
            labels = clusterer.fit_predict(X)
        elif len(valid_records) == 1:
            labels = np.array([0])
        else:
            return {}, []

        counts = defaultdict(int)
        for lab in labels:
            counts[lab] += 1

        valid_labels = sorted([l for l, c in counts.items() if c >= min_cluster_size])
        remap = {old: new for new, old in enumerate(valid_labels)}

        for r, lab in zip(valid_records, labels):
            r["person_id"] = remap.get(lab, -1)

        by_person = defaultdict(list)
        for r in valid_records:
            pid = r.get("person_id", -1)
            if pid >= 0 and r.get("thumb_path") and os.path.exists(r["thumb_path"]):
                by_person[pid].append(r)

        person_summary = {}
        for pid, recs in by_person.items():
            pdir = os.path.join(preview_dir, f"person_{pid:03d}")
            os.makedirs(pdir, exist_ok=True)
            first_thumb = recs[0]["thumb_path"]
            preview_thumb = os.path.join(pdir, "preview.jpg")
            shutil.copy(first_thumb, preview_thumb)
            
            unique_vids = set(r["zip_inner_path"] for r in recs)
            person_summary[pid] = {
                "count": len(recs),
                "videos_count": len(unique_vids),
                "preview_path": preview_thumb,
                "videos": list(unique_vids)
            }

        clustered_pkl_path = os.path.join(work_dir, "faces_clustered.pkl")
        with open(clustered_pkl_path, "wb") as f:
            pickle.dump(records, f)

        return person_summary, records

    @staticmethod
    def extract_person_videos(zip_path, clustered_pkl_path, target_person_ids, output_zip_path):
        """3-BOSQICH: Tanlangan insonlar ishtirok etgan videolarni yangi ZIP qilib paketlash"""
        with open(clustered_pkl_path, "rb") as f:
            records = pickle.load(f)

        target_set = set(target_person_ids)
        matching_videos = set()
        for r in records:
            if r.get("person_id") in target_set:
                matching_videos.add(r["zip_inner_path"])

        with zipfile.ZipFile(zip_path, "r") as src_zip:
            with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as out_zip:
                for v_path in matching_videos:
                    try:
                        data = src_zip.read(v_path)
                        out_zip.writestr(os.path.basename(v_path), data)
                    except Exception as e:
                        print(f"Fayl nusxalashda xatolik {v_path}: {e}")
        
        return output_zip_path

"""
2-BOSQICH: Yig'ilgan yuz embeddinglarni klasterlab, bir xil insonlarni avtomatik guruhlash.

Ishlatish:
    python 2_cluster_faces.py --data faces_data.pkl --out faces_clustered.pkl --threshold 0.45

--threshold qiymati muhim:
    - Kichikroq (masalan 0.35) -> qattiqroq, bitta insonni 2 klasterga bo'lib yuborishi mumkin
    - Kattaroq (masalan 0.55) -> yumshoqroq, 2 xil insonni bitta klasterga qo'shib yuborishi mumkin
    Standart 0.45 dan boshlang, natijani preview papkasidan ko'rib, kerak bo'lsa qayta ishga tushiring.

Natija:
    - faces_clustered.pkl: har bir yozuvga "person_id" qo'shiladi (-1 = klasterlanmadi, kam uchragan/noaniq yuz)
    - clusters_preview/person_XX/ papkalarida har klasterdan bir nechta namuna rasm (agar 1-bosqichda --save_thumbs ishlatilgan bo'lsa)
"""

import argparse
import os
import pickle
import shutil
from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="faces_clustered.pkl")
    ap.add_argument("--threshold", type=float, default=0.45, help="Cosine distance chegarasi")
    ap.add_argument("--min_cluster_size", type=int, default=5, help="Shundan kam uchragan klaster shovqin deb hisoblanadi")
    ap.add_argument("--preview_dir", default="clusters_preview")
    ap.add_argument("--preview_per_cluster", type=int, default=12)
    args = ap.parse_args()

    with open(args.data, "rb") as fh:
        records = pickle.load(fh)

    if not records:
        print("Yozuvlar topilmadi, avval 1-bosqichni ishga tushiring.")
        return

    # Faqat yuz aniqlangan va embeddingga ega yozuvlarni ajratamiz
    valid_records = [r for r in records if r.get("has_face", True) and r.get("embedding") is not None]

    if not valid_records:
        print("Yuzlar topilmadi, klasterlash uchun ma'lumot yetarli emas.")
        for r in records:
            r["person_id"] = -2  # -2: yuz aniqlanmadi
        n_people = 0
        final_labels_count_noise = 0
    else:
        X = np.stack([r["embedding"] for r in valid_records])
        print(f"Klasterlash boshlandi: {len(X)} ta yuz...")

        if len(X) >= 2:
            clusterer = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=args.threshold,
                metric="cosine",
                linkage="average",
            )
            labels = clusterer.fit_predict(X)
        else:
            labels = np.array([0])

        # Kichik klasterlarni shovqin (-1) deb belgilash
        counts = defaultdict(int)
        for lab in labels:
            counts[lab] += 1

        valid_labels = sorted([l for l, c in counts.items() if c >= args.min_cluster_size])
        remap = {old: new for new, old in enumerate(valid_labels)}

        final_labels = []
        for lab in labels:
            if counts[lab] < args.min_cluster_size:
                final_labels.append(-1)
            else:
                final_labels.append(remap[lab])

        # Natijalarni valid yozuvlarga yozamiz
        for r, lab in zip(valid_records, final_labels):
            r["person_id"] = int(lab)

        # Qolgan (yuzi yo'q) videolarga person_id = -2 (no face) beramiz
        for r in records:
            if not r.get("has_face", True) or r.get("embedding") is None:
                r["person_id"] = -2

        n_people = len(valid_labels)
        final_labels_count_noise = final_labels.count(-1)

    print(f"Natija: {n_people} ta inson (klaster) topildi, shovqin (-1) sifatida {final_labels_count_noise} ta yuz belgilandi")

    with open(args.out, "wb") as fh:
        pickle.dump(records, fh)
    print(f"Saqlandi -> {args.out}")

    # Preview yaratish (agar thumbnail mavjud bo'lsa)
    has_thumbs = any(r.get("thumb_path") for r in records)
    if has_thumbs:
        if os.path.exists(args.preview_dir):
            shutil.rmtree(args.preview_dir)
        by_person = defaultdict(list)
        for r in records:
            if r.get("person_id", -1) >= 0 and r.get("thumb_path"):
                by_person[r["person_id"]].append(r["thumb_path"])

        for pid, thumbs in by_person.items():
            pdir = os.path.join(args.preview_dir, f"person_{pid:03d}")
            os.makedirs(pdir, exist_ok=True)
            step = max(1, len(thumbs) // args.preview_per_cluster)
            for i, t in enumerate(thumbs[::step][: args.preview_per_cluster]):
                if os.path.exists(t):
                    shutil.copy(t, os.path.join(pdir, os.path.basename(t)))

        print(f"Har klasterdan namuna rasmlar -> {args.preview_dir}/ (tekshirib chiqing!)")
    else:
        print("Eslatma: 1-bosqichda --save_thumbs ishlatilmagan, shuning uchun vizual preview yo'q.")


if __name__ == "__main__":
    main()
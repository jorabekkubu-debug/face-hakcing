"""
3-BOSQICH: Har bir videoni, unda qatnashgan insonlarga qarab, tegishli papkaga ko'chirish yoki nusxalash.
Mahalliy papka yoki ZIP arxivini qo'llab-quvvatlaydi.

Ishlatish (avval --dry_run bilan tekshiring, xato bo'lmasin):
    python loyha3.py --data faces_clustered.pkl --out_dir /path/to/organized --dry_run
    python loyha3.py --data faces_clustered.pkl --out_dir /path/to/organized

Papka tuzilishi:
    out_dir/
        person_000/          <- faqat shu 1 kishi qatnashgan videolar (kamida --min_frames_for_person marta ko'ringan)
        person_001/
        ...
        multiple_people/     <- 2 yoki undan ko'p kishi qatnashgan videolar
        unknown_person/      <- yuz topilgan, lekin klasterga tushmagan yoki kam ko'ringanlar
        no_face/             <- umuman yuz topilmagan yoki ochilmagan videolar
    out_dir/report.csv        <- barcha videolar haqida to'liq hisobot jadvali
"""

import argparse
import csv
import os
import shutil
import zipfile
import pickle
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="faces_clustered.pkl", help="2-bosqichdagi faces_clustered.pkl")
    ap.add_argument("--out_dir", default=None, help="Tartiblangan videolar joylashadigan papka (dry-run bo'lsa shart emas)")
    ap.add_argument("--min_frames_for_person", type=int, default=2,
                     help="Video shu insonga tegishli deb hisoblanishi uchun, kamida shuncha freymda ko'rinishi kerak")
    ap.add_argument("--move", action="store_true", help="Nusxalash (copy) o'rniga original fayllarni ko'chirish (move)")
    ap.add_argument("--dry_run", action="store_true", help="Hech narsa nusxalamaydi/ko'chirmaydi, faqat report.csv chiqaradi")
    ap.add_argument("--person_ids", type=str, default=None, help="Faqat tanlangan inson ID lari bo'yicha videolarni ajratish (masalan: 238,168,637)")
    args = ap.parse_args()

    if not args.dry_run and not args.out_dir:
        ap.error("--out_dir is required unless --dry_run is specified.")

    selected_pids = None
    if args.person_ids:
        selected_pids = set(int(x.strip()) for x in args.person_ids.split(","))

    with open(args.data, "rb") as fh:
        records = pickle.load(fh)

    # (video_path, zip_inner_path) -> { "tracks": [list], "has_face": bool, "skipped_oversized": bool }
    video_info = defaultdict(lambda: {"tracks": [], "has_face": False, "skipped_oversized": False})
    
    for r in records:
        vpath = r["video_path"]
        zip_inner = r.get("zip_inner_path")
        key = (vpath, zip_inner)
        
        # Video ma'lumotlarini kafolatli yaratamiz (hatto yuzi yo'q bo'lsa ham)
        _ = video_info[key]
        
        if r.get("skipped_oversized", False):
            video_info[key]["skipped_oversized"] = True
        
        if r.get("has_face", False) and r.get("embedding") is not None:
            video_info[key]["has_face"] = True
            video_info[key]["tracks"].append({
                "person_id": r.get("person_id", -1),
                "track_len": r.get("track_len", 1)
            })

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
    report_rows = []

    # Har bir video uchun qualifying insonlarni saqlash
    # (video_path, zip_inner_path) -> list of qualifying person_ids
    video_qualifying_persons = defaultdict(list)

    # Har bir videoni toifalash va nusxalash/ko'chirish
    for key in sorted(video_info.keys()):
        vpath, zip_inner_path = key
        info = video_info[key]
        has_face = info["has_face"]
        tracks = info["tracks"]

        if info.get("skipped_oversized", False):
            category = "skipped_oversized"
            dest_dir = os.path.join(args.out_dir, "skipped_oversized") if args.out_dir else ""
            qualifying = []
        elif not has_face:
            category = "no_face"
            dest_dir = os.path.join(args.out_dir, "no_face") if args.out_dir else ""
            qualifying = []
        else:
            # Min_frames_for_person shartini qanoatlantiruvchi va klasterlangan insonlar
            qualifying = sorted(list(set(
                t["person_id"] for t in tracks 
                if t["person_id"] >= 0 and t["track_len"] >= args.min_frames_for_person
            )))
            video_qualifying_persons[key] = qualifying

            if len(qualifying) == 0:
                category = "unknown_person"
                dest_dir = os.path.join(args.out_dir, "unknown_person") if args.out_dir else ""
            elif len(qualifying) == 1:
                category = f"person_{qualifying[0]:03d}"
                dest_dir = os.path.join(args.out_dir, category) if args.out_dir else ""
            else:
                category = "multiple_people"
                dest_dir = os.path.join(args.out_dir, "multiple_people") if args.out_dir else ""

        # Video fayl nomi
        vname = os.path.basename(zip_inner_path) if zip_inner_path else os.path.basename(vpath)

        report_rows.append({
            "video": zip_inner_path if zip_inner_path else vpath,
            "source_archive": vpath if zip_inner_path else "",
            "category": category,
            "persons_detected": ",".join(str(p) for p in qualifying),
        })

        should_copy = True
        if selected_pids is not None:
            should_copy = any(p in selected_pids for p in qualifying)

        if should_copy and not args.dry_run and args.out_dir:
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, vname)
            
            # Nomlar to'qnashib qolmasligi uchun
            base, ext = os.path.splitext(dest_path)
            i = 1
            while os.path.exists(dest_path):
                dest_path = f"{base}_{i}{ext}"
                i += 1

            if zip_inner_path:
                # Ogohlantirish
                if args.move:
                    print(f"OGOHLANTIRISH: ZIP ichidagi fayllarni ko'chirib (move) bo'lmaydi. Nusxalash bajarildi -> {vname}")
                
                with zipfile.ZipFile(vpath, "r") as z:
                    with z.open(zip_inner_path) as src:
                        with open(dest_path, "wb") as tgt:
                            shutil.copyfileobj(src, tgt)
            else:
                if os.path.exists(vpath):
                    if args.move:
                        shutil.move(vpath, dest_path)
                    else:
                        shutil.copy2(vpath, dest_path)
                else:
                    print(f"XATO: Manba fayl topilmadi -> {vpath}")

    if args.out_dir:
        report_path = os.path.join(args.out_dir, "report.csv")
        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["video", "source_archive", "category", "persons_detected"])
            writer.writeheader()
            writer.writerows(report_rows)
        print(f"Hisobot -> {report_path}")

    print(f"Jami video: {len(video_info)}")
    if args.dry_run:
        if args.out_dir:
            print("DRY RUN: fayllarga tegilmadi. report.csv ni tekshirib chiqing.")
        else:
            print("DRY RUN: fayllarga tegilmadi va nusxalanmadi.")
    else:
        action_verb = "ko'chirildi" if args.move else "nusxalandi"
        print(f"Barcha videolar {action_verb} va tartiblandi.")

    # --- INSONLAR BO'YICHA STATISTIKA ---
    # person_id -> list of video filenames
    person_videos = defaultdict(set)
    for key, pids in video_qualifying_persons.items():
        vpath, zip_inner = key
        vname = os.path.basename(zip_inner) if zip_inner else os.path.basename(vpath)
        for pid in pids:
            person_videos[pid].add(vname)

    # Har bir person_id uchun vakil video topish (eng yuqori det_score * track_len bo'lgan)
    person_rep_record = {}
    for r in records:
        pid = r.get("person_id", -2)
        if pid >= 0:
            vpath = r["video_path"]
            zip_inner = r.get("zip_inner_path")
            key = (vpath, zip_inner)
            if key in video_qualifying_persons and pid in video_qualifying_persons[key]:
                quality = r.get("det_score", 0.0) * r.get("track_len", 1)
                if pid not in person_rep_record or quality > person_rep_record[pid]["quality"]:
                    vname = os.path.basename(zip_inner) if zip_inner else os.path.basename(vpath)
                    person_rep_record[pid] = {
                        "vname": vname,
                        "quality": quality
                    }

    sorted_people = sorted(
        person_videos.keys(),
        key=lambda pid: len(person_videos[pid]),
        reverse=True
    )

    print("\n" + "=" * 60)
    print("INSONLAR BO'YICHA VIDEOLAR SONI (TARTIBLANGAN):")
    print("=" * 60)
    if not sorted_people:
        print("Hech qanday inson (klaster) aniqlanmadi.")
    for idx, pid in enumerate(sorted_people, 1):
        rep_video = person_rep_record.get(pid, {}).get("vname", "noma'lum")
        count = len(person_videos[pid])
        print(f"{idx}. person_{pid:03d} (Vakil video: {rep_video}) -> {count} ta video")
    print("=" * 60)

    # Interaktiv batafsil ko'rish
    import sys
    if sys.stdin.isatty():
        try:
            while True:
                choice = input("\nBatafsil ko'rish uchun inson ID sini kiriting (masalan, 0) yoki chiqish uchun Enter tugmasini bosing: ").strip()
                if not choice:
                    break
                try:
                    pid = int(choice)
                    if pid in person_videos:
                        print(f"\nperson_{pid:03d} ishtirok etgan videolar ({len(person_videos[pid])} ta):")
                        for v_idx, v_name in enumerate(sorted(list(person_videos[pid])), 1):
                            print(f"  {v_idx}. {v_name}")
                    else:
                        print(f"XATO: Bunday inson ID si topilmadi (mavjud ID lar: {', '.join(str(p) for p in sorted(person_videos.keys()))})")
                except ValueError:
                    print("Iltimos, to'g'ri inson ID raqamini (butun son) kiriting.")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
"""
videos.zip ni N ta kichik ZIP ga bo'lib chiqadi.
Ishlatish: python split_zip.py
"""

import zipfile
import os
from pathlib import Path
from math import ceil

# ─── SOZLAMALAR ──────────────────────────────────────────────
INPUT_ZIP   = r"C:\Users\user\Downloads\videos.zip"   # Katta ZIP yo'li
OUTPUT_DIR  = r"C:\Users\user\Downloads\split_zips"   # Chiqish papkasi
NUM_PARTS   = 5                                         # Nechta bo'lakka bo'lish
# ─────────────────────────────────────────────────────────────

VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.flv'}

def split_zip(input_zip, output_dir, num_parts):
    print(f"📂 ZIP ochilmoqda: {input_zip}")

    with zipfile.ZipFile(input_zip, 'r') as z:
        all_info = z.infolist()
        videos = [f for f in all_info if Path(f.filename).suffix.lower() in VIDEO_EXTS]

    total = len(videos)
    print(f"📹 Jami videolar: {total} ta")
    print(f"📦 Bo'laklarga ajratish: {num_parts} ta\n")

    if total == 0:
        print("❌ ZIP ichida video topilmadi!")
        return

    per_part = ceil(total / num_parts)
    os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(input_zip, 'r') as src:
        for part_idx in range(num_parts):
            start = part_idx * per_part
            end   = min(start + per_part, total)
            part_videos = videos[start:end]

            if not part_videos:
                continue

            out_path = os.path.join(output_dir, f"videos_part{part_idx + 1}.zip")
            print(f"⏳ Part {part_idx+1} yaratilmoqda ({len(part_videos)} ta video)...")

            with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_STORED) as out_zip:
                for info in part_videos:
                    data = src.read(info.filename)
                    # Faqat fayl nomini saqlaymiz (papka tuzilmasiz)
                    out_zip.writestr(Path(info.filename).name, data)

            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"   ✅ {out_path}  ({size_mb:.0f} MB, {len(part_videos)} video)")

    print(f"\n🎉 Tayyor! {output_dir} papkasiga {num_parts} ta ZIP yaratildi.")
    print("Ularni Telegram botga birma-bir yuboring.")

if __name__ == "__main__":
    split_zip(INPUT_ZIP, OUTPUT_DIR, NUM_PARTS)

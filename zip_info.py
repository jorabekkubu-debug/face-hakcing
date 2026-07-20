import argparse
import os
import zipfile
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip_path", required=True, help="ZIP fayl yo'li")
    ap.add_argument("--max_size_mb", type=float, default=20.0, help="Tekshiriladigan maksimal video hajmi (MB)")
    args = ap.parse_args()

    zip_abs_path = os.path.abspath(args.zip_path)
    if not os.path.exists(zip_abs_path):
        print(f"XATO: ZIP fayl topilmadi -> {zip_abs_path}")
        return

    print("=" * 60)
    print(f"ZIP ARXIV TAHLILI: {os.path.basename(zip_abs_path)}")
    print("=" * 60)

    total_files = 0
    total_videos = 0
    small_videos = 0
    large_videos = 0
    total_video_bytes = 0

    sizes_mb = []

    with zipfile.ZipFile(zip_abs_path, "r") as z:
        infolist = z.infolist()
        total_files = len(infolist)
        for info in infolist:
            name = info.filename
            if Path(name).suffix.lower() in VIDEO_EXTS:
                total_videos += 1
                size_mb = info.file_size / (1024 * 1024)
                sizes_mb.append(size_mb)
                total_video_bytes += info.file_size
                if size_mb <= args.max_size_mb:
                    small_videos += 1
                else:
                    large_videos += 1

    print(f"Arxiv ichidagi barcha fayllar soni: {total_files}")
    print(f"Jami video fayllar soni:            {total_videos}")
    print("-" * 60)
    if total_videos == 0:
        print("ZIP ichida hech qanday video topilmadi.")
        return
    print(f"Hajmi <= {args.max_size_mb} MB bo'lgan videolar:   {small_videos} ({small_videos/total_videos*100:.1f}%)")
    print(f"Hajmi >  {args.max_size_mb} MB bo'lgan videolar:    {large_videos} ({large_videos/total_videos*100:.1f}%)")
    print("-" * 60)
    
    if total_videos > 0:
        avg_size = (total_video_bytes / total_videos) / (1024 * 1024)
        total_size_gb = total_video_bytes / (1024 * 1024 * 1024)
        print(f"Videolarning jami hajmi:            {total_size_gb:.2f} GB")
        print(f"Bitta videoning o'rtacha hajmi:      {avg_size:.2f} MB")
        
        # Hajm bo'yicha taqsimot diapazonlari
        ranges = [
            ("0 - 5 MB", lambda x: x <= 5),
            ("5 - 10 MB", lambda x: 5 < x <= 10),
            ("10 - 20 MB", lambda x: 10 < x <= 20),
            ("20 - 50 MB", lambda x: 20 < x <= 50),
            ("50 - 100 MB", lambda x: 50 < x <= 100),
            ("> 100 MB", lambda x: x > 100)
        ]
        
        print("\nVideolar hajmi bo'yicha taqsimoti:")
        print("-" * 60)
        for label, cond in ranges:
            count = sum(1 for s in sizes_mb if cond(s))
            pct = (count / total_videos) * 100 if total_videos > 0 else 0
            bar = "#" * int(pct / 2)
            print(f"{label:<12} | {count:<5} ({pct:>5.1f}%) | {bar}")
    print("=" * 60)

if __name__ == "__main__":
    main()

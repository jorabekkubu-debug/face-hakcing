import os
import sys
import argparse
import subprocess
from pathlib import Path

def run_cli(zip_path, device="gpu", threshold=0.50, every_sec=5.0):
    print("=" * 65)
    print("🚀 AI VIDEO FACE ANALYTICS (CLI REJIM)")
    print(f"📦 ZIP fayl: {zip_path}")
    print(f"⚙️ Qurilma: {device.upper()}")
    print("=" * 65)

    if not os.path.exists(zip_path):
        print(f"❌ XATOLIK: ZIP fayl topilmadi -> {zip_path}")
        return

    # 1-BOSQICH: Video tahlili va Yuzlarni yig'ish
    print("\n--- 1-BOSQICH: Videolardan Yuzlarni Tahlil Qilish ---")
    cmd1 = [
        sys.executable, "loyha.py",
        "--zip_path", zip_path,
        "--out", "faces_data.pkl",
        "--every_sec", str(every_sec),
        "--device", device,
        "--save_thumbs",
        "--thumbs_dir", "face_thumbs"
    ]
    res1 = subprocess.run(cmd1)
    if res1.returncode != 0:
        print("❌ 1-Bosqichda xatolik yuz berdi!")
        return

    # 2-BOSQICH: Yuzlarni Klasterlash
    print("\n--- 2-BOSQICH: Inson Yuzlarini Guruhlash va Klasterlash ---")
    cmd2 = [
        sys.executable, "loyha2.py",
        "--data", "faces_data.pkl",
        "--out", "faces_clustered.pkl",
        "--threshold", str(threshold),
        "--min_cluster_size", "1",
        "--preview_dir", "clusters_preview"
    ]
    res2 = subprocess.run(cmd2)
    if res2.returncode != 0:
        print("❌ 2-Bosqichda xatolik yuz berdi!")
        return

    print("\n" + "=" * 65)
    print("🎉 TAHLIL MUVAFFAQIYATLI YAKUNLANDI!")
    print("📁 Natijaviy inson yuzlari rasmlari papkasi: clusters_preview/")
    print("=" * 65)
    print("\n💡 Endi o'zingizga kerakli inson videolarini ajratib olish uchun:")
    print("   python loyha3.py --zip_path YOUR_ZIP --clustered faces_clustered.pkl --persons 0 1")

def main():
    ap = argparse.ArgumentParser(description="AI Video Face Analytics CLI Runner")
    ap.add_argument("--zip_path", required=True, help="Tahlil qilinadigan ZIP fayli yo'li")
    ap.add_argument("--device", choices=["gpu", "cpu"], default="gpu", help="Qurilma (gpu yoki cpu)")
    ap.add_argument("--threshold", type=float, default=0.50, help="Yuz moslik darajasi (default: 0.50)")
    ap.add_argument("--every_sec", type=float, default=5.0, help="Har necha soniyada freym olish (default: 5.0)")
    args = ap.parse_args()

    run_cli(args.zip_path, device=args.device, threshold=args.threshold, every_sec=args.every_sec)

if __name__ == "__main__":
    main()

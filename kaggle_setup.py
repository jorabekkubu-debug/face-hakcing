"""
Kaggle Notebook — To'liq ishga tushirish kodi
Quyidagi kodni Kaggle notebook'ga cell bo'lib joylashtiring.
"""

# ════════════════════════════════════════════
# CELL 1 — Muhitni tayyorlash
# ════════════════════════════════════════════
"""
%cd /kaggle/working
!rm -rf /kaggle/working/my_bot
!fuser -k 8000/tcp 2>/dev/null || true
"""

# ════════════════════════════════════════════
# CELL 2 — Kutubxonalarni o'rnatish
# ════════════════════════════════════════════
"""
!pip install -q \
    aiogram==3.17.0 \
    insightface==0.7.3 \
    onnxruntime==1.20.0 \
    opencv-python-headless \
    scikit-learn numpy requests tqdm \
    fastapi uvicorn python-multipart \
    pyngrok
"""

# ════════════════════════════════════════════
# CELL 3 — Token va GitHub repo
# ════════════════════════════════════════════
"""
import os
os.environ["BOT_TOKEN"] = "8204492763:AAH_X8BpE-NoNhrfToDV2U42ciST8jNaoiE"

!git clone https://github.com/jorabekkubu-debug/face-hakcing.git /kaggle/working/my_bot
%cd /kaggle/working/my_bot
"""

# ════════════════════════════════════════════
# CELL 4 — Web serverni ishga tushirish + ngrok tunnel
# ════════════════════════════════════════════
"""
import subprocess, time, os
from pyngrok import ngrok

# Web serverni background'da ishga tushiramiz
web_proc = subprocess.Popen([
    "uvicorn", "web_app:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--log-level", "warning"
])

# Server tayyor bo'lguncha kutamiz
time.sleep(3)
print("✅ Web server port 8000 da ishga tushdi.")

# Ngrok tunnel ochish
# IXTIYORIY: agar ngrok accountingiz bo'lsa tokenni qo'shing (bepul hisobda 8 soat ishlaydi)
# ngrok.set_auth_token("your_ngrok_token_here")

tunnel = ngrok.connect(8000, "http")
public_url = tunnel.public_url

print("=" * 60)
print(f"🌐 WEB PORTAL MANZILI (brauzerda oching):")
print(f"   {public_url}")
print("=" * 60)
print("Ushbu manzilni oching → ZIP yuklang → Kodni oling → Botga yuboring!")
"""

# ════════════════════════════════════════════
# CELL 5 — Telegram Botni ishga tushirish
# (Bu cell bloklanadi — bu normal!)
# ════════════════════════════════════════════
"""
!python bot.py
"""

"""
Kaggle'da hamma narsani birga ishga tushuradigan bosh fayl.
Ikkala xizmatni ham ishga tushiradi:
  1. FastAPI web portal (pyngrok orqali public URL bilan)
  2. Telegram Bot (aiogram polling)

Ishlatish (Kaggle notebook'da):
    import subprocess
    subprocess.Popen(["python", "run_all.py"])
    
    yoki to'g'ridan-to'g'ri:
    !python run_all.py
"""

import os
import sys
import asyncio
import logging
import threading
import subprocess

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_all")

# ─── Konfiguratsiya ──────────────────────────────────────────────────────────
WEB_PORT      = int(os.getenv("WEB_PORT", "8000"))
NGROK_TOKEN   = os.getenv("NGROK_AUTH_TOKEN", "")   # Kaggle Secret yoki quyida to'g'ridan to'g'ri kiriting
BOT_TOKEN     = os.getenv("BOT_TOKEN", "8204492763:AAH_X8BpE-NoNhrfToDV2U42ciST8jNaoiE")


def start_web_server():
    """Web serverni alohida jarayonda ishga tushiradi."""
    log.info(f"🌐 Web server port {WEB_PORT} da ishga tushmoqda...")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "web_app:app",
        "--host", "0.0.0.0",
        "--port", str(WEB_PORT),
        "--log-level", "warning",
    ])


def start_ngrok():
    """
    pyngrok orqali tunnelni ochadi va public URL ni chop etadi.
    Avval pyngrok o'rnatilgan bo'lishi kerak: pip install pyngrok
    """
    try:
        from pyngrok import ngrok, conf

        if NGROK_TOKEN:
            conf.get_default().auth_token = NGROK_TOKEN
            log.info("✅ Ngrok autentifikatsiya tokeni o'rnatildi.")
        else:
            log.warning(
                "⚠️  NGROK_AUTH_TOKEN o'rnatilmagan. "
                "Bepul limitlar qo'llaniladi (1 ta tunnel, 8 soat)."
            )

        # Veb-server tayyor bo'lguncha biroz kutamiz
        import time
        time.sleep(3)

        tunnel = ngrok.connect(WEB_PORT, "http")
        public_url = tunnel.public_url
        log.info("=" * 60)
        log.info(f"🔗 WEB PORTAL PUBLIC URL: {public_url}")
        log.info("=" * 60)
        print(f"\n{'='*60}")
        print(f"  🌐 Veb portal manzili (internetda ochiq):")
        print(f"  {public_url}")
        print(f"{'='*60}\n")
        return public_url

    except ImportError:
        log.error("❌ pyngrok o'rnatilmagan. Quyidagi buyruqni ishga tushiring:")
        log.error("   pip install pyngrok")
        return None
    except Exception as e:
        log.error(f"❌ Ngrok xatoligi: {e}")
        return None


async def start_bot():
    """Telegram botni ishga tushiradi."""
    # bot.py dagi bot va dp ni import qilamiz
    from aiogram import Bot, Dispatcher
    from bot import dp, bot as tg_bot

    log.info("🤖 Telegram bot ishga tushmoqda...")
    try:
        await dp.start_polling(tg_bot)
    except Exception as e:
        log.error(f"❌ Bot xatoligi: {e}")
        raise


def main():
    log.info("🚀 Barcha xizmatlar ishga tushirilmoqda...")

    # 1. Web serverni alohida threadda ishga tushiramiz
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    # 2. Ngrok tunnelni alohida threadda ochib, URL ni chiqaramiz
    ngrok_thread = threading.Thread(target=start_ngrok, daemon=True)
    ngrok_thread.start()

    # 3. Telegram botni asosiy thread da ishga tushiramiz (asyncio)
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        log.info("⛔ Jarayon to'xtatildi.")


if __name__ == "__main__":
    main()

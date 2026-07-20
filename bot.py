import os
import sys
import logging
import asyncio
import tempfile
import shutil
import time
import urllib.request
import urllib.parse
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core_engine import FacePipeline

# Environment setup
BOT_TOKEN = os.getenv("BOT_TOKEN", "8204492763:AAH_X8BpE-NoNhrfToDV2U42ciST8jNaoiE")
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Memory session state: user_id -> state dict
USER_SESSIONS = {}

pipeline_engine = None

def get_pipeline():
    global pipeline_engine
    if pipeline_engine is None:
        pipeline_engine = FacePipeline(use_gpu=True)
    return pipeline_engine

@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = (
        "👋 **Xush kelibsiz!**\n\n"
        "Men videolardagi inson yuzlarini Sun'iy Intellekt yordamida tahlil qiluvchi va "
        "avtomatik guruhlovchi botman.\n\n"
        "📹 **Menga nimani yuborishingiz mumkin?**\n"
        "1. Videosi bor **ZIP fayl** (hujjat ko'rinishida yuboring).\n"
        "2. Yoki **Cloud.mail.ru** ommaviy havolasini yuboring.\n\n"
        "Tahlil vaqtida men sizga real vaqtda nechta video tahlil qilingani va qanchasi qolganini aytib turaman!"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(F.document)
async def handle_document(message: Message):
    doc = message.document
    if not doc.file_name.lower().endswith('.zip'):
        await message.answer("⚠️ Iltimos, faqat `.zip` kengaytmali arxiv fayl yuboring!")
        return

    msg = await message.answer("📥 ZIP fayl yuklab olinmoqda, iltimos kuting...")
    
    user_id = message.from_user.id
    work_dir = tempfile.mkdtemp(prefix=f"bot_session_{user_id}_")
    zip_path = os.path.join(work_dir, "uploaded_videos.zip")

    file_info = await bot.get_file(doc.file_id)
    await bot.download_file(file_info.file_path, zip_path)

    await process_videos_task(message, work_dir, zip_path, msg)

@dp.message(F.text.startswith("http://") | F.text.startswith("https://"))
async def handle_url(message: Message):
    url = message.text.strip()
    msg = await message.answer("🌐 Bulutli havola qabul qilindi. Fayl yuklanmoqda...")

    user_id = message.from_user.id
    work_dir = tempfile.mkdtemp(prefix=f"bot_session_{user_id}_")
    zip_path = os.path.join(work_dir, "downloaded_videos.zip")

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        await process_videos_task(message, work_dir, zip_path, msg)
    except Exception as e:
        await msg.edit_text(f"❌ Faylni havoladan yuklashda xatolik yuz berdi: {e}")
        shutil.rmtree(work_dir, ignore_errors=True)

async def process_videos_task(message: Message, work_dir: str, zip_path: str, status_msg: Message):
    user_id = message.from_user.id
    last_update_time = [0.0]

    async def async_update_progress(current, total, current_video):
        now = time.time()
        # Update Telegram status at most once every 3 seconds to avoid rate limits
        if now - last_update_time[0] >= 3.0 or current == total:
            last_update_time[0] = now
            pct = int((current / total) * 100)
            bar_len = 10
            filled = int(bar_len * current / total)
            bar = "▓" * filled + "░" * (bar_len - filled)
            remaining = total - current
            vname = os.path.basename(current_video)
            
            text = (
                f"⚙️ **Videolar tahlil qilinmoqda (GPU)...**\n\n"
                f"Progress: [{bar}] **{pct}%**\n"
                f"✅ Tahlil qilindi: **{current} / {total}** ta video\n"
                f"⏳ Qoldi: **{remaining}** ta video\n"
                f"📹 Hozirgi video: `{vname[:30]}`"
            )
            try:
                await status_msg.edit_text(text, parse_mode="Markdown")
            except Exception:
                pass

    loop = asyncio.get_running_loop()

    def sync_progress_callback(current, total, video_name):
        asyncio.run_coroutine_threadsafe(
            async_update_progress(current, total, video_name), loop
        )

    try:
        engine = get_pipeline()
        
        data_pkl_path = await loop.run_in_executor(
            None, engine.analyze_zip, zip_path, work_dir, 5.0, sync_progress_callback
        )

        await status_msg.edit_text("🔍 Yuzlar klasterlanmoqda va guruhlanmoqda...")
        
        person_summary, records = await loop.run_in_executor(
            None, engine.cluster_faces, data_pkl_path, work_dir, 0.50, 1
        )

        if not person_summary:
            await status_msg.edit_text("❌ Videolardan birorta ham yuz aniqlanmadi.")
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        USER_SESSIONS[user_id] = {
            "work_dir": work_dir,
            "zip_path": zip_path,
            "clustered_pkl_path": os.path.join(work_dir, "faces_clustered.pkl"),
            "person_summary": person_summary,
            "selected_ids": set()
        }

        top_people = sorted(person_summary.items(), key=lambda x: x[1]['videos_count'], reverse=True)[:10]

        await status_msg.edit_text(
            f"✅ **Tahlil to'liq yakunlandi!**\n\n"
            f"📊 Jami topilgan insonlar: **{len(person_summary)} ta**\n"
            f"👇 Quyidagi tugmalardan o'zingizga kerakli insonni tanlang:",
            parse_mode="Markdown"
        )

        builder = InlineKeyboardBuilder()
        for pid, pdata in top_people:
            btn_text = f"👤 Inson #{pid} ({pdata['videos_count']} ta video)"
            builder.button(text=btn_text, callback_query_data=f"select_person_{pid}")
        
        builder.adjust(1)
        builder.row(InlineKeyboardButton(text="📦 Tanlangan videolarni yuklab olish", callback_query_data="finish_selection"))

        first_pid, first_pdata = top_people[0]
        preview_file = FSInputFile(first_pdata["preview_path"])
        
        await message.answer_photo(
            photo=preview_file,
            caption="📸 Eng ko'p ko'ringan inson (Namuna rasm):\nInsonlarni tanlab, poyondagi tugmani bosing.",
            reply_markup=builder.as_markup()
        )

    except zipfile.BadZipFile:
        await status_msg.edit_text("❌ **Xatolik:** Yuborilgan fayl yoki havola to'g'ri ZIP arxiv emas!\nIltimos, videolarni `.zip` fayli ko'rinishida yuboring.", parse_mode="Markdown")
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception as e:
        logging.error(f"Xatolik: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")

@dp.callback_query(F.data.startswith("select_person_"))
async def cb_select_person(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.answer("⚠️ Sessiya muddati tugagan. Iltimos, faylni qayta yuboring.", show_alert=True)
        return

    pid = int(callback.data.split("_")[-1])
    session = USER_SESSIONS[user_id]
    
    if pid in session["selected_ids"]:
        session["selected_ids"].remove(pid)
        await callback.answer(f"❌ Inson #{pid} ro'yxatdan olib tashlandi.")
    else:
        session["selected_ids"].add(pid)
        await callback.answer(f"✅ Inson #{pid} tanlandi!")

    person_summary = session["person_summary"]
    top_people = sorted(person_summary.items(), key=lambda x: x[1]['videos_count'], reverse=True)[:10]

    builder = InlineKeyboardBuilder()
    for item_pid, pdata in top_people:
        is_selected = item_pid in session["selected_ids"]
        icon = "✅" if is_selected else "👤"
        btn_text = f"{icon} Inson #{item_pid} ({pdata['videos_count']} ta video)"
        builder.button(text=btn_text, callback_data=f"select_person_{item_pid}")
    
    builder.adjust(1)
    selected_count = len(session["selected_ids"])
    builder.row(InlineKeyboardButton(
        text=f"📦 Tanlangan ({selected_count} ta inson) videolarni yuklash",
        callback_data="finish_selection"
    ))

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

@dp.callback_query(F.data == "finish_selection")
async def cb_finish_selection(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.answer("⚠️ Sessiya topilmadi.", show_alert=True)
        return

    session = USER_SESSIONS[user_id]
    selected_ids = list(session["selected_ids"])

    if not selected_ids:
        await callback.answer("⚠️ Iltimos, kamida bitta insonni tanlang!", show_alert=True)
        return

    await callback.answer("📦 Videolar tayyorlanmoqda...")
    msg = await callback.message.answer("📦 Tanlangan insonlarning videolari alohida ZIP qilinmoqda...")

    work_dir = session["work_dir"]
    out_zip_path = os.path.join(work_dir, "selected_result.zip")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        FacePipeline.extract_person_videos,
        session["zip_path"],
        session["clustered_pkl_path"],
        selected_ids,
        out_zip_path
    )

    if os.path.exists(out_zip_path) and os.path.getsize(out_zip_path) > 0:
        result_file = FSInputFile(out_zip_path, filename="selected_person_videos.zip")
        await callback.message.answer_document(
            document=result_file,
            caption=f"🎉 **Tayyor!**\nSiz tanlagan insonlar ({selected_ids}) qatnashgan barcha videolar ajratildi."
        )
        await msg.delete()
    else:
        await msg.edit_text("❌ Afsuski, mos videolar topilmadi yoki arxivlashda xatolik bo'ldi.")

    shutil.rmtree(work_dir, ignore_errors=True)
    del USER_SESSIONS[user_id]

async def main():
    print("🤖 Telegram Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

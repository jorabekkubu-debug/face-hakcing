import os
import sys
import logging
import asyncio
import tempfile
import shutil
import time
import zipfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core_engine import FacePipeline
import task_db

# ─── Sozlamalar ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8204492763:AAH_X8BpE-NoNhrfToDV2U42ciST8jNaoiE")
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ─── Global holatlar ─────────────────────────────────────────────────────────
# user_id -> {
#   "work_dir": str,
#   "zip_paths": [str, ...],          # Qabul qilingan ZIP fayllar
#   "collection_msg_id": int,         # ZIP yig'ish xabar ID si
#   "selected_ids": set,              # Tanlangan insonlar (tahlildan keyin)
#   "person_summary": dict,
#   "clustered_pkl_path": str,
# }
USER_SESSIONS: dict = {}

pipeline_engine = None

def get_pipeline():
    global pipeline_engine
    if pipeline_engine is None:
        pipeline_engine = FacePipeline(use_gpu=True)
    return pipeline_engine


# ─── /start ──────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 **Xush kelibsiz!**\n\n"
        "Men videolardagi yuzlarni AI yordamida tahlil qilaman.\n\n"
        "📦 **Qanday ishlatiladi:**\n"
        "1. Videolaringizni ZIP fayl ko'rinishiga oling\n"
        "2. ZIP fayllarni bu yerga yuboring (bir yoki bir nechta)\n"
        "3. Barcha fayllar yuborilgach **✅ Tahlilni Boshlash** tugmasini bosing\n"
        "4. Tahlil tugagach insonlarni tanlang va videolarni yuklab oling!\n\n"
        "🚀 Boshlash uchun ZIP fayl yuboring!"
    )
    await message.answer(text, parse_mode="Markdown")


# ─── ZIP fayl qabul qilish ────────────────────────────────────────────────────
@dp.message(F.document)
async def handle_document(message: Message):
    doc = message.document

    # Faqat ZIP qabul qilamiz
    if not doc.file_name.lower().endswith('.zip'):
        await message.answer("⚠️ Iltimos, faqat `.zip` kengaytmali fayl yuboring!")
        return

    # Fayl hajmini tekshirish (Telegram max 2GB)
    size_mb = doc.file_size / 1024 / 1024

    user_id = message.from_user.id

    # Yangi session yoki mavjud session
    if user_id not in USER_SESSIONS:
        work_dir = tempfile.mkdtemp(prefix=f"bot_{user_id}_")
        USER_SESSIONS[user_id] = {
            "work_dir": work_dir,
            "zip_paths": [],
            "collection_msg_id": None,
            "selected_ids": set(),
            "person_summary": {},
            "clustered_pkl_path": None,
        }

    session = USER_SESSIONS[user_id]
    work_dir = session["work_dir"]

    # Yuklab olish
    status = await message.answer(f"📥 `{doc.file_name}` yuklab olinmoqda ({size_mb:.1f} MB)...", parse_mode="Markdown")
    zip_path = os.path.join(work_dir, f"part_{len(session['zip_paths']) + 1:02d}_{doc.file_name}")

    try:
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, zip_path)
    except Exception as e:
        await status.edit_text(f"❌ Yuklashda xatolik: {e}")
        return

    session["zip_paths"].append(zip_path)
    await status.delete()

    # Yig'ish xabarini yangilaymiz
    await update_collection_message(message, session)


async def update_collection_message(message: Message, session: dict):
    """ZIP yig'ish holatini ko'rsatuvchi xabarni yangilaydi yoki yaratadi."""
    user_id = message.from_user.id
    zip_paths = session["zip_paths"]
    count = len(zip_paths)

    # Ro'yxat
    lines = []
    total_mb = 0.0
    for i, zp in enumerate(zip_paths, 1):
        mb = os.path.getsize(zp) / 1024 / 1024
        total_mb += mb
        lines.append(f"  📦 {i}. `{Path(zp).name}` — {mb:.1f} MB")

    text = (
        f"📂 **{count} ta ZIP fayl qabul qilindi** (jami {total_mb:.1f} MB)\n\n"
        + "\n".join(lines)
        + "\n\n"
        "➕ Yana ZIP yuboring yoki tahlilni boshlang:"
    )

    # Keyboard
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"🚀 Tahlilni Boshlash ({count} ta ZIP)",
        callback_data="start_analysis"
    ))
    builder.row(InlineKeyboardButton(
        text="🗑️ Bekor qilish",
        callback_data="cancel_session"
    ))
    markup = builder.as_markup()

    # Yangi xabar yoki mavjudni yangilash
    if session["collection_msg_id"]:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=session["collection_msg_id"],
                parse_mode="Markdown",
                reply_markup=markup
            )
            return
        except Exception:
            pass  # Yangilashda xatolik bo'lsa, yangi xabar yuboramiz

    sent = await message.answer(text, parse_mode="Markdown", reply_markup=markup)
    session["collection_msg_id"] = sent.message_id


# ─── Tahlilni boshlash ────────────────────────────────────────────────────────
@dp.callback_query(F.data == "start_analysis")
async def cb_start_analysis(callback: CallbackQuery):
    user_id = callback.from_user.id

    if user_id not in USER_SESSIONS or not USER_SESSIONS[user_id]["zip_paths"]:
        await callback.answer("⚠️ Avval ZIP fayl yuboring!", show_alert=True)
        return

    await callback.answer("🚀 Tahlil boshlanmoqda...")

    session = USER_SESSIONS[user_id]
    zip_paths = session["zip_paths"]
    work_dir  = session["work_dir"]

    # Yig'ish xabarini o'chirish
    try:
        await callback.message.delete()
    except Exception:
        pass

    status_msg = await callback.message.answer(
        f"⚙️ **{len(zip_paths)} ta ZIP tahlil qilinmoqda...**\n\n"
        "⏳ Iltimos kuting, bu bir necha daqiqa vaqt olishi mumkin.",
        parse_mode="Markdown"
    )

    await process_zips_task(callback.message, session, zip_paths, work_dir, status_msg)


# ─── Bekor qilish ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "cancel_session")
async def cb_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in USER_SESSIONS:
        shutil.rmtree(USER_SESSIONS[user_id]["work_dir"], ignore_errors=True)
        del USER_SESSIONS[user_id]
    await callback.message.edit_text("❌ Bekor qilindi. Qayta boshlash uchun ZIP fayl yuboring.")
    await callback.answer()


# ─── Asosiy tahlil vazifasi ───────────────────────────────────────────────────
async def process_zips_task(
    message: Message,
    session: dict,
    zip_paths: list,
    work_dir: str,
    status_msg: Message
):
    user_id = message.from_user.id
    last_update = [0.0]

    async def async_progress(current, total, video_name):
        now = time.time()
        if now - last_update[0] < 3.0 and current != total:
            return
        last_update[0] = now

        pct = int(current / total * 100)
        filled = int(10 * current / total)
        bar = "▓" * filled + "░" * (10 - filled)
        vname = os.path.basename(video_name)[:30]
        text = (
            f"⚙️ **Videolar tahlil qilinmoqda...**\n\n"
            f"[{bar}] **{pct}%**\n"
            f"✅ Tahlil: **{current}/{total}** ta video\n"
            f"⏳ Qoldi: **{total - current}** ta\n"
            f"📹 Hozir: `{vname}`"
        )
        try:
            await status_msg.edit_text(text, parse_mode="Markdown")
        except Exception:
            pass

    loop = asyncio.get_running_loop()

    def sync_progress(current, total, video_name):
        asyncio.run_coroutine_threadsafe(
            async_progress(current, total, video_name), loop
        )

    try:
        engine = get_pipeline()

        # Barcha ZIP larni birga tahlil qilamiz
        data_pkl = await loop.run_in_executor(
            None,
            engine.analyze_zip_batch,
            zip_paths, work_dir, 5.0, sync_progress
        )

        await status_msg.edit_text("🔍 Yuzlar klasterlanmoqda...")

        person_summary, records = await loop.run_in_executor(
            None,
            engine.cluster_faces,
            data_pkl, work_dir, 0.50, 1
        )

        if not person_summary:
            await status_msg.edit_text(
                "❌ Videolardan birorta ham yuz aniqlanmadi.\n"
                "ZIP fayllar video fayl o'z ichiga olganligini tekshiring."
            )
            shutil.rmtree(work_dir, ignore_errors=True)
            del USER_SESSIONS[user_id]
            return

        # Session yangilash
        session["person_summary"]    = person_summary
        session["clustered_pkl_path"] = os.path.join(work_dir, "faces_clustered.pkl")

        # Umumiy statistika
        total_videos = sum(p["videos_count"] for p in person_summary.values())
        top_people = sorted(
            person_summary.items(),
            key=lambda x: x[1]["videos_count"],
            reverse=True
        )[:10]

        await status_msg.edit_text(
            f"✅ **Tahlil yakunlandi!**\n\n"
            f"📊 Topilgan insonlar: **{len(person_summary)} ta**\n"
            f"📹 Jami videolar: **{total_videos} ta**\n"
            f"📦 Tahlil qilingan ZIP lar: **{len(zip_paths)} ta**\n\n"
            "👇 Kerakli insonlarni tanlang:",
            parse_mode="Markdown"
        )

        # Inson tanlash klaviaturasi
        builder = InlineKeyboardBuilder()
        for pid, pdata in top_people:
            btn = f"👤 Inson #{pid}  ({pdata['videos_count']} ta video)"
            builder.button(text=btn, callback_data=f"select_person_{pid}")
        builder.adjust(1)
        builder.row(InlineKeyboardButton(
            text="📦 Tanlangan videolarni yuklab olish",
            callback_data="finish_selection"
        ))

        # Preview rasm
        first_pid, first_data = top_people[0]
        preview_file = FSInputFile(first_data["preview_path"])
        await message.answer_photo(
            photo=preview_file,
            caption="📸 Eng ko'p ko'ringan inson (preview):\nQuyidagilardan tanlang 👇",
            reply_markup=builder.as_markup()
        )

    except zipfile.BadZipFile:
        await status_msg.edit_text(
            "❌ Yuborilgan fayllardan biri noto'g'ri ZIP arxiv!\n"
            "Iltimos, videolarni to'g'ri ZIP qilib yuboring."
        )
        shutil.rmtree(work_dir, ignore_errors=True)
        if user_id in USER_SESSIONS:
            del USER_SESSIONS[user_id]
    except Exception as e:
        logging.error(f"Tahlil xatoligi: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Xatolik yuz berdi:\n`{e}`", parse_mode="Markdown")


# ─── Inson tanlash ────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("select_person_"))
async def cb_select_person(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.answer("⚠️ Sessiya muddati tugagan. Qayta ZIP yuboring.", show_alert=True)
        return

    pid = int(callback.data.split("_")[-1])
    session = USER_SESSIONS[user_id]

    if pid in session["selected_ids"]:
        session["selected_ids"].remove(pid)
        await callback.answer(f"❌ Inson #{pid} olib tashlandi.")
    else:
        session["selected_ids"].add(pid)
        await callback.answer(f"✅ Inson #{pid} tanlandi!")

    # Klaviaturani yangilash
    person_summary = session["person_summary"]
    top_people = sorted(
        person_summary.items(),
        key=lambda x: x[1]["videos_count"],
        reverse=True
    )[:10]

    builder = InlineKeyboardBuilder()
    for item_pid, pdata in top_people:
        icon = "✅" if item_pid in session["selected_ids"] else "👤"
        btn = f"{icon} Inson #{item_pid}  ({pdata['videos_count']} ta video)"
        builder.button(text=btn, callback_data=f"select_person_{item_pid}")
    builder.adjust(1)

    sel_count = len(session["selected_ids"])
    builder.row(InlineKeyboardButton(
        text=f"📦 Yuklab olish ({sel_count} ta inson)",
        callback_data="finish_selection"
    ))

    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception:
        pass


# ─── Yuklab olish ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "finish_selection")
async def cb_finish_selection(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in USER_SESSIONS:
        await callback.answer("⚠️ Sessiya topilmadi.", show_alert=True)
        return

    session = USER_SESSIONS[user_id]
    selected_ids = list(session["selected_ids"])

    if not selected_ids:
        await callback.answer("⚠️ Kamida bitta inson tanlang!", show_alert=True)
        return

    await callback.answer("📦 Tayyorlanmoqda...")
    msg = await callback.message.answer("📦 Tanlangan insonlarning videolari ZIP qilinmoqda...")

    work_dir     = session["work_dir"]
    out_zip_path = os.path.join(work_dir, "result.zip")

    loop = asyncio.get_running_loop()

    # Barcha ZIP lardagi mos videolarni bitta ZIP ga yig'amiz
    await loop.run_in_executor(
        None,
        _extract_from_multiple_zips,
        session["zip_paths"],
        session["clustered_pkl_path"],
        selected_ids,
        out_zip_path
    )

    if os.path.exists(out_zip_path) and os.path.getsize(out_zip_path) > 0:
        size_mb = os.path.getsize(out_zip_path) / 1024 / 1024
        result_file = FSInputFile(out_zip_path, filename="selected_person_videos.zip")
        await callback.message.answer_document(
            document=result_file,
            caption=(
                f"🎉 **Tayyor!**\n"
                f"Tanlangan insonlar: {selected_ids}\n"
                f"Fayl hajmi: {size_mb:.1f} MB"
            ),
            parse_mode="Markdown"
        )
        await msg.delete()
    else:
        await msg.edit_text("❌ Mos videolar topilmadi yoki arxivlashda xatolik bo'ldi.")

    # Sessionni tozalash
    shutil.rmtree(work_dir, ignore_errors=True)
    if user_id in USER_SESSIONS:
        del USER_SESSIONS[user_id]


def _extract_from_multiple_zips(zip_paths, clustered_pkl_path, target_ids, output_zip_path):
    """Klasterlangan ma'lumotdan mos videolarni topib, yangi ZIP ga yozadi."""
    import pickle

    with open(clustered_pkl_path, "rb") as f:
        records = pickle.load(f)

    target_set = set(target_ids)

    # zip_path -> set of zip_inner_path
    from collections import defaultdict
    zip_to_videos = defaultdict(set)
    for r in records:
        if r.get("person_id") in target_set:
            zip_to_videos[r["video_path"]].add(r["zip_inner_path"])

    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as out_zip:
        seen_names = set()
        for zip_path, video_paths in zip_to_videos.items():
            try:
                with zipfile.ZipFile(zip_path, "r") as src_zip:
                    for v_path in video_paths:
                        try:
                            data = src_zip.read(v_path)
                            base_name = os.path.basename(v_path)
                            # Nom to'qnashuvi oldini olish
                            final_name = base_name
                            counter = 1
                            while final_name in seen_names:
                                stem = Path(base_name).stem
                                ext  = Path(base_name).suffix
                                final_name = f"{stem}_{counter}{ext}"
                                counter += 1
                            seen_names.add(final_name)
                            out_zip.writestr(final_name, data)
                        except Exception as e:
                            print(f"Video nusxalashda xatolik {v_path}: {e}")
            except Exception as e:
                print(f"ZIP ochishda xatolik {zip_path}: {e}")

    return output_zip_path


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    print("🤖 Bot ishga tushdi. ZIP fayllar kutilmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

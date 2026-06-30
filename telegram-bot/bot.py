import os
import json
import logging
import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    JobQueue,
    filters,
    ContextTypes,
)
from content import STRUCTURE, DAILY_QUESTIONS
from reminders import (
    get_wife_dua,
    get_wird_reminder,
    get_adhkar_sabah_reminder,
    get_adhkar_masa_reminder,
    get_hijri_date,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── مسارات الملفات ──────────────────────────────────────────────────────────
SUBSCRIBERS_FILE = Path(__file__).parent / "subscribers.json"
QUESTION_INDEX_FILE = Path(__file__).parent / "question_index.json"


def load_subscribers() -> set:
    if SUBSCRIBERS_FILE.exists():
        try:
            data = json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8"))
            return set(data)
        except Exception:
            return set()
    return set()


def save_subscribers(subs: set):
    SUBSCRIBERS_FILE.write_text(
        json.dumps(list(subs), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_question_index() -> int:
    if QUESTION_INDEX_FILE.exists():
        try:
            data = json.loads(QUESTION_INDEX_FILE.read_text(encoding="utf-8"))
            return data.get("index", 0)
        except Exception:
            return 0
    return 0


def save_question_index(idx: int):
    QUESTION_INDEX_FILE.write_text(
        json.dumps({"index": idx}, ensure_ascii=False),
        encoding="utf-8"
    )


# ─── بناء لوحة المفاتيح ───────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for cat_key, cat_data in STRUCTURE.items():
        rows.append([InlineKeyboardButton(cat_data["title"], callback_data=f"CAT:{cat_key}")])
    rows.append([InlineKeyboardButton("📅 سؤال اليوم", callback_data="DAILY_Q")])
    rows.append([
        InlineKeyboardButton("🔔 اشترك في التذكيرات", callback_data="SUBSCRIBE"),
        InlineKeyboardButton("🔕 إلغاء الاشتراك", callback_data="UNSUBSCRIBE"),
    ])
    return InlineKeyboardMarkup(rows)


def topics_keyboard(cat_key: str) -> InlineKeyboardMarkup:
    cat = STRUCTURE[cat_key]
    rows = []
    for topic_key, topic_data in cat["topics"].items():
        rows.append([
            InlineKeyboardButton(topic_data["title"], callback_data=f"TOPIC:{cat_key}:{topic_key}")
        ])
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")])
    return InlineKeyboardMarkup(rows)


def subtopics_keyboard(cat_key: str, topic_key: str) -> InlineKeyboardMarkup:
    topic = STRUCTURE[cat_key]["topics"][topic_key]
    rows = []
    for sub_key, sub_data in topic["subtopics"].items():
        rows.append([
            InlineKeyboardButton(sub_data["title"], callback_data=f"SUB:{cat_key}:{topic_key}:{sub_key}")
        ])
    rows.append([
        InlineKeyboardButton("🔙 رجوع", callback_data=f"CAT:{cat_key}"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN"),
    ])
    return InlineKeyboardMarkup(rows)


def back_to_topic_keyboard(cat_key: str, topic_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع للأقسام الفرعية", callback_data=f"TOPIC:{cat_key}:{topic_key}")],
        [
            InlineKeyboardButton("📂 القسم", callback_data=f"CAT:{cat_key}"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN"),
        ],
    ])


# ─── المعالجات ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name if user else "أخي / أختي"
    hijri = get_hijri_date()
    welcome = (
        f"السلام عليكم ورحمة الله وبركاته 🌿\n\n"
        f"📅 *{hijri}*\n\n"
        f"مرحباً يا *{name}* في بوت *العلم الشرعي للموحدين* 📚\n\n"
        "هذا البوت جُمع فيه ما يحتاجه الأخ والأخت الموحدة من:\n"
        "• 📗 العقيدة الصحيحة والتوحيد الخالص\n"
        "• 📘 الفقه والعبادات بالتفصيل\n"
        "• 🌸 علوم المرأة المسلمة كاملة\n"
        "• 🔵 أحكام الرجل المسلم\n"
        "• 💎 تزكية النفس والأخلاق\n"
        "• 📿 الأذكار والأدعية المأثورة\n"
        "• 📖 القرآن وعلومه\n"
        "• 📜 الحديث النبوي والسيرة\n"
        "• 🌟 قصص الصحابة والصحابيات\n"
        "• 📅 سؤال ديني يومي + تذكيرات يومية\n\n"
        "اختر من القائمة 👇"
    )
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *الأوامر المتاحة:*\n\n"
        "/start — القائمة الرئيسية\n"
        "/help — المساعدة\n"
        "/search <كلمة> — البحث في المحتوى\n"
        "/subscribe — الاشتراك في التذكيرات اليومية\n"
        "/unsubscribe — إلغاء الاشتراك\n"
        "/daily — سؤال اليوم الآن\n"
        "/wird — ورد القرآن اليومي\n"
        "/dua — دعاء المرأة الصابرة\n"
        "/stats — إحصائيات البوت\n\n"
        "📅 *التذكيرات اليومية للمشتركين:*\n"
        "🌅 06:00 — الورد القرآني اليومي\n"
        "🤲 06:30 — تذكير أذكار الصباح\n"
        "❓ 10:00 — سؤال شرعي يومي\n"
        "🌆 17:30 — تذكير أذكار المساء\n"
        "🌙 21:00 — دعاء المرأة الصابرة\n"
        "_(التوقيت بتوقيت الجزائر)_\n\n"
        "💡 يمكنك أيضاً كتابة أي كلمة مباشرةً للبحث التلقائي."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = load_subscribers()
    if user_id in subs:
        await update.message.reply_text("✅ أنت مشترك بالفعل في التذكيرات اليومية!")
        return
    subs.add(user_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "🔔 *تم الاشتراك بنجاح!*\n\n"
        "ستصلك يومياً إن شاء الله:\n"
        "🌅 الورد القرآني — 6:00 صباحاً\n"
        "🤲 أذكار الصباح — 6:30 صباحاً\n"
        "❓ سؤال شرعي — 10:00 صباحاً\n"
        "🌆 أذكار المساء — 5:30 مساءً\n"
        "🌙 دعاء المرأة الصابرة — 9:00 مساءً\n"
        "_(بتوقيت الجزائر)_\n\n"
        "لإلغاء الاشتراك: /unsubscribe",
        parse_mode="Markdown"
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = load_subscribers()
    if user_id not in subs:
        await update.message.reply_text("أنت لست مشتركاً حالياً.")
        return
    subs.discard(user_id)
    save_subscribers(subs)
    await update.message.reply_text("🔕 تم إلغاء اشتراكك. يمكنك الاشتراك مجدداً بـ /subscribe")


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = load_question_index()
    q = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    text = (
        f"📅 *سؤال اليوم*\n\n"
        f"❓ *{q['q']}*\n\n"
        f"{q['a']}\n\n"
        "─────────────────\n"
        "اشترك في التذكيرات اليومية: /subscribe"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def wird_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day_of_year = datetime.date.today().timetuple().tm_yday
    text = get_wird_reminder(day_of_year)
    await update.message.reply_text(text, parse_mode="Markdown")


async def dua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_wife_dua()
    await update.message.reply_text(text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    total_content = sum(
        len(topic["subtopics"])
        for cat in STRUCTURE.values()
        for topic in cat["topics"].values()
    )
    text = (
        "📊 *إحصائيات البوت*\n\n"
        f"👥 المشتركون في التذكيرات: *{len(subs)}*\n"
        f"📚 عدد الأقسام الرئيسية: *{len(STRUCTURE)}*\n"
        f"📋 عدد المواضيع الفرعية: *{total_content}*\n"
        f"❓ عدد أسئلة اليوم المتوفرة: *{len(DAILY_QUESTIONS)}*\n"
        f"📅 {get_hijri_date()}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(
            "أرسل الكلمة بعد الأمر مثل:\n`/search الحيض`",
            parse_mode="Markdown"
        )
        return
    await _do_search(update, query)


async def _do_search(update: Update, query: str):
    results = []
    for cat_key, cat in STRUCTURE.items():
        for topic_key, topic in cat["topics"].items():
            for sub_key, sub in topic["subtopics"].items():
                if query in sub["title"] or query in sub["text"]:
                    results.append((sub["title"], f"SUB:{cat_key}:{topic_key}:{sub_key}"))
    if not results:
        await update.message.reply_text(f"لم أجد نتائج لـ «{query}»، جرّب كلمة أخرى 🔍")
        return
    keyboard = [[InlineKeyboardButton(t, callback_data=d)] for t, d in results[:10]]
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")])
    await update.message.reply_text(
        f"🔍 نتائج «{query}» ({len(results)} نتيجة):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "MAIN":
        await query.edit_message_text(
            f"🏠 *القائمة الرئيسية*\n📅 {get_hijri_date()}\n\nاختر القسم:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

    elif data == "DAILY_Q":
        idx = load_question_index()
        q = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
        text = (
            f"📅 *سؤال اليوم*\n\n"
            f"❓ *{q['q']}*\n\n"
            f"{q['a']}\n\n"
            "─────────────────\n"
            "اشترك في التذكيرات اليومية عبر الزر أدناه 👇"
        )
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك", callback_data="SUBSCRIBE")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")],
            ])
        )

    elif data == "SUBSCRIBE":
        user_id = query.from_user.id
        subs = load_subscribers()
        if user_id in subs:
            await query.answer("✅ أنت مشترك بالفعل!", show_alert=True)
        else:
            subs.add(user_id)
            save_subscribers(subs)
            await query.answer("🔔 تم الاشتراك! ستصلك تذكيرات يومية إن شاء الله", show_alert=True)

    elif data == "UNSUBSCRIBE":
        user_id = query.from_user.id
        subs = load_subscribers()
        if user_id not in subs:
            await query.answer("أنت لست مشتركاً.", show_alert=True)
        else:
            subs.discard(user_id)
            save_subscribers(subs)
            await query.answer("🔕 تم إلغاء الاشتراك.", show_alert=True)

    elif data.startswith("CAT:"):
        cat_key = data[4:]
        if cat_key not in STRUCTURE:
            return
        cat = STRUCTURE[cat_key]
        await query.edit_message_text(
            f"*{cat['title']}*\n\nاختر الموضوع:",
            parse_mode="Markdown",
            reply_markup=topics_keyboard(cat_key)
        )

    elif data.startswith("TOPIC:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            return
        cat_key, topic_key = parts[1], parts[2]
        if cat_key not in STRUCTURE or topic_key not in STRUCTURE[cat_key]["topics"]:
            return
        topic = STRUCTURE[cat_key]["topics"][topic_key]
        await query.edit_message_text(
            f"📂 *{topic['title']}*\n\nاختر القسم الفرعي:",
            parse_mode="Markdown",
            reply_markup=subtopics_keyboard(cat_key, topic_key)
        )

    elif data.startswith("SUB:"):
        parts = data.split(":", 3)
        if len(parts) < 4:
            return
        cat_key, topic_key, sub_key = parts[1], parts[2], parts[3]
        try:
            sub = STRUCTURE[cat_key]["topics"][topic_key]["subtopics"][sub_key]
        except KeyError:
            return
        await query.edit_message_text(
            sub["text"],
            parse_mode="Markdown",
            reply_markup=back_to_topic_keyboard(cat_key, topic_key)
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text(
            "اكتب كلمة للبحث أو اضغط /start للقائمة 🌿"
        )
        return
    await _do_search(update, text)


# ─── وظائف الإرسال الجماعي ────────────────────────────────────────────────────

async def _broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    subs = load_subscribers()
    if not subs:
        return
    failed = []
    for user_id in list(subs):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"فشل الإرسال لـ {user_id}: {e}")
            failed.append(user_id)
    if failed:
        save_subscribers(subs - set(failed))


async def send_daily_question(context: ContextTypes.DEFAULT_TYPE):
    idx = load_question_index()
    q = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    save_question_index(idx + 1)
    today = datetime.date.today().strftime("%A %d/%m/%Y")
    text = (
        f"🌅 *السؤال اليومي — {today}*\n"
        f"📅 {get_hijri_date()}\n\n"
        f"❓ *{q['q']}*\n\n"
        f"{q['a']}\n\n"
        "─────────────────\n"
        "📚 للمزيد من العلم الشرعي اضغط /start"
    )
    await _broadcast(context, text)


async def send_wird_reminder(context: ContextTypes.DEFAULT_TYPE):
    day_of_year = datetime.date.today().timetuple().tm_yday
    text = get_wird_reminder(day_of_year)
    await _broadcast(context, text)


async def send_adhkar_sabah(context: ContextTypes.DEFAULT_TYPE):
    text = get_adhkar_sabah_reminder()
    await _broadcast(context, text)


async def send_adhkar_masa(context: ContextTypes.DEFAULT_TYPE):
    text = get_adhkar_masa_reminder()
    await _broadcast(context, text)


async def send_wife_dua(context: ContextTypes.DEFAULT_TYPE):
    text = get_wife_dua()
    await _broadcast(context, text)


# ─── التشغيل ─────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("wird", wird_command))
    app.add_handler(CommandHandler("dua", dua_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    job_queue: JobQueue = app.job_queue

    # الجزائر UTC+1 — نطرح 1 ساعة للحصول على UTC
    # 🌅 الورد القرآني — 6:00 صباحاً الجزائر = 5:00 UTC
    job_queue.run_daily(
        send_wird_reminder,
        time=datetime.time(hour=5, minute=0, second=0),
        name="wird_reminder"
    )
    # 🤲 أذكار الصباح — 6:30 الجزائر = 5:30 UTC
    job_queue.run_daily(
        send_adhkar_sabah,
        time=datetime.time(hour=5, minute=30, second=0),
        name="adhkar_sabah"
    )
    # ❓ السؤال اليومي — 10:00 الجزائر = 9:00 UTC
    job_queue.run_daily(
        send_daily_question,
        time=datetime.time(hour=9, minute=0, second=0),
        name="daily_question"
    )
    # 🌆 أذكار المساء — 17:30 الجزائر = 16:30 UTC
    job_queue.run_daily(
        send_adhkar_masa,
        time=datetime.time(hour=16, minute=30, second=0),
        name="adhkar_masa"
    )
    # 🌙 دعاء المرأة الصابرة — 21:00 الجزائر = 20:00 UTC
    job_queue.run_daily(
        send_wife_dua,
        time=datetime.time(hour=20, minute=0, second=0),
        name="wife_dua"
    )

    logger.info("✅ بوت العلم الشرعي يعمل مع التذكيرات الخمسة اليومية...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

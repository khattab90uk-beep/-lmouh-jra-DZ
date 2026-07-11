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
from content import STRUCTURE, DAILY_QUESTIONS, QUIZ_QUESTIONS
from reminders import (
    get_wife_dua,
    get_wird_reminder,
    get_adhkar_sabah_reminder,
    get_adhkar_masa_reminder,
    get_qiyam_reminder,
    get_hijri_date,
)
from prayer_times import compute_prayer_times, prayer_reminder_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── مسارات الملفات ──────────────────────────────────────────────────────────
SUBSCRIBERS_FILE   = Path(__file__).parent / "subscribers.json"
QUESTION_INDEX_FILE = Path(__file__).parent / "question_index.json"
ALL_USERS_FILE     = Path(__file__).parent / "all_users.json"   # كل من استخدم البوت


# ═══════════════════════════════════════════════════════════════════
# إدارة المستخدمين
# ═══════════════════════════════════════════════════════════════════

def load_all_users() -> set:
    """جميع المستخدمين الذين فتحوا البوت — يتلقون التذكيرات الإلزامية."""
    if ALL_USERS_FILE.exists():
        try:
            return set(json.loads(ALL_USERS_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_all_users(users: set):
    ALL_USERS_FILE.write_text(
        json.dumps(list(users), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def register_user(user_id: int):
    """سجّل المستخدم في قائمة الكل تلقائياً."""
    users = load_all_users()
    if user_id not in users:
        users.add(user_id)
        save_all_users(users)


def load_subscribers() -> set:
    """المشتركون في السؤال اليومي ودعاء المرأة الصابرة فقط."""
    if SUBSCRIBERS_FILE.exists():
        try:
            return set(json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8")))
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
            return json.loads(QUESTION_INDEX_FILE.read_text(encoding="utf-8")).get("index", 0)
        except Exception:
            return 0
    return 0


def save_question_index(idx: int):
    QUESTION_INDEX_FILE.write_text(
        json.dumps({"index": idx}, ensure_ascii=False),
        encoding="utf-8"
    )


# ═══════════════════════════════════════════════════════════════════
# الإرسال الجماعي
# ═══════════════════════════════════════════════════════════════════

async def _broadcast_all(bot, text: str):
    """أرسل لجميع المستخدمين — التذكيرات الإلزامية."""
    users = load_all_users()
    if not users:
        return
    failed = []
    for uid in list(users):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"فشل الإرسال لـ {uid}: {e}")
            failed.append(uid)
    if failed:
        save_all_users(users - set(failed))


async def _broadcast_subscribers(bot, text: str):
    """أرسل للمشتركين فقط — السؤال اليومي ودعاء المرأة."""
    subs = load_subscribers()
    if not subs:
        return
    failed = []
    for uid in list(subs):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"فشل الإرسال لـ {uid}: {e}")
            failed.append(uid)
    if failed:
        save_subscribers(subs - set(failed))


# ═══════════════════════════════════════════════════════════════════
# لوحات المفاتيح
# ═══════════════════════════════════════════════════════════════════

def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for cat_key, cat_data in STRUCTURE.items():
        rows.append([InlineKeyboardButton(cat_data["title"], callback_data=f"CAT:{cat_key}")])
    rows.append([InlineKeyboardButton("📅 سؤال اليوم", callback_data="DAILY_Q")])
    rows.append([InlineKeyboardButton("🕌 مواقيت صلاة الجزائر اليوم", callback_data="PRAYER_TIMES")])
    rows.append([
        InlineKeyboardButton("🔔 اشترك في السؤال اليومي", callback_data="SUBSCRIBE"),
        InlineKeyboardButton("🔕 إلغاء", callback_data="UNSUBSCRIBE"),
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


def quiz_keyboard(idx: int) -> InlineKeyboardMarkup:
    q = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(q["choices"][0], callback_data=f"QUIZ_ANS:{idx}:0")],
        [InlineKeyboardButton(q["choices"][1], callback_data=f"QUIZ_ANS:{idx}:1")],
        [InlineKeyboardButton("💡 مساعدة — اعطني تلميح", callback_data=f"QUIZ_HINT:{idx}")],
    ])


def back_to_topic_keyboard(cat_key: str, topic_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع للأقسام الفرعية", callback_data=f"TOPIC:{cat_key}:{topic_key}")],
        [
            InlineKeyboardButton("📂 القسم", callback_data=f"CAT:{cat_key}"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN"),
        ],
    ])


# ═══════════════════════════════════════════════════════════════════
# الأوامر الأساسية
# ═══════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)          # تسجيل تلقائي إلزامي
    name  = user.first_name if user else "أخي / أختي"
    hijri = get_hijri_date()
    times = compute_prayer_times(datetime.date.today())
    welcome = (
        f"السلام عليكم ورحمة الله وبركاته 🌿\n\n"
        f"📅 *{hijri}*\n\n"
        f"مرحباً يا *{name}* في بوت *العلم الشرعي للموحدين* 📚\n\n"
        "• 📗 العقيدة والتوحيد\n"
        "• 📘 الفقه والعبادات\n"
        "• 🌸 أحكام المرأة المسلمة\n"
        "• 🔵 أحكام الرجل المسلم\n"
        "• 💎 التزكية والأخلاق\n"
        "• 📿 الأذكار والأدعية\n"
        "• 📖 القرآن الكريم\n"
        "• 📜 الحديث والسيرة\n"
        "• 🌟 قصص الصحابة والصحابيات\n\n"
        f"🕌 *مواقيت اليوم — الجزائر:*\n"
        f"فجر {times['fajr'].strftime('%H:%M')} | ظهر {times['dhuhr'].strftime('%H:%M')} | "
        f"عصر {times['asr'].strftime('%H:%M')} | مغرب {times['maghrib'].strftime('%H:%M')} | "
        f"عشاء {times['isha'].strftime('%H:%M')}\n\n"
        "اختر من القائمة 👇"
    )
    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    text = (
        "📋 *الأوامر المتاحة:*\n\n"
        "/start — القائمة الرئيسية + مواقيت اليوم\n"
        "/prayers — مواقيت الصلاة الآن\n"
        "/wird — الورد القرآني اليومي\n"
        "/dua — دعاء المرأة الصابرة\n"
        "/daily — سؤال اليوم\n"
        "/stats — الإحصائيات\n"
        "/search <كلمة> — البحث\n"
        "/subscribe — الاشتراك في السؤال اليومي\n"
        "/unsubscribe — إلغاء الاشتراك\n\n"
        "📲 *التذكيرات الإلزامية لكل مستخدم:*\n"
        "🌅 06:00 — الورد القرآني\n"
        "🤲 06:30 — أذكار الصباح\n"
        "🌆 17:30 — أذكار المساء\n"
        "🌙 02:25 — قيام الليل (الثلث الأخير)\n"
        "🕌 تنبيه قبل كل صلاة بـ 10 دقائق\n\n"
        "📩 *للمشتركين فقط:*\n"
        "❓ 10:00 — سؤال شرعي يومي\n"
        "🌙 21:00 — دعاء المرأة الصابرة\n\n"
        "_(أوقات الجزائر UTC+1)_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def prayers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    hijri = get_hijri_date()
    times = compute_prayer_times(datetime.date.today())
    text = (
        f"🕌 *مواقيت الصلاة — الجزائر*\n"
        f"📅 {hijri}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌙 الفجر   ← *{times['fajr'].strftime('%H:%M')}*\n"
        f"🌤️ الشروق ← *{times['sunrise'].strftime('%H:%M')}*\n"
        f"☀️ الظهر  ← *{times['dhuhr'].strftime('%H:%M')}*\n"
        f"🌤️ العصر  ← *{times['asr'].strftime('%H:%M')}*\n"
        f"🌅 المغرب ← *{times['maghrib'].strftime('%H:%M')}*\n"
        f"🌙 العشاء  ← *{times['isha'].strftime('%H:%M')}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_الحساب: طريقة رابطة العالم الإسلامي — مدينة الجزائر_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    subs = load_subscribers()
    if user_id in subs:
        await update.message.reply_text("✅ أنت مشترك بالفعل في السؤال اليومي!")
        return
    subs.add(user_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "🔔 *تم الاشتراك في السؤال اليومي!*\n\n"
        "ستصلك إضافةً للتذكيرات الإلزامية:\n"
        "❓ سؤال شرعي — 10:00 صباحاً\n"
        "🌙 دعاء المرأة الصابرة — 9:00 مساءً\n\n"
        "لإلغاء الاشتراك: /unsubscribe",
        parse_mode="Markdown"
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = load_subscribers()
    if user_id not in subs:
        await update.message.reply_text(
            "أنت لست مشتركاً في السؤال اليومي.\n"
            "⚠️ التذكيرات الإلزامية (الصلوات، الأذكار، القيام) تصلك دائماً."
        )
        return
    subs.discard(user_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "🔕 تم إلغاء اشتراكك في السؤال اليومي.\n"
        "⚠️ التذكيرات الإلزامية (الصلوات، الأذكار، القيام) ستظل تصلك."
    )


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    idx = load_question_index()
    q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    text = (
        f"📅 *سؤال اليوم*\n\n"
        f"❓ *{q['q']}*\n\n"
        f"{q['a']}\n\n"
        "─────────────────\n"
        "اشترك في السؤال اليومي: /subscribe"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def wird_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    day = datetime.date.today().timetuple().tm_yday
    await update.message.reply_text(get_wird_reminder(day), parse_mode="Markdown")


async def dua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    await update.message.reply_text(get_wife_dua(), parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    all_users = load_all_users()
    subs      = load_subscribers()
    total     = sum(
        len(t["subtopics"])
        for cat in STRUCTURE.values()
        for t in cat["topics"].values()
    )
    text = (
        "📊 *إحصائيات البوت*\n\n"
        f"👤 إجمالي المستخدمين: *{len(all_users)}*\n"
        f"🔔 مشتركو السؤال اليومي: *{len(subs)}*\n"
        f"📚 الأقسام الرئيسية: *{len(STRUCTURE)}*\n"
        f"📋 الأقسام الفرعية: *{total}*\n"
        f"❓ أسئلة اليوم المتوفرة: *{len(DAILY_QUESTIONS)}*\n"
        f"📅 {get_hijri_date()}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(
            "أرسل الكلمة بعد الأمر مثل:\n`/search الحيض`", parse_mode="Markdown"
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


# ═══════════════════════════════════════════════════════════════════
# معالج الأزرار
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    register_user(query.from_user.id)

    if data == "MAIN":
        await query.edit_message_text(
            f"🏠 *القائمة الرئيسية*\n📅 {get_hijri_date()}\n\nاختر القسم:",
            parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )

    elif data == "PRAYER_TIMES":
        times = compute_prayer_times(datetime.date.today())
        hijri = get_hijri_date()
        text = (
            f"🕌 *مواقيت الصلاة — الجزائر*\n📅 {hijri}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🌙 الفجر   ← *{times['fajr'].strftime('%H:%M')}*\n"
            f"🌤️ الشروق ← *{times['sunrise'].strftime('%H:%M')}*\n"
            f"☀️ الظهر  ← *{times['dhuhr'].strftime('%H:%M')}*\n"
            f"🌤️ العصر  ← *{times['asr'].strftime('%H:%M')}*\n"
            f"🌅 المغرب ← *{times['maghrib'].strftime('%H:%M')}*\n"
            f"🌙 العشاء  ← *{times['isha'].strftime('%H:%M')}*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_رابطة العالم الإسلامي — مدينة الجزائر_"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")]
            ])
        )

    elif data == "DAILY_Q":
        idx = load_question_index()
        q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
        text = (
            f"📅 *سؤال اليوم*\n\n❓ *{q['q']}*\n\n{q['a']}\n\n"
            "─────────────────\n"
            "اشترك في السؤال اليومي عبر الزر أدناه 👇"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك في السؤال اليومي", callback_data="SUBSCRIBE")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")],
            ])
        )

    elif data == "SUBSCRIBE":
        uid  = query.from_user.id
        subs = load_subscribers()
        if uid in subs:
            await query.answer("✅ أنت مشترك بالفعل!", show_alert=True)
        else:
            subs.add(uid)
            save_subscribers(subs)
            await query.answer("🔔 تم الاشتراك! ستصلك أسئلة شرعية يومياً", show_alert=True)

    elif data == "UNSUBSCRIBE":
        uid  = query.from_user.id
        subs = load_subscribers()
        if uid not in subs:
            await query.answer("أنت لست مشتركاً في السؤال اليومي.", show_alert=True)
        else:
            subs.discard(uid)
            save_subscribers(subs)
            await query.answer("🔕 تم إلغاء اشتراكك في السؤال اليومي.", show_alert=True)

    elif data.startswith("QUIZ_ANS:"):
        parts = data.split(":")
        idx, choice = int(parts[1]), int(parts[2])
        q = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
        if choice == q["correct"]:
            result_text = q["explanation"]
        else:
            result_text = q["wrong"]
        await query.edit_message_text(
            f"📅 {get_hijri_date()}\n\n{result_text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")]
            ])
        )

    elif data.startswith("QUIZ_HINT:"):
        idx = int(data.split(":")[1])
        q   = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
        await query.answer(q["hint"], show_alert=True)

    elif data.startswith("CAT:"):
        cat_key = data[4:]
        if cat_key not in STRUCTURE:
            return
        cat = STRUCTURE[cat_key]
        await query.edit_message_text(
            f"*{cat['title']}*\n\nاختر الموضوع:",
            parse_mode="Markdown", reply_markup=topics_keyboard(cat_key)
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
            parse_mode="Markdown", reply_markup=subtopics_keyboard(cat_key, topic_key)
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
            sub["text"], parse_mode="Markdown",
            reply_markup=back_to_topic_keyboard(cat_key, topic_key)
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text("اكتب كلمة للبحث أو اضغط /start للقائمة 🌿")
        return
    await _do_search(update, text)


# ═══════════════════════════════════════════════════════════════════
# وظائف الجدولة اليومية
# ═══════════════════════════════════════════════════════════════════

async def job_wird(context: ContextTypes.DEFAULT_TYPE):
    day = datetime.date.today().timetuple().tm_yday
    await _broadcast_all(context.bot, get_wird_reminder(day))


async def job_adhkar_sabah(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_adhkar_sabah_reminder())


async def job_adhkar_masa(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_adhkar_masa_reminder())


async def job_qiyam(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_qiyam_reminder())


async def job_daily_question(context: ContextTypes.DEFAULT_TYPE):
    idx = load_question_index()
    q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    save_question_index(idx + 1)
    today = datetime.date.today().strftime("%A %d/%m/%Y")
    text = (
        f"🌅 *السؤال اليومي — {today}*\n"
        f"📅 {get_hijri_date()}\n\n"
        f"❓ *{q['q']}*\n\n{q['a']}\n\n"
        "─────────────────\n"
        "📚 للمزيد اضغط /start"
    )
    await _broadcast_subscribers(context.bot, text)


async def job_wife_dua(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_subscribers(context.bot, get_wife_dua())


async def job_daily_quiz(context: ContextTypes.DEFAULT_TYPE):
    """يُرسل سؤال الاختبار التفاعلي للمشتركين — 08:00 الجزائر."""
    idx = load_question_index() % len(QUIZ_QUESTIONS)
    q   = QUIZ_QUESTIONS[idx]
    hijri = get_hijri_date()
    text = (
        f"🧠 *اختبار اليوم*\n"
        f"📅 {hijri}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{q['q']}\n\n"
        "_اختر الجواب الصحيح 👇_"
    )
    subs = load_subscribers()
    if not subs:
        return
    failed = []
    for uid in list(subs):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode="Markdown",
                reply_markup=quiz_keyboard(idx),
            )
        except Exception as e:
            logger.warning(f"فشل إرسال الاختبار لـ {uid}: {e}")
            failed.append(uid)
    if failed:
        save_subscribers(subs - set(failed))


# ─── إرسال تنبيه صلاة واحدة ──────────────────────────────────────
async def _send_prayer_alert(context: ContextTypes.DEFAULT_TYPE):
    """يُستدعى من run_once — data هو اسم الصلاة."""
    prayer_key  = context.job.data["prayer"]
    prayer_time = context.job.data["time"]
    hijri       = get_hijri_date()
    text = prayer_reminder_text(prayer_key, prayer_time, hijri)
    await _broadcast_all(context.bot, text)


# ─── إعادة جدولة مواقيت الصلاة كل يوم ──────────────────────────
async def job_schedule_prayers(context: ContextTypes.DEFAULT_TYPE):
    """
    يعمل يومياً عند 00:05 UTC (01:05 الجزائر).
    يحسب مواقيت اليوم ويجدول run_once لكل صلاة.
    """
    today = datetime.date.today()
    times = compute_prayer_times(today)
    now   = datetime.datetime.utcnow()

    for prayer_key in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
        pt = times[prayer_key]
        # تحويل وقت الصلاة (الجزائر UTC+1) إلى UTC
        utc_h = (pt.hour - 1) % 24
        prayer_utc = datetime.datetime(
            today.year, today.month, today.day,
            utc_h, pt.minute, 0
        )
        # التنبيه 10 دقائق قبل الصلاة
        alert_utc = prayer_utc - datetime.timedelta(minutes=10)

        if alert_utc > now:
            delay = (alert_utc - now).total_seconds()
            context.job_queue.run_once(
                _send_prayer_alert,
                when=delay,
                data={"prayer": prayer_key, "time": pt},
                name=f"prayer_{prayer_key}_{today.isoformat()}"
            )
            logger.info(f"⏰ جُدول تنبيه {prayer_key} الساعة {pt.strftime('%H:%M')} الجزائر")


# ═══════════════════════════════════════════════════════════════════
# التشغيل
# ═══════════════════════════════════════════════════════════════════

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

    app = Application.builder().token(token).build()

    # ─── الأوامر
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("prayers",     prayers_command))
    app.add_handler(CommandHandler("subscribe",   subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("daily",       daily_command))
    app.add_handler(CommandHandler("wird",        wird_command))
    app.add_handler(CommandHandler("dua",         dua_command))
    app.add_handler(CommandHandler("stats",       stats_command))
    app.add_handler(CommandHandler("search",      search_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    jq: JobQueue = app.job_queue

    # ══ تذكيرات إلزامية لكل المستخدمين (UTC = الجزائر - 1 ساعة) ══

    # 🌅 الورد القرآني — 06:00 الجزائر = 05:00 UTC
    jq.run_daily(job_wird,         datetime.time(5,  0), name="wird")
    # 🤲 أذكار الصباح — 06:30 الجزائر = 05:30 UTC
    jq.run_daily(job_adhkar_sabah, datetime.time(5, 30), name="adhkar_sabah")
    # 🌆 أذكار المساء — 17:30 الجزائر = 16:30 UTC
    jq.run_daily(job_adhkar_masa,  datetime.time(16, 30), name="adhkar_masa")
    # 🌙 قيام الليل — 02:25 الجزائر = 01:25 UTC
    jq.run_daily(job_qiyam,        datetime.time(1, 25), name="qiyam")

    # 🕌 جدولة مواقيت الصلاة — تُعاد يومياً الساعة 00:05 UTC
    jq.run_daily(job_schedule_prayers, datetime.time(0, 5), name="schedule_prayers")

    # ══ تذكيرات للمشتركين فقط ══

    # 🧠 اختبار تفاعلي — 08:00 الجزائر = 07:00 UTC
    jq.run_daily(job_daily_quiz,     datetime.time(7,  0), name="daily_quiz")
    # ❓ السؤال اليومي — 10:00 الجزائر = 09:00 UTC
    jq.run_daily(job_daily_question, datetime.time(9,  0), name="daily_question")
    # 🌙 دعاء زوجة المجاهد — 21:00 الجزائر = 20:00 UTC
    jq.run_daily(job_wife_dua,       datetime.time(20, 0), name="wife_dua")

    # ── جدول صلوات اليوم الأول فور الإقلاع (بعد 10 ثوانٍ)
    jq.run_once(job_schedule_prayers, when=10, name="schedule_prayers_startup")

    logger.info("✅ البوت يعمل — 7 تذكيرات يومية + مواقيت الصلوات الخمس")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import os
import json
import logging
import datetime
from pathlib import Path
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
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
    get_owner_dua,
    OWNER_DUA,
)
from prayer_times import (
    compute_prayer_times,
    compute_prayer_times_for_wilaya,
    prayer_reminder_text,
    WILAYAS,
    DEFAULT_WILAYA,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── مسارات الملفات ──────────────────────────────────────────────────────────
SUBSCRIBERS_FILE    = Path(__file__).parent / "subscribers.json"
QUESTION_INDEX_FILE = Path(__file__).parent / "question_index.json"
ALL_USERS_FILE      = Path(__file__).parent / "all_users.json"
USER_WILAYAS_FILE   = Path(__file__).parent / "user_wilayas.json"


# ═══════════════════════════════════════════════════════════════════
# إدارة المستخدمين
# ═══════════════════════════════════════════════════════════════════

def load_all_users() -> set:
    if ALL_USERS_FILE.exists():
        try:
            return set(json.loads(ALL_USERS_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_all_users(users: set):
    ALL_USERS_FILE.write_text(
        json.dumps(list(users), ensure_ascii=False, indent=2), encoding="utf-8"
    )

def register_user(user_id: int):
    users = load_all_users()
    if user_id not in users:
        users.add(user_id)
        save_all_users(users)

def load_subscribers() -> set:
    if SUBSCRIBERS_FILE.exists():
        try:
            return set(json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_subscribers(subs: set):
    SUBSCRIBERS_FILE.write_text(
        json.dumps(list(subs), ensure_ascii=False, indent=2), encoding="utf-8"
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
        json.dumps({"index": idx}, ensure_ascii=False), encoding="utf-8"
    )

# ─── ولايات المستخدمين ───────────────────────────────────────────
def load_user_wilayas() -> dict:
    """يُعيد dict: {str(user_id): wilaya_key}"""
    if USER_WILAYAS_FILE.exists():
        try:
            return json.loads(USER_WILAYAS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_user_wilayas(data: dict):
    USER_WILAYAS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def get_user_wilaya(user_id: int) -> str:
    data = load_user_wilayas()
    return data.get(str(user_id), DEFAULT_WILAYA)

def set_user_wilaya(user_id: int, wilaya_key: str):
    data = load_user_wilayas()
    data[str(user_id)] = wilaya_key
    save_user_wilayas(data)


# ═══════════════════════════════════════════════════════════════════
# الإرسال الجماعي
# ═══════════════════════════════════════════════════════════════════

async def _broadcast_all(bot, text: str):
    users = load_all_users()
    if not users:
        return
    failed = []
    for uid in list(users):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"broadcast_all fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_all_users(users - set(failed))

async def _broadcast_subscribers(bot, text: str):
    subs = load_subscribers()
    if not subs:
        return
    failed = []
    for uid in list(subs):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"broadcast_sub fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_subscribers(subs - set(failed))


# ═══════════════════════════════════════════════════════════════════
# لوحات المفاتيح
# ═══════════════════════════════════════════════════════════════════

# ─── خريطة أزرار القائمة الرئيسية ───────────────────────────────
# نص الزر → callback_data (يعالجه message_handler)
REPLY_BUTTONS: dict[str, str] = {}

def _build_reply_buttons():
    for cat_key, cat_data in STRUCTURE.items():
        REPLY_BUTTONS[cat_data["title"]] = f"CAT:{cat_key}"
    REPLY_BUTTONS["📅 سؤال اليوم"]              = "DAILY_Q"
    REPLY_BUTTONS["🗺️ اختر ولايتك"]             = "WILAYA_MENU"
    REPLY_BUTTONS["🕌 مواقيت الصلاة"]           = "PRAYERS"
    REPLY_BUTTONS["📊 إحصائيات"]                = "STATS"
    REPLY_BUTTONS["🔔 اشترك"]                   = "SUBSCRIBE"
    REPLY_BUTTONS["🔕 إلغاء الاشتراك"]          = "UNSUBSCRIBE"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """القائمة الرئيسية الدائمة أسفل الشاشة — تظهر/تختفي بزر المربع."""
    cats = list(STRUCTURE.values())
    rows = []
    for i in range(0, len(cats), 2):
        row = [cats[i]["title"]]
        if i + 1 < len(cats):
            row.append(cats[i + 1]["title"])
        rows.append(row)
    rows.append(["📅 سؤال اليوم",     "🗺️ اختر ولايتك"])
    rows.append(["🕌 مواقيت الصلاة",  "📊 إحصائيات"])
    rows.append(["🔔 اشترك",          "🔕 إلغاء الاشتراك"])
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=False,
    )


def wilaya_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة بجميع الولايات — عمودان."""
    keys   = list(WILAYAS.keys())
    rows   = []
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i+2]:
            row.append(InlineKeyboardButton(
                WILAYAS[k]["name"], callback_data=f"SET_WILAYA:{k}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")])
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
    rows  = []
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

def quiz_keyboard(idx: int) -> InlineKeyboardMarkup:
    q = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(q["choices"][0], callback_data=f"QUIZ_ANS:{idx}:0")],
        [InlineKeyboardButton(q["choices"][1], callback_data=f"QUIZ_ANS:{idx}:1")],
        [InlineKeyboardButton("💡 مساعدة — اعطني تلميح", callback_data=f"QUIZ_HINT:{idx}")],
    ])


# ═══════════════════════════════════════════════════════════════════
# مساعد عرض مواقيت الولاية
# ═══════════════════════════════════════════════════════════════════

def _format_wilaya_times(wilaya_key: str, date: datetime.date, hijri: str) -> str:
    w     = WILAYAS.get(wilaya_key, WILAYAS[DEFAULT_WILAYA])
    times = compute_prayer_times_for_wilaya(date, wilaya_key)
    return (
        f"🕌 *مواقيت الصلاة*\n"
        f"📍 *{w['name']}*\n"
        f"📅 {hijri}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌙 الفجر   ← *{times['fajr'].strftime('%H:%M')}*\n"
        f"🌤️ الشروق ← *{times['sunrise'].strftime('%H:%M')}*\n"
        f"☀️ الظهر  ← *{times['dhuhr'].strftime('%H:%M')}*\n"
        f"🌤️ العصر  ← *{times['asr'].strftime('%H:%M')}*\n"
        f"🌅 المغرب ← *{times['maghrib'].strftime('%H:%M')}*\n"
        f"🌙 العشاء  ← *{times['isha'].strftime('%H:%M')}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_رابطة العالم الإسلامي — سيتم تنبيهك قبل كل صلاة بـ 10 دقائق_ 🌿"
    )


# ═══════════════════════════════════════════════════════════════════
# الأوامر الأساسية
# ═══════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)
    name  = user.first_name if user else "أخي / أختي"
    hijri = get_hijri_date()
    wkey  = get_user_wilaya(user.id)
    w     = WILAYAS[wkey]
    times = compute_prayer_times_for_wilaya(datetime.date.today(), wkey)
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
        f"🕌 *مواقيت اليوم — {w['name']}:*\n"
        f"فجر {times['fajr'].strftime('%H:%M')} | ظهر {times['dhuhr'].strftime('%H:%M')} | "
        f"عصر {times['asr'].strftime('%H:%M')} | مغرب {times['maghrib'].strftime('%H:%M')} | "
        f"عشاء {times['isha'].strftime('%H:%M')}\n\n"
        "اختر من القائمة 👇\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤲 اللهم اجعل هذا البوت في ميزان حسنات صاحبته\n"
        "*رَيْحَانَةُ المَغْرِبِ الأَوْسَطِ الأَنْدَلُسِيَّة* — غفر الله لها 🌿"
    )
    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=main_reply_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    text = (
        "📋 *الأوامر المتاحة:*\n\n"
        "/start — القائمة الرئيسية\n"
        "/prayers — مواقيت الصلاة لولايتك\n"
        "/wilaya — اختر ولايتك\n"
        "/wird — الورد القرآني اليومي\n"
        "/dua — دعاء زوجة المجاهد\n"
        "/daily — سؤال اليوم\n"
        "/stats — الإحصائيات\n"
        "/search <كلمة> — البحث\n"
        "/subscribe — الاشتراك في الأسئلة اليومية\n"
        "/unsubscribe — إلغاء الاشتراك\n\n"
        "📲 *التذكيرات الإلزامية:*\n"
        "🌅 06:00 — الورد القرآني\n"
        "🤲 06:30 — أذكار الصباح\n"
        "🌆 17:30 — أذكار المساء\n"
        "🌙 02:25 — قيام الليل\n"
        "🕌 قبل كل صلاة بـ10 دق — تنبيه بتوقيت ولايتك\n\n"
        "📩 *للمشتركين فقط:*\n"
        "🧠 08:00 — اختبار تفاعلي\n"
        "❓ 10:00 — سؤال شرعي\n"
        "🌙 21:00 — دعاء زوجة المجاهد"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def prayers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    uid   = update.effective_user.id
    wkey  = get_user_wilaya(uid)
    hijri = get_hijri_date()
    text  = _format_wilaya_times(wkey, datetime.date.today(), hijri)
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺️ غيّر ولايتك", callback_data="WILAYA_MENU")]
        ])
    )

async def wilaya_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    uid  = update.effective_user.id
    wkey = get_user_wilaya(uid)
    w    = WILAYAS[wkey]
    await update.message.reply_text(
        f"🗺️ *اختيار الولاية*\n\n"
        f"ولايتك الحالية: *{w['name']}*\n\n"
        "اختر ولايتك من القائمة ليصلك تنبيه الصلاة\nبتوقيتها الصحيح 👇",
        parse_mode="Markdown",
        reply_markup=wilaya_menu_keyboard()
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    subs = load_subscribers()
    if user_id in subs:
        await update.message.reply_text("✅ أنت مشترك بالفعل في الأسئلة اليومية!")
        return
    subs.add(user_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "🔔 *تم الاشتراك!*\n\n"
        "ستصلك إضافةً للتذكيرات الإلزامية:\n"
        "🧠 اختبار تفاعلي — 08:00 صباحاً\n"
        "❓ سؤال شرعي — 10:00 صباحاً\n"
        "🌙 دعاء زوجة المجاهد — 9:00 مساءً\n\n"
        "لإلغاء الاشتراك: /unsubscribe",
        parse_mode="Markdown"
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs    = load_subscribers()
    if user_id not in subs:
        await update.message.reply_text(
            "أنت لست مشتركاً.\n"
            "⚠️ التذكيرات الإلزامية والصلوات تصلك دائماً."
        )
        return
    subs.discard(user_id)
    save_subscribers(subs)
    await update.message.reply_text("🔕 تم إلغاء اشتراكك في الأسئلة اليومية.")

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    idx = load_question_index()
    q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    await update.message.reply_text(
        f"📅 *سؤال اليوم*\n\n❓ *{q['q']}*\n\n{q['a']}\n\n"
        "─────────────────\n/subscribe للأسئلة اليومية",
        parse_mode="Markdown"
    )

async def wird_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    day = datetime.date.today().timetuple().tm_yday
    await update.message.reply_text(get_wird_reminder(day), parse_mode="Markdown")

async def dua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    await update.message.reply_text(get_wife_dua(), parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    all_users   = load_all_users()
    subs        = load_subscribers()
    user_wils   = load_user_wilayas()
    total_subs  = sum(
        len(t["subtopics"])
        for cat in STRUCTURE.values()
        for t in cat["topics"].values()
    )
    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👤 إجمالي المستخدمين: *{len(all_users)}*\n"
        f"🔔 المشتركون في الأسئلة: *{len(subs)}*\n"
        f"🗺️ اختاروا ولاياتهم: *{len(user_wils)}*\n"
        f"📚 الأقسام الرئيسية: *{len(STRUCTURE)}*\n"
        f"📋 الأقسام الفرعية: *{total_subs}*\n"
        f"🧠 أسئلة الاختبار: *{len(QUIZ_QUESTIONS)}*\n"
        f"📅 {get_hijri_date()}\n",
        parse_mode="Markdown"
    )

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
    data  = query.data
    uid   = query.from_user.id
    register_user(uid)

    # ── الرئيسية ──────────────────────────────────────────────────
    if data == "MAIN":
        await query.edit_message_text(
            f"🏠 *القائمة الرئيسية*\n📅 {get_hijri_date()}\n\n"
            "استخدم الأزرار أسفل الشاشة للتنقل 👇",
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            chat_id=uid,
            text="اختر من القائمة 👇",
            reply_markup=main_reply_keyboard(),
        )

    # ── قائمة الولايات ────────────────────────────────────────────
    elif data == "WILAYA_MENU":
        wkey = get_user_wilaya(uid)
        w    = WILAYAS[wkey]
        await query.edit_message_text(
            f"🗺️ *اختر ولايتك*\n\n"
            f"ولايتك الحالية: *{w['name']}*\n\n"
            "اضغط على اسم ولايتك لتفعيل التنبيهات\nبتوقيت الصلاة الصحيح لمدينتك 👇",
            parse_mode="Markdown",
            reply_markup=wilaya_menu_keyboard()
        )

    # ── اختيار ولاية ──────────────────────────────────────────────
    elif data.startswith("SET_WILAYA:"):
        wkey = data.split(":", 1)[1]
        if wkey not in WILAYAS:
            await query.answer("ولاية غير معروفة!", show_alert=True)
            return
        set_user_wilaya(uid, wkey)
        w     = WILAYAS[wkey]
        hijri = get_hijri_date()
        times_text = _format_wilaya_times(wkey, datetime.date.today(), hijri)
        await query.edit_message_text(
            f"✅ *تم اختيار {w['name']}!*\n\n"
            f"ستصلك تنبيهات الصلاة بتوقيت ولايتك 🕌\n\n"
            f"{times_text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗺️ تغيير الولاية", callback_data="WILAYA_MENU")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")],
            ])
        )

    # ── السؤال اليومي ─────────────────────────────────────────────
    elif data == "DAILY_Q":
        idx = load_question_index()
        q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
        await query.edit_message_text(
            f"📅 *سؤال اليوم*\n\n❓ *{q['q']}*\n\n{q['a']}\n\n"
            "─────────────────\nاشترك في الأسئلة اليومية 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك في الأسئلة اليومية", callback_data="SUBSCRIBE")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")],
            ])
        )

    # ── اشتراك / إلغاء ────────────────────────────────────────────
    elif data == "SUBSCRIBE":
        subs = load_subscribers()
        if uid in subs:
            await query.answer("✅ أنت مشترك بالفعل!", show_alert=True)
        else:
            subs.add(uid)
            save_subscribers(subs)
            await query.answer("🔔 تم الاشتراك! ستصلك أسئلة وأخبار يومياً", show_alert=True)

    elif data == "UNSUBSCRIBE":
        subs = load_subscribers()
        if uid not in subs:
            await query.answer("أنت لست مشتركاً.", show_alert=True)
        else:
            subs.discard(uid)
            save_subscribers(subs)
            await query.answer("🔕 تم إلغاء اشتراكك.", show_alert=True)

    # ── اختبار تفاعلي ─────────────────────────────────────────────
    elif data.startswith("QUIZ_ANS:"):
        parts  = data.split(":")
        idx    = int(parts[1])
        choice = int(parts[2])
        q      = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
        result = q["explanation"] if choice == q["correct"] else q["wrong"]
        await query.edit_message_text(
            f"📅 {get_hijri_date()}\n\n{result}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")]
            ])
        )

    elif data.startswith("QUIZ_HINT:"):
        idx = int(data.split(":")[1])
        q   = QUIZ_QUESTIONS[idx % len(QUIZ_QUESTIONS)]
        await query.answer(q["hint"], show_alert=True)

    # ── تصفح المحتوى ──────────────────────────────────────────────
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
    uid  = update.effective_user.id
    register_user(uid)
    text = (update.message.text or "").strip()

    # ── زر من القائمة الرئيسية ReplyKeyboard ──────────────────────
    action = REPLY_BUTTONS.get(text)
    if action:
        if action.startswith("CAT:"):
            cat_key = action[4:]
            if cat_key in STRUCTURE:
                cat = STRUCTURE[cat_key]
                await update.message.reply_text(
                    f"*{cat['title']}*\n\nاختر الموضوع:",
                    parse_mode="Markdown",
                    reply_markup=topics_keyboard(cat_key),
                )
            return

        if action == "DAILY_Q":
            idx = load_question_index()
            q   = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
            await update.message.reply_text(
                f"📅 *سؤال اليوم*\n\n❓ *{q['q']}*\n\n{q['a']}\n\n"
                "─────────────────\nاشترك لتصلك الأسئلة يومياً 🔔",
                parse_mode="Markdown",
            )
            return

        if action == "WILAYA_MENU":
            wkey = get_user_wilaya(uid)
            w    = WILAYAS[wkey]
            await update.message.reply_text(
                f"🗺️ *اختر ولايتك*\n\n"
                f"ولايتك الحالية: *{w['name']}*\n\n"
                "اضغط على اسم ولايتك لتفعيل تنبيهات الصلاة 👇",
                parse_mode="Markdown",
                reply_markup=wilaya_menu_keyboard(),
            )
            return

        if action == "PRAYERS":
            wkey  = get_user_wilaya(uid)
            hijri = get_hijri_date()
            text_ = _format_wilaya_times(wkey, datetime.date.today(), hijri)
            await update.message.reply_text(
                text_, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗺️ غيّر ولايتك", callback_data="WILAYA_MENU")]
                ]),
            )
            return

        if action == "STATS":
            all_users  = load_all_users()
            subs       = load_subscribers()
            user_wils  = load_user_wilayas()
            total_subs = sum(
                len(t["subtopics"])
                for cat in STRUCTURE.values()
                for t in cat["topics"].values()
            )
            await update.message.reply_text(
                "📊 *إحصائيات البوت*\n\n"
                f"👤 إجمالي المستخدمين: *{len(all_users)}*\n"
                f"🔔 المشتركون في الأسئلة: *{len(subs)}*\n"
                f"🗺️ اختاروا ولاياتهم: *{len(user_wils)}*\n"
                f"📚 الأقسام الرئيسية: *{len(STRUCTURE)}*\n"
                f"📋 الأقسام الفرعية: *{total_subs}*\n"
                f"🧠 أسئلة الاختبار: *{len(QUIZ_QUESTIONS)}*\n"
                f"📅 {get_hijri_date()}",
                parse_mode="Markdown",
            )
            return

        if action == "SUBSCRIBE":
            subs = load_subscribers()
            if uid in subs:
                await update.message.reply_text("✅ أنت مشترك بالفعل في الأسئلة اليومية!")
            else:
                subs.add(uid)
                save_subscribers(subs)
                await update.message.reply_text(
                    "🔔 *تم الاشتراك!*\n\n"
                    "ستصلك إضافةً للتذكيرات الإلزامية:\n"
                    "🧠 اختبار تفاعلي — 08:00 صباحاً\n"
                    "❓ سؤال شرعي — 10:00 صباحاً\n"
                    "🌙 دعاء زوجة المجاهد — 9:00 مساءً\n\n"
                    "لإلغاء الاشتراك اضغط: 🔕 إلغاء الاشتراك",
                    parse_mode="Markdown",
                )
            return

        if action == "UNSUBSCRIBE":
            subs = load_subscribers()
            if uid not in subs:
                await update.message.reply_text(
                    "أنت لست مشتركاً.\n"
                    "⚠️ التذكيرات الإلزامية والصلوات تصلك دائماً."
                )
            else:
                subs.discard(uid)
                save_subscribers(subs)
                await update.message.reply_text("🔕 تم إلغاء اشتراكك في الأسئلة اليومية.")
            return

    # ── بحث نصي حر ────────────────────────────────────────────────
    if len(text) < 2:
        await update.message.reply_text("اكتب كلمة للبحث أو استخدم الأزرار أسفل الشاشة 🌿")
        return
    await _do_search(update, text)


# ═══════════════════════════════════════════════════════════════════
# وظائف الجدولة
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
    idx   = load_question_index()
    q     = DAILY_QUESTIONS[idx % len(DAILY_QUESTIONS)]
    save_question_index(idx + 1)
    today = datetime.date.today().strftime("%A %d/%m/%Y")
    text  = (
        f"🌅 *السؤال اليومي — {today}*\n"
        f"📅 {get_hijri_date()}\n\n"
        f"❓ *{q['q']}*\n\n{q['a']}\n\n"
        "─────────────────\n📚 /start للمزيد"
    )
    await _broadcast_subscribers(context.bot, text)

async def job_wife_dua(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_subscribers(context.bot, get_wife_dua())

async def job_daily_quiz(context: ContextTypes.DEFAULT_TYPE):
    idx   = load_question_index() % len(QUIZ_QUESTIONS)
    q     = QUIZ_QUESTIONS[idx]
    hijri = get_hijri_date()
    text  = (
        f"🧠 *اختبار اليوم*\n"
        f"📅 {hijri}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{q['q']}\n\n"
        "_اختر الجواب الصحيح 👇_"
    )
    subs   = load_subscribers()
    failed = []
    for uid in list(subs):
        try:
            await context.bot.send_message(
                chat_id=uid, text=text,
                parse_mode="Markdown",
                reply_markup=quiz_keyboard(idx),
            )
        except Exception as e:
            logger.warning(f"quiz fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_subscribers(subs - set(failed))


# ─── تنبيه صلاة واحدة — يُستدعى من run_once ─────────────────────

async def _send_prayer_alert(context: ContextTypes.DEFAULT_TYPE):
    """
    يُرسل تنبيه صلاة لمستخدمي ولاية معينة.
    context.job.data = {"wilaya": key, "prayer": key, "time": datetime.time}
    """
    wilaya_key  = context.job.data["wilaya"]
    prayer_key  = context.job.data["prayer"]
    prayer_time = context.job.data["time"]
    hijri       = get_hijri_date()
    w           = WILAYAS.get(wilaya_key, WILAYAS[DEFAULT_WILAYA])
    text        = prayer_reminder_text(prayer_key, prayer_time, hijri, w["name"])

    user_wilayas = load_user_wilayas()
    all_users    = load_all_users()

    if wilaya_key == DEFAULT_WILAYA:
        # مستخدمو الولاية الافتراضية + من لم يختر ولاية
        targets = {
            uid for uid in all_users
            if str(uid) not in user_wilayas or user_wilayas[str(uid)] == DEFAULT_WILAYA
        }
    else:
        targets = {
            int(uid) for uid, wk in user_wilayas.items() if wk == wilaya_key
        } & all_users

    failed = []
    for uid in targets:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"prayer alert fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_all_users(all_users - set(failed))


# ─── جدولة مواقيت الصلاة لكل الولايات يومياً ────────────────────

async def job_schedule_prayers(context: ContextTypes.DEFAULT_TYPE):
    """
    يعمل يومياً 00:05 UTC.
    يحسب مواقيت كل ولاية لها مستخدمون ويجدول run_once لكل صلاة.
    """
    today        = datetime.date.today()
    now_utc      = datetime.datetime.utcnow()
    user_wilayas = load_user_wilayas()
    all_users    = load_all_users()

    # الولايات النشطة: الافتراضية + أي ولاية اختارها مستخدم
    active = {DEFAULT_WILAYA}
    for wk in user_wilayas.values():
        if wk in WILAYAS:
            active.add(wk)

    for wkey in active:
        w     = WILAYAS[wkey]
        times = compute_prayer_times_for_wilaya(today, wkey)

        for prayer_key in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
            pt = times[prayer_key]
            # تحويل التوقيت المحلي → UTC: نطرح الفارق الزمني للولاية
            utc_h = (pt.hour - w["utc"]) % 24
            prayer_utc = datetime.datetime(
                today.year, today.month, today.day, utc_h, pt.minute, 0
            )
            alert_utc = prayer_utc - datetime.timedelta(minutes=10)

            if alert_utc > now_utc:
                delay = (alert_utc - now_utc).total_seconds()
                context.job_queue.run_once(
                    _send_prayer_alert,
                    when=delay,
                    data={"wilaya": wkey, "prayer": prayer_key, "time": pt},
                    name=f"prayer_{wkey}_{prayer_key}_{today.isoformat()}"
                )
                logger.info(f"⏰ {wkey} — {prayer_key} الساعة {pt.strftime('%H:%M')}")


# ═══════════════════════════════════════════════════════════════════
# التشغيل
# ═══════════════════════════════════════════════════════════════════

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!")

    # بناء خريطة أزرار ReplyKeyboard من STRUCTURE (بعد استيراده)
    _build_reply_buttons()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("prayers",     prayers_command))
    app.add_handler(CommandHandler("wilaya",      wilaya_command))
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

    # ══ إلزامية لكل المستخدمين ══
    jq.run_daily(job_wird,             datetime.time(5,  0),  name="wird")
    jq.run_daily(job_adhkar_sabah,     datetime.time(5,  30), name="adhkar_sabah")
    jq.run_daily(job_adhkar_masa,      datetime.time(16, 30), name="adhkar_masa")
    jq.run_daily(job_qiyam,            datetime.time(1,  25), name="qiyam")
    jq.run_daily(job_schedule_prayers, datetime.time(0,  5),  name="schedule_prayers")

    # ══ للمشتركين فقط ══
    jq.run_daily(job_daily_quiz,     datetime.time(7,  0),  name="daily_quiz")
    jq.run_daily(job_daily_question, datetime.time(9,  0),  name="daily_question")
    jq.run_daily(job_wife_dua,       datetime.time(20, 0),  name="wife_dua")

    # ── جدول صلوات اليوم فور الإقلاع
    jq.run_once(job_schedule_prayers, when=10, name="schedule_prayers_startup")

    logger.info("✅ البوت يعمل — 31 ولاية + 9 وظائف يومية")

    # ── Railway → webhook | أي بيئة ثانية → polling ────────────────
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    port           = int(os.environ.get("PORT", 0))

    if railway_domain and port:
        webhook_url = f"https://{railway_domain}/{token}"
        logger.info(f"🌐 وضع Webhook على {webhook_url} — PORT={port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("🔄 وضع Polling (تطوير)")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

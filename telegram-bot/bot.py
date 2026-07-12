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
from content import STORIES, FAWAID, REFLECTIONS
from reminders import (
    get_wife_dua,
    get_wird_reminder,
    get_adhkar_sabah_reminder,
    get_adhkar_masa_reminder,
    get_qiyam_reminder,
    get_hijri_date,
    get_hijri_history_text,
)
from prayer_times import (
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
SUBSCRIBERS_FILE   = Path(__file__).parent / "subscribers.json"
ALL_USERS_FILE     = Path(__file__).parent / "all_users.json"
USER_WILAYAS_FILE  = Path(__file__).parent / "user_wilayas.json"
CONTENT_INDEX_FILE = Path(__file__).parent / "content_index.json"


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


# ─── فهرس تدوير المحتوى (قصص / فوائد / خواطر) ───────────────────
def _load_content_index() -> dict:
    if CONTENT_INDEX_FILE.exists():
        try:
            return json.loads(CONTENT_INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_content_index(data: dict):
    CONTENT_INDEX_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def next_content_item(key: str, items: list):
    """يُعيد العنصر التالي من قائمة (دورياً) ويحفظ الفهرس الجديد."""
    data = _load_content_index()
    idx  = data.get(key, 0) % len(items)
    data[key] = (idx + 1) % len(items)
    _save_content_index(data)
    return items[idx]


# ═══════════════════════════════════════════════════════════════════
# الإرسال الجماعي
# ═══════════════════════════════════════════════════════════════════

async def _broadcast_all(bot, text: str, reply_markup=None):
    users = load_all_users()
    if not users:
        return
    failed = []
    for uid in list(users):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"broadcast_all fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_all_users(users - set(failed))

async def _broadcast_subscribers(bot, text: str, reply_markup=None):
    subs = load_subscribers()
    if not subs:
        return
    failed = []
    for uid in list(subs):
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"broadcast_sub fail {uid}: {e}")
            failed.append(uid)
    if failed:
        save_subscribers(subs - set(failed))


# ═══════════════════════════════════════════════════════════════════
# لوحات المفاتيح
# ═══════════════════════════════════════════════════════════════════

def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """القائمة الرئيسية الدائمة أسفل الشاشة — مواقيت الصلاة قسم ثابت."""
    rows = [
        ["🕌 مواقيت الصلاة",  "🗺️ اختر ولايتك"],
        ["📊 إحصائيات",       "🔔 اشترك"],
        ["🔕 إلغاء الاشتراك"],
    ]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=False,
    )

# خريطة نص الزر → معرّف الإجراء (يعالجها message_handler)
REPLY_BUTTONS: dict[str, str] = {
    "🕌 مواقيت الصلاة":  "PRAYERS",
    "🗺️ اختر ولايتك":   "WILAYA_MENU",
    "📊 إحصائيات":       "STATS",
    "🔔 اشترك":          "SUBSCRIBE",
    "🔕 إلغاء الاشتراك": "UNSUBSCRIBE",
}


def wilaya_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة بجميع الولايات — عمودان."""
    keys = list(WILAYAS.keys())
    rows = []
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i + 2]:
            row.append(InlineKeyboardButton(
                WILAYAS[k]["name"], callback_data=f"SET_WILAYA:{k}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="MAIN")])
    return InlineKeyboardMarkup(rows)


def dismiss_keyboard() -> InlineKeyboardMarkup:
    """زر يظهر أسفل تذكيرات الأذكار — يحذف الرسالة بعد قراءتها لتفادي التراكم."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قرأتها — إخفاء الرسالة", callback_data="DISMISS")]
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
        f"مرحباً يا *{name}* 📚\n\n"
        "🕌 *مواقيت الصلاة* — قسمٌ ثابت في البوت، بحسب ولايتك.\n\n"
        "وكمشترك، تصلك أيضاً:\n"
        "• 📅 التاريخ الهجري وأحداث بارزة وقعت في نفس اليوم\n"
        "• 🌟 قصص صالحين من بلاد المغرب الإسلامي وجزيرة العرب، كل نصف ساعة\n"
        "• 💎 فوائد إيمانية متنوعة، كل نصف ساعة\n"
        "• 🤍 خواطر وتدبرات، بعد كل قصة بخمس دقائق\n\n"
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
        "/stats — الإحصائيات\n"
        "/subscribe — الاشتراك في المحتوى اليومي والمتجدد\n"
        "/unsubscribe — إلغاء الاشتراك\n\n"
        "📲 *التذكيرات الإلزامية (لكل المستخدمين):*\n"
        "🌅 06:00 — الورد القرآني\n"
        "🤲 06:30 — أذكار الصباح (مع زر لإخفائها بعد القراءة)\n"
        "🌆 17:30 — أذكار المساء (مع زر لإخفائها بعد القراءة)\n"
        "🌙 02:25 — قيام الليل\n"
        "🕌 قبل كل صلاة بـ10 دقائق — تنبيه بتوقيت ولايتك\n\n"
        "📩 *للمشتركين فقط:*\n"
        "📅 08:00 — التاريخ الهجري وأحداث هذا اليوم في التاريخ الإسلامي\n"
        "🌟 كل نصف ساعة — قصة من قصص الصالحين\n"
        "💎 كل نصف ساعة — فائدة إيمانية\n"
        "🤍 بعد كل قصة بخمس دقائق — خاطرة وتدبر\n"
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
        await update.message.reply_text("✅ أنت مشترك بالفعل في المحتوى اليومي والمتجدد!")
        return
    subs.add(user_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "🔔 *تم الاشتراك!*\n\n"
        "ستصلك إضافةً للتذكيرات الإلزامية:\n"
        "📅 التاريخ الهجري وأحداث هذا اليوم — 08:00 صباحاً\n"
        "🌟 قصص صالحين من المغرب الإسلامي وجزيرة العرب — كل نصف ساعة\n"
        "💎 فوائد إيمانية — كل نصف ساعة\n"
        "🤍 خواطر وتدبرات — بعد كل قصة بخمس دقائق\n"
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
    await update.message.reply_text("🔕 تم إلغاء اشتراكك في المحتوى اليومي والمتجدد.")

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
    user_wils = load_user_wilayas()
    await update.message.reply_text(
        "📊 *إحصائيات البوت*\n\n"
        f"👤 إجمالي المستخدمين: *{len(all_users)}*\n"
        f"🔔 المشتركون في المحتوى المتجدد: *{len(subs)}*\n"
        f"🗺️ اختاروا ولاياتهم: *{len(user_wils)}*\n"
        f"🌟 قصص الصالحين المتاحة: *{len(STORIES)}*\n"
        f"💎 الفوائد الإيمانية المتاحة: *{len(FAWAID)}*\n"
        f"📅 {get_hijri_date()}\n",
        parse_mode="Markdown"
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

    # ── إخفاء تذكير الأذكار بعد قراءته ──────────────────────────────
    if data == "DISMISS":
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"dismiss delete fail {uid}: {e}")
        return

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

    # ── اشتراك / إلغاء ────────────────────────────────────────────
    elif data == "SUBSCRIBE":
        subs = load_subscribers()
        if uid in subs:
            await query.answer("✅ أنت مشترك بالفعل!", show_alert=True)
        else:
            subs.add(uid)
            save_subscribers(subs)
            await query.answer("🔔 تم الاشتراك! ستصلك قصص وفوائد وتنبيهات يومياً", show_alert=True)

    elif data == "UNSUBSCRIBE":
        subs = load_subscribers()
        if uid not in subs:
            await query.answer("أنت لست مشتركاً.", show_alert=True)
        else:
            subs.discard(uid)
            save_subscribers(subs)
            await query.answer("🔕 تم إلغاء اشتراكك.", show_alert=True)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    register_user(uid)
    text = (update.message.text or "").strip()

    action = REPLY_BUTTONS.get(text)

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

    if action == "STATS":
        all_users = load_all_users()
        subs      = load_subscribers()
        user_wils = load_user_wilayas()
        await update.message.reply_text(
            "📊 *إحصائيات البوت*\n\n"
            f"👤 إجمالي المستخدمين: *{len(all_users)}*\n"
            f"🔔 المشتركون في المحتوى المتجدد: *{len(subs)}*\n"
            f"🗺️ اختاروا ولاياتهم: *{len(user_wils)}*\n"
            f"🌟 قصص الصالحين المتاحة: *{len(STORIES)}*\n"
            f"💎 الفوائد الإيمانية المتاحة: *{len(FAWAID)}*\n"
            f"📅 {get_hijri_date()}",
            parse_mode="Markdown",
        )
        return

    if action == "SUBSCRIBE":
        subs = load_subscribers()
        if uid in subs:
            await update.message.reply_text("✅ أنت مشترك بالفعل في المحتوى المتجدد!")
        else:
            subs.add(uid)
            save_subscribers(subs)
            await update.message.reply_text(
                "🔔 *تم الاشتراك!*\n\n"
                "ستصلك إضافةً للتذكيرات الإلزامية:\n"
                "📅 التاريخ الهجري وأحداث هذا اليوم — 08:00 صباحاً\n"
                "🌟 قصص صالحين — كل نصف ساعة\n"
                "💎 فوائد إيمانية — كل نصف ساعة\n"
                "🤍 خواطر وتدبرات — بعد كل قصة بخمس دقائق\n"
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
            await update.message.reply_text("🔕 تم إلغاء اشتراكك في المحتوى المتجدد.")
        return

    # ── أي نص آخر ─────────────────────────────────────────────────
    await update.message.reply_text("استخدم الأزرار أسفل الشاشة للتنقل 👇🌿")


# ═══════════════════════════════════════════════════════════════════
# وظائف الجدولة
# ═══════════════════════════════════════════════════════════════════

async def job_wird(context: ContextTypes.DEFAULT_TYPE):
    day = datetime.date.today().timetuple().tm_yday
    await _broadcast_all(context.bot, get_wird_reminder(day))

async def job_adhkar_sabah(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_adhkar_sabah_reminder(), reply_markup=dismiss_keyboard())

async def job_adhkar_masa(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_adhkar_masa_reminder(), reply_markup=dismiss_keyboard())

async def job_qiyam(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_all(context.bot, get_qiyam_reminder())

async def job_hijri_history(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_subscribers(context.bot, get_hijri_history_text())

async def job_wife_dua(context: ContextTypes.DEFAULT_TYPE):
    await _broadcast_subscribers(context.bot, get_wife_dua())

async def job_story(context: ContextTypes.DEFAULT_TYPE):
    story = next_content_item("stories", STORIES)
    text  = f"{story['title']}\n\n{story['text']}"
    await _broadcast_subscribers(context.bot, text)

async def job_fawaid(context: ContextTypes.DEFAULT_TYPE):
    fawaid_text = next_content_item("fawaid", FAWAID)
    await _broadcast_subscribers(context.bot, fawaid_text)

async def job_reflection(context: ContextTypes.DEFAULT_TYPE):
    reflection = next_content_item("reflections", REFLECTIONS)
    await _broadcast_subscribers(context.bot, reflection)


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

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("prayers",     prayers_command))
    app.add_handler(CommandHandler("wilaya",      wilaya_command))
    app.add_handler(CommandHandler("subscribe",   subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("wird",        wird_command))
    app.add_handler(CommandHandler("dua",         dua_command))
    app.add_handler(CommandHandler("stats",       stats_command))
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
    jq.run_daily(job_hijri_history, datetime.time(7, 0),  name="hijri_history")
    jq.run_daily(job_wife_dua,      datetime.time(20, 0), name="wife_dua")

    # محتوى متجدد كل نصف ساعة — قصص الصالحين، ثم بعدها بـ15 دقيقة فائدة
    # إيمانية، ثم خاطرة/تدبر بعد كل قصة بخمس دقائق (يتكرر لاحقاً كل نصف ساعة)
    jq.run_repeating(job_story,      interval=1800, first=0,   name="story")
    jq.run_repeating(job_reflection, interval=1800, first=300, name="reflection")
    jq.run_repeating(job_fawaid,     interval=1800, first=900, name="fawaid")

    # ── جدول صلوات اليوم فور الإقلاع
    jq.run_once(job_schedule_prayers, when=10, name="schedule_prayers_startup")

    logger.info("✅ البوت يعمل — 31 ولاية + مواقيت الصلاة + محتوى متجدد للمشتركين")

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

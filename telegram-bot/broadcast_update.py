"""
سكريبت إرسال جماعي لمرة واحدة — إشعار بالتحديثات الجديدة
يُشغَّل منفصلاً: python3 broadcast_update.py
"""
import asyncio
import json
import os
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError

BASE = Path(__file__).parent

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

ALL_USERS_FILE   = BASE / "all_users.json"
SUBSCRIBERS_FILE = BASE / "subscribers.json"


def load_all_users() -> set:
    if ALL_USERS_FILE.exists():
        try:
            return set(json.loads(ALL_USERS_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


MESSAGE = (
    "السلام عليكم ورحمة الله وبركاته 🌿\n\n"
    "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
    "🌟 *تحديث جديد في البوت!*\n"
    "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n\n"
    "يا خوتي وخواتي الموحدين 🤍\n\n"
    "البوت تجدّد بميزات جديدة تخدمكم:\n\n"
    "🎛️ *قائمة أزرار جديدة*\n"
    "دروك القائمة تظهر في أسفل الشاشة\n"
    "تقدروا تخفّوها وتظهّروها بزر المربع ■\n\n"
    "🗺️ *31 ولاية — مواقيت الصلاة لمدينتك*\n"
    "اختر ولايتك وتصلك تنبيهات الصلاة\n"
    "بتوقيت مدينتك الصحيح بالضبط\n\n"
    "🧠 *بنك أسئلة جديد*\n"
    "أحكام المرأة المسلمة وقصص الصحابيات\n"
    "كل يوم سؤال جديد بخيارين + تلميح\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🤍 *دعاء هدية*:\n\n"
    "اللهم اجعل هذا البوت في ميزان حسنات صاحبته\n"
    "*رَيْحَانَةُ المَغْرِبِ الأَوْسَطِ الأَنْدَلُسِيَّة*\n"
    "اللهم اغفر لها وارحمها وثقّل موازينها\n"
    "بكل حرف تعلّمه مسلم من هذا البوت\n"
    "آمين يا رب العالمين 🌿\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "👇 *اضغط /start لتفعيل القائمة الجديدة*\n\n"
    "🖤⚔️☝🏻"
)


async def broadcast():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN غير موجود!")
        return

    bot   = Bot(token=TOKEN)
    users = load_all_users()

    if not users:
        print("⚠️ لا يوجد مستخدمون في قاعدة البيانات.")
        return

    print(f"📤 إرسال لـ {len(users)} مستخدم...")
    sent = failed = 0

    for uid in list(users):
        try:
            await bot.send_message(
                chat_id=uid,
                text=MESSAGE,
                parse_mode="Markdown",
            )
            sent += 1
            await asyncio.sleep(0.05)   # 20 رسالة/ثانية — ضمن حدود Telegram
        except TelegramError as e:
            print(f"  ⚠️ فشل {uid}: {e}")
            failed += 1

    print(f"\n✅ تم الإرسال: {sent} | ❌ فشل: {failed}")


if __name__ == "__main__":
    asyncio.run(broadcast())

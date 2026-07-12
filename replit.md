# بوت تيليجرام إسلامي (تذكيرات، أوقات الصلاة، أسئلة)

بوت تيليجرام بايثون يقدّم تذكيرات دينية (أذكار، ورد، قيام)، أوقات الصلاة حسب الولاية، وأسئلة/كويز يومية. الكود الأساسي في مجلد `telegram-bot/`.

## التشغيل والنشر

- **الإنتاج (Production) يعمل على Railway**، وليس على Replit. النشر يتم عبر `Dockerfile` (في جذر المشروع) الذي ينسخ `telegram-bot/` وينفّذ `python3 bot.py`، وإعدادات Railway في `railway.json`.
- **Replit هنا هو منصة تعديل الكود فقط** — لا يوجد workflow لتشغيل البوت على Replit عمداً، لتجنّب تعارض في استقبال تحديثات تيليجرام (Telegram لا يسمح بأكثر من عميل واحد يعمل بـ polling على نفس التوكن في نفس الوقت). لا تُشغّل `telegram-bot/bot.py` هنا إلا إذا أردت تعطيل البوت على Railway أولاً.
- المتغيّر `TELEGRAM_BOT_TOKEN` محفوظ كـ **Secret** مشفّر على Replit (وليس كنص عادي)، ويجب ضبط نفس التوكن كمتغيّر بيئة على Railway بشكل منفصل.

## البنية

- `telegram-bot/bot.py` — نقطة الدخول الرئيسية للبوت (handlers، polling)
- `telegram-bot/content.py` — محتوى الأذكار/الأسئلة/الكويز
- `telegram-bot/reminders.py` — نصوص التذكيرات (وِرد، أذكار، قيام، دعاء)
- `telegram-bot/prayer_times.py` — حساب أوقات الصلاة حسب الولاية
- `telegram-bot/broadcast_update.py` — سكريبت بث رسالة جماعية لمرة واحدة (يُشغَّل يدويًا)
- `telegram-bot/*.json` — تخزين بسيط بملفات JSON (subscribers, users, wilayas)

## ملاحظة أمان

كان `TELEGRAM_BOT_TOKEN` محفوظًا كنص عادي في ملف `.replit` (وهو موجود في تاريخ git)، فتم نقله إلى Secrets. **يُنصح بتجديد التوكن من BotFather** (`/revoke` أو `/token`) لأنه كان مكشوفًا في الكود، ثم تحديث القيمة الجديدة في Secrets هنا وفي متغيرات بيئة Railway.

## User preferences

- Replit يُستخدم فقط لتعديل الكود — لا تُشغّل أو تنشر البوت من Replit؛ التشغيل الحي دائمًا على Railway.

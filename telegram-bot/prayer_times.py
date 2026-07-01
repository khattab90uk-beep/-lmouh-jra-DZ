# ═══════════════════════════════════════════════════════════════════
# حساب مواقيت الصلاة — مدينة الجزائر
# الإحداثيات: 36.7538 شمالاً، 3.0588 شرقاً
# الطريقة: رابطة العالم الإسلامي (MWL)
# ═══════════════════════════════════════════════════════════════════

import math
import datetime

LAT         = 36.7538   # خط العرض
LON         = 3.0588    # خط الطول
UTC_DIFF    = 1         # الجزائر UTC+1
FAJR_ANGLE  = 18.0      # زاوية الفجر  (MWL)
ISHA_ANGLE  = 17.0      # زاوية العشاء (MWL)
ASR_FACTOR  = 1.0       # شافعي/مالكي/حنبلي


def _dtr(d): return d * math.pi / 180.0
def _rtd(r): return r * 180.0 / math.pi

def _fix_hour(h):
    h %= 24
    return h + 24 if h < 0 else h

def _fix_angle(a):
    a %= 360
    return a + 360 if a < 0 else a


def _sun_position(jd: float):
    """موضع الشمس لتاريخ جوليان — يُعيد (الميل، معادلة الوقت بالساعات)."""
    d = jd - 2451545.0
    g = _fix_angle(357.529 + 0.98560028 * d)
    q = _fix_angle(280.459 + 0.98564736 * d)
    L = _fix_angle(q + 1.915 * math.sin(_dtr(g)) + 0.020 * math.sin(_dtr(2 * g)))
    e = 23.439 - 0.00000036 * d
    RA  = _rtd(math.atan2(math.cos(_dtr(e)) * math.sin(_dtr(L)), math.cos(_dtr(L)))) / 15
    dec = _rtd(math.asin(math.sin(_dtr(e)) * math.sin(_dtr(L))))
    EqT = q / 15 - _fix_hour(RA)
    return dec, EqT


def _julian_day(year: int, month: int, day: int) -> float:
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100)
    B = 2 - A + math.floor(A / 4)
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5


def _hour_angle(altitude_deg: float, dec: float) -> float:
    """
    حساب زاوية الساعة (بالساعات) لزاوية ارتفاع معطاة.
    altitude_deg موجب = فوق الأفق، سالب = تحت الأفق.
    """
    sin_alt = math.sin(_dtr(altitude_deg))
    sin_lat = math.sin(_dtr(LAT))
    cos_lat = math.cos(_dtr(LAT))
    sin_dec = math.sin(_dtr(dec))
    cos_dec = math.cos(_dtr(dec))

    val = (sin_alt - sin_lat * sin_dec) / (cos_lat * cos_dec)
    if abs(val) > 1:
        return float('nan')
    return _rtd(math.acos(val)) / 15


def compute_prayer_times(date: datetime.date) -> dict:
    """
    يحسب مواقيت الصلاة لتاريخ معطى.
    يُعيد dict بـ datetime.time بتوقيت الجزائر (UTC+1).
    """
    jd  = _julian_day(date.year, date.month, date.day) - LON / (15 * 24)
    dec, EqT = _sun_position(jd)

    # الظهر = نصف النهار الشمسي
    dhuhr_h = 12 - EqT - LON / 15 + UTC_DIFF

    # الشروق والغروب (ارتفاع = −0.8333° لتصحيح الانكسار وقطر الشمس)
    ha_horizon = _hour_angle(-0.8333, dec)
    sunrise_h  = dhuhr_h - ha_horizon
    sunset_h   = dhuhr_h + ha_horizon

    # الفجر: الشمس تحت الأفق بـ FAJR_ANGLE
    fajr_h = dhuhr_h - _hour_angle(-FAJR_ANGLE, dec)

    # العشاء: الشمس تحت الأفق بـ ISHA_ANGLE
    isha_h = dhuhr_h + _hour_angle(-ISHA_ANGLE, dec)

    # العصر: ارتفاع الشمس = arctan(1 / (عامل + tan|خط العرض - الميل|))
    asr_alt = _rtd(math.atan(1.0 / (ASR_FACTOR + math.tan(_dtr(abs(LAT - dec))))))
    asr_h   = dhuhr_h + _hour_angle(asr_alt, dec)

    # المغرب = الغروب + 5 دقائق احتياطاً
    maghrib_h = sunset_h + 5 / 60

    def _to_time(h: float) -> datetime.time:
        if math.isnan(h):
            return datetime.time(0, 0)
        h = _fix_hour(h)
        hours   = int(h)
        minutes = int(round((h - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes -= 60
        return datetime.time(hours % 24, minutes)

    return {
        "fajr":    _to_time(fajr_h),
        "sunrise": _to_time(sunrise_h),
        "dhuhr":   _to_time(dhuhr_h),
        "asr":     _to_time(asr_h),
        "maghrib": _to_time(maghrib_h),
        "isha":    _to_time(isha_h),
    }


PRAYER_TEXTS = {
    "fajr": {
        "title":  "🌅 وقت الفجر",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "دروك وقت الفجر — *{time}* — قومو صلّو!\n\n"
            "الفجر يفتح باب يوم جديد معَ ربّك،\n"
            "ما تضيّعوش هذي اللحظة الغالية!\n\n"
            "قال ﷺ:\n"
            "«*ركعتا الفجر خير من الدنيا وما فيها*»\n"
            "[مسلم]\n\n"
            "وقال:\n"
            "«*من صلى الفجر في جماعة فكأنما قام الليل كله*»\n"
            "[مسلم]\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "dhuhr": {
        "title":  "☀️ وقت الظهر",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "وقت الظهر — *{time}* — واش راكم؟\n\n"
            "خلّو كل حاجة وقومو صلّو!\n"
            "الله يستاهل إنك تقفو ليه دقايق في وسط يومك 🤍\n\n"
            "قال ﷺ:\n"
            "«*من حافظ على أربع ركعات قبل الظهر وأربع بعدها\n"
            "حرّمه الله على النار*»\n"
            "[أبو داود — صحيح]\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "asr": {
        "title":  "🌤️ وقت العصر",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "وقت العصر — *{time}* — هذي هي الصلاة الوسطى!\n\n"
            "ربّك قالها بنفسه في القرآن:\n"
            "﴿*حَافِظُوا عَلَى الصَّلَوَاتِ وَالصَّلَاةِ الْوُسْطَىٰ*﴾\n\n"
            "وقال ﷺ:\n"
            "«*من فاتته صلاة العصر فكأنما وُتر أهله وماله*»\n"
            "[متفق عليه]\n\n"
            "ما تفوّتوهاش — صلّو دروك! 🤍\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "maghrib": {
        "title":  "🌅 وقت المغرب",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "غرب الشمس — وقت المغرب *{time}* — صلّو بسرعة!\n\n"
            "المغرب ما يتأخّرش — وقتها قصير وقيمتها كبير!\n\n"
            "قال ﷺ:\n"
            "«*لا تزال أمتي بخير ما لم يؤخّروا المغرب\n"
            "إلى أن تشتبك النجوم*»\n"
            "[أبو داود — صحيح]\n\n"
            "وبعد الصلاة لا تنسو أذكار المساء 🌿\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "isha": {
        "title":  "🌙 وقت العشاء",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "وقت العشاء — *{time}* — الصلاة الأخيرة في يومك!\n\n"
            "اختمو يومكم مع الله قبل ما تناموا 🤍\n\n"
            "قال ﷺ:\n"
            "«*من صلى العشاء في جماعة فكأنما قام نصف الليل،\n"
            "ومن صلى الفجر في جماعة فكأنما قام الليل كله*»\n"
            "[مسلم]\n\n"
            "وبعد العشاء لا تنسو:\n"
            "✅ الوتر قبل النوم\n"
            "✅ آية الكرسي قبل ما تناموا\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
}


def prayer_reminder_text(prayer_key: str, prayer_time: datetime.time, hijri: str) -> str:
    p    = PRAYER_TEXTS[prayer_key]
    body = p["body"].replace("{time}", prayer_time.strftime("%H:%M"))
    return (
        f"🕌 *{p['title']}*\n"
        f"📅 {hijri}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}"
    )

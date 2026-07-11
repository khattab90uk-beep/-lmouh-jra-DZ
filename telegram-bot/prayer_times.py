# ═══════════════════════════════════════════════════════════════════
# حساب مواقيت الصلاة — 30 ولاية جزائرية + حضرموت
# الطريقة: رابطة العالم الإسلامي (MWL)
# ═══════════════════════════════════════════════════════════════════

import math
import datetime

FAJR_ANGLE  = 18.0
ISHA_ANGLE  = 17.0
ASR_FACTOR  = 1.0

# ─── 30 ولاية جزائرية + حضرموت ───────────────────────────────────
WILAYAS = {
    "adrar":          {"name": "ولاية أدرار (01)",              "lat":  27.874, "lon":  -0.294, "utc": 1},
    "chlef":          {"name": "ولاية الشلف (02)",              "lat":  36.165, "lon":   1.332, "utc": 1},
    "laghouat":       {"name": "ولاية الأغواط (03)",            "lat":  33.800, "lon":   2.883, "utc": 1},
    "oum_bouaghi":    {"name": "ولاية أم البواقي (04)",         "lat":  35.878, "lon":   7.113, "utc": 1},
    "batna":          {"name": "ولاية باتنة (05)",              "lat":  35.555, "lon":   6.174, "utc": 1},
    "bejaia":         {"name": "ولاية بجاية (06)",              "lat":  36.751, "lon":   5.057, "utc": 1},
    "biskra":         {"name": "ولاية بسكرة (07)",              "lat":  34.850, "lon":   5.733, "utc": 1},
    "bechar":         {"name": "ولاية بشار (08)",               "lat":  31.624, "lon":  -2.216, "utc": 1},
    "blida":          {"name": "ولاية البليدة (09)",            "lat":  36.472, "lon":   2.828, "utc": 1},
    "bouira":         {"name": "ولاية البويرة (10)",            "lat":  36.374, "lon":   3.900, "utc": 1},
    "tamanrasset":    {"name": "ولاية تمنراست (11)",            "lat":  22.785, "lon":   5.523, "utc": 1},
    "tebessa":        {"name": "ولاية تبسة (12)",               "lat":  35.404, "lon":   8.125, "utc": 1},
    "tlemcen":        {"name": "ولاية تلمسان (13)",             "lat":  34.883, "lon":  -1.317, "utc": 1},
    "tiaret":         {"name": "ولاية تيارت (14)",              "lat":  35.371, "lon":   1.322, "utc": 1},
    "tizi_ouzou":     {"name": "ولاية تيزي وزو (15)",          "lat":  36.717, "lon":   4.050, "utc": 1},
    "alger":          {"name": "ولاية الجزائر العاصمة (16)",   "lat":  36.754, "lon":   3.059, "utc": 1},
    "djelfa":         {"name": "ولاية الجلفة (17)",             "lat":  34.671, "lon":   3.264, "utc": 1},
    "jijel":          {"name": "ولاية جيجل (18)",               "lat":  36.822, "lon":   5.766, "utc": 1},
    "setif":          {"name": "ولاية سطيف (19)",               "lat":  36.191, "lon":   5.414, "utc": 1},
    "saida":          {"name": "ولاية سعيدة (20)",              "lat":  34.831, "lon":   0.153, "utc": 1},
    "skikda":         {"name": "ولاية سكيكدة (21)",             "lat":  36.876, "lon":   6.906, "utc": 1},
    "sidi_bel_abbes": {"name": "ولاية سيدي بلعباس (22)",       "lat":  35.190, "lon":  -0.631, "utc": 1},
    "annaba":         {"name": "ولاية عنابة (23)",              "lat":  36.900, "lon":   7.767, "utc": 1},
    "guelma":         {"name": "ولاية قالمة (24)",              "lat":  36.464, "lon":   7.428, "utc": 1},
    "constantine":    {"name": "ولاية قسنطينة (25)",            "lat":  36.365, "lon":   6.615, "utc": 1},
    "medea":          {"name": "ولاية المدية (26)",             "lat":  36.264, "lon":   2.752, "utc": 1},
    "mostaganem":     {"name": "ولاية مستغانم (27)",            "lat":  35.932, "lon":   0.089, "utc": 1},
    "msila":          {"name": "ولاية المسيلة (28)",            "lat":  35.707, "lon":   4.544, "utc": 1},
    "mascara":        {"name": "ولاية معسكر (29)",              "lat":  35.397, "lon":   0.140, "utc": 1},
    "ouargla":        {"name": "ولاية ورقلة (30)",              "lat":  31.959, "lon":   5.325, "utc": 1},
    "hadhramaut":     {"name": "🌙 ولاية حضرموت — اليمن",      "lat":  15.500, "lon":  48.300, "utc": 3},
}

DEFAULT_WILAYA = "alger"


def _dtr(d): return d * math.pi / 180.0
def _rtd(r): return r * 180.0 / math.pi

def _fix_hour(h):
    h %= 24
    return h + 24 if h < 0 else h

def _fix_angle(a):
    a %= 360
    return a + 360 if a < 0 else a


def _sun_position(jd: float):
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


def _hour_angle(altitude_deg: float, dec: float, lat: float) -> float:
    sin_alt = math.sin(_dtr(altitude_deg))
    sin_lat = math.sin(_dtr(lat))
    cos_lat = math.cos(_dtr(lat))
    sin_dec = math.sin(_dtr(dec))
    cos_dec = math.cos(_dtr(dec))
    val = (sin_alt - sin_lat * sin_dec) / (cos_lat * cos_dec)
    if abs(val) > 1:
        return float('nan')
    return _rtd(math.acos(val)) / 15


def compute_prayer_times(date: datetime.date,
                         lat: float = 36.7538,
                         lon: float = 3.0588,
                         utc_offset: int = 1) -> dict:
    """
    يحسب مواقيت الصلاة لتاريخ وإحداثيات معطاة.
    يُعيد dict بـ datetime.time بالتوقيت المحلي للموقع.
    """
    jd  = _julian_day(date.year, date.month, date.day) - lon / (15 * 24)
    dec, EqT = _sun_position(jd)

    dhuhr_h   = 12 - EqT - lon / 15 + utc_offset
    ha_horizon = _hour_angle(-0.8333, dec, lat)
    sunrise_h  = dhuhr_h - ha_horizon
    sunset_h   = dhuhr_h + ha_horizon
    fajr_h     = dhuhr_h - _hour_angle(-FAJR_ANGLE, dec, lat)
    isha_h     = dhuhr_h + _hour_angle(-ISHA_ANGLE, dec, lat)
    asr_alt    = _rtd(math.atan(1.0 / (ASR_FACTOR + math.tan(_dtr(abs(lat - dec))))))
    asr_h      = dhuhr_h + _hour_angle(asr_alt, dec, lat)
    maghrib_h  = sunset_h + 5 / 60

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


def compute_prayer_times_for_wilaya(date: datetime.date, wilaya_key: str) -> dict:
    w = WILAYAS.get(wilaya_key, WILAYAS[DEFAULT_WILAYA])
    return compute_prayer_times(date, lat=w["lat"], lon=w["lon"], utc_offset=w["utc"])


PRAYER_TEXTS = {
    "fajr": {
        "title": "🌅 وقت الفجر",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "دروك وقت الفجر — *{time}* — قومو صلّو!\n\n"
            "الفجر يفتح باب يوم جديد معَ ربّك،\n"
            "ما تضيّعوش هذي اللحظة الغالية!\n\n"
            "قال ﷺ:\n"
            "«*ركعتا الفجر خير من الدنيا وما فيها*»\n"
            "[مسلم]\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "dhuhr": {
        "title": "☀️ وقت الظهر",
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
        "title": "🌤️ وقت العصر",
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
        "title": "🌅 وقت المغرب",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "غرب الشمس — وقت المغرب *{time}* — صلّو بسرعة!\n\n"
            "المغرب ما يتأخّرش!\n\n"
            "قال ﷺ:\n"
            "«*لا تزال أمتي بخير ما لم يؤخّروا المغرب\n"
            "إلى أن تشتبك النجوم*»\n"
            "[أبو داود — صحيح]\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
    "isha": {
        "title": "🌙 وقت العشاء",
        "body": (
            "يا خوتي الموحدين 🤍  يا خواتي الموحدات 🤍\n\n"
            "وقت العشاء — *{time}* — الصلاة الأخيرة في يومك!\n\n"
            "اختمو يومكم مع الله قبل ما تناموا 🤍\n\n"
            "قال ﷺ:\n"
            "«*من صلى العشاء في جماعة فكأنما قام نصف الليل*»\n"
            "[مسلم]\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "_حيّ على الصلاة — حيّ على الفلاح_ 🌿\n\n"
            "🖤⚔️☝🏻"
        ),
    },
}


def prayer_reminder_text(prayer_key: str, prayer_time: datetime.time,
                         hijri: str, wilaya_name: str = "") -> str:
    p    = PRAYER_TEXTS[prayer_key]
    body = p["body"].replace("{time}", prayer_time.strftime("%H:%M"))
    loc  = f"\n📍 _{wilaya_name}_" if wilaya_name else ""
    return (
        f"🕌 *{p['title']}*\n"
        f"📅 {hijri}{loc}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}"
    )

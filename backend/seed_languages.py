"""
Jednorazowe wypełnienie tabeli `languages` 50 najpopularniejszymi językami.
Uruchom raz: python -m backend.seed_languages
"""
import asyncio
from sqlalchemy import select
from .database import AsyncSessionLocal, init_db
from .models import Language

# (code, name_pl, name_native, flag_emoji)
LANGUAGES = [
    ("en", "Angielski", "English", "🇬🇧"),
    ("zh", "Chiński", "中文", "🇨🇳"),
    ("hi", "Hindi", "हिन्दी", "🇮🇳"),
    ("es", "Hiszpański", "Español", "🇪🇸"),
    ("fr", "Francuski", "Français", "🇫🇷"),
    ("ar", "Arabski", "العربية", "🇸🇦"),
    ("bn", "Bengalski", "বাংলা", "🇧🇩"),
    ("pt", "Portugalski", "Português", "🇵🇹"),
    ("ru", "Rosyjski", "Русский", "🇷🇺"),
    ("ur", "Urdu", "اردو", "🇵🇰"),
    ("id", "Indonezyjski", "Bahasa Indonesia", "🇮🇩"),
    ("de", "Niemiecki", "Deutsch", "🇩🇪"),
    ("ja", "Japoński", "日本語", "🇯🇵"),
    ("sw", "Suahili", "Kiswahili", "🇰🇪"),
    ("mr", "Marathi", "मराठी", "🇮🇳"),
    ("te", "Telugu", "తెలుగు", "🇮🇳"),
    ("tr", "Turecki", "Türkçe", "🇹🇷"),
    ("ta", "Tamilski", "தமிழ்", "🇮🇳"),
    ("vi", "Wietnamski", "Tiếng Việt", "🇻🇳"),
    ("ko", "Koreański", "한국어", "🇰🇷"),
    ("it", "Włoski", "Italiano", "🇮🇹"),
    ("yue", "Kantoński", "廣東話", "🇭🇰"),
    ("th", "Tajski", "ไทย", "🇹🇭"),
    ("gu", "Gudżarati", "ગુજરાતી", "🇮🇳"),
    ("fa", "Perski", "فارسی", "🇮🇷"),
    ("pl", "Polski", "Polski", "🇵🇱"),
    ("uk", "Ukraiński", "Українська", "🇺🇦"),
    ("ml", "Malajalam", "മലയാളം", "🇮🇳"),
    ("kn", "Kannada", "ಕನ್ನಡ", "🇮🇳"),
    ("or", "Orija", "ଓଡ଼ିଆ", "🇮🇳"),
    ("my", "Birmański", "မြန်မာ", "🇲🇲"),
    ("pa", "Pendżabski", "ਪੰਜਾਬੀ", "🇮🇳"),
    ("ro", "Rumuński", "Română", "🇷🇴"),
    ("nl", "Niderlandzki", "Nederlands", "🇳🇱"),
    ("az", "Azerbejdżański", "Azərbaycan", "🇦🇿"),
    ("el", "Grecki", "Ελληνικά", "🇬🇷"),
    ("cs", "Czeski", "Čeština", "🇨🇿"),
    ("hu", "Węgierski", "Magyar", "🇭🇺"),
    ("sv", "Szwedzki", "Svenska", "🇸🇪"),
    ("he", "Hebrajski", "עברית", "🇮🇱"),
    ("da", "Duński", "Dansk", "🇩🇰"),
    ("fi", "Fiński", "Suomi", "🇫🇮"),
    ("no", "Norweski", "Norsk", "🇳🇴"),
    ("sk", "Słowacki", "Slovenčina", "🇸🇰"),
    ("bg", "Bułgarski", "Български", "🇧🇬"),
    ("hr", "Chorwacki", "Hrvatski", "🇭🇷"),
    ("sr", "Serbski", "Српски", "🇷🇸"),
    ("lt", "Litewski", "Lietuvių", "🇱🇹"),
    ("lv", "Łotewski", "Latviešu", "🇱🇻"),
    ("et", "Estoński", "Eesti", "🇪🇪"),
]


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Language.code))).scalars().all()
        existing_set = set(existing)
        added = 0
        for code, name_pl, name_native, flag in LANGUAGES:
            if code in existing_set:
                continue
            db.add(Language(code=code, name_pl=name_pl, name_native=name_native, flag_emoji=flag))
            added += 1
        await db.commit()
        print(f"Dodano {added} języków (łącznie w bazie: {len(existing) + added}).")


if __name__ == "__main__":
    asyncio.run(main())
def build_ai_prompt(form_data: dict, count: int) -> str:
    from_districts = ", ".join(form_data.get("from_districts", []))
    to_districts = ", ".join(form_data.get("to_districts", []))

    flags = form_data.get("flags", {})
    urgent = "ha" if flags.get("urgent") else "yo‘q"
    has_woman = "ha" if flags.get("has_woman") else "yo‘q"
    baggage = "ha" if flags.get("baggage") else "yo‘q"
    mail = "ha" if flags.get("mail") else "yo‘q"
    telegram = "ha" if flags.get("telegram") else "yo‘q"

    return f"""
SEN — Telegramda e’lon yozadigan TAJRIBALI SHAFYORSAN.
SEN YOZADIGAN MATN REAL ODAM YOZGANDAY BO‘LISHI SHART.

ENG MUHIM QOIDA (BUNI BUZMA):
- Xar bir malumotdan keyin bir qatorni bo`sh qoldir
- Avval gapni ICHINGDA soddalashtir
- Keyin ENG ODDIY, OG‘ZAKI KO‘RINISHDA yoz
- Telegramda odamlar qanday yozsa — XUDDI SHUNDAY yoz
- “nazarda tutaman”, “shuning uchun”, “maqsadim”, “qulay bo‘lishi uchun” kabi so‘zlarni ISHLATMA
- izohlab yozma, shunchaki AYTGANDAY yoz

❌ QAT’IYAN YO‘Q:
- rasmiy jumlalar
- tushuntirish
- reklama ohangi
- ortiqcha so‘z

POST KO‘RINISHI SHART:
- qisqa jumlalar
- 1–2 qatorlik bloklar
- bo‘sh qatorlar bilan ajratilgan
- o‘qilishi juda oson

MA’LUMOTLAR (FAKT SIFATIDA ISHLAT):
Yo‘nalish:
{form_data.get("from_region")}, {from_districts} → {form_data.get("to_region")}, {to_districts}

Vaqt: {form_data.get("time")}
Odam soni: {form_data.get("people")}

Mashina: {form_data.get("car")}
Yoqilg‘i: {form_data.get("fuel")}

Bagaj: {baggage}
Pochta: {mail}
Ayol kishi: {has_woman}
Tezkor: {urgent}

Izoh: {form_data.get("comment")}

Aloqa:
{form_data.get("phone")}
Telegram: {telegram}

YOZISH USLUBI MISOLI (SHUNGA O‘XSHATIB YOZ):

🚕 Yo‘l bor.

Andijondan Toshkentga ketaman.
Bugun kechqurun chiqaman.

Mashina Gentra.
2 kishiga joy bor.

⏰ 22:30

Bagaj muammo emas.
Telegramdan yozsa bo‘ladi.

VAZIFA:
Yuqoridagi MA’LUMOTLAR asosida {count} ta TURFA post yoz.

HAR BIR POST:
- aynan shunaqa uslubda bo‘lsin
- haddan tashqari chiroyli bo‘lmasin
- “haqiqiy shafyor yozgan” degan taassurot bersin
- oxiri aloqa qilishga undasin

POSTLARNI ALOHIDA BLOK QIL.
RAQAMLAMA QILMA.
""".strip()

def build_ai_prompt(form_data: dict, count: int) -> str:
    from_d = ", ".join(form_data.get("from_districts", []))
    to_d = ", ".join(form_data.get("to_districts", []))

    return f"""
SEN O‘ZBEK TILINI JUDA YAXSHI BILADIGAN TAJRIBALI SHAFYORSAN.
SEN YOZGAN HAR BIR GAP O‘ZBEK TILI GRAMMATIKASIGA TO‘LIQ MOS BO‘LISHI SHART.

SEN PSIXOLOG HAM SAN:
- Telegramdagi gavjum guruhlarda qaysi e’lonlar e’tibor tortishini bilasan
- odamlar nimaga tez yozishini tushunasan

QAT’IY QOIDALAR:
- gaplar sodda, ravon va tabiiy bo‘lsin
- sun’iy yoki tarjima ohangidagi gaplar BO‘LMASIN
- noto‘g‘ri so‘z tartibi BO‘LMASIN
- reklama yoki marketing uslubi BO‘LMASIN
- shafyor o‘z nomidan gapirsin
- juda rasmiy ham, juda hazil ham bo‘lmasin

FORMAT TALABLARI:
- post UZUN bo‘lsin (kamida 10–14 qator)
- bo‘sh qatorlar bilan ajrat
- o‘qishga oson bo‘lsin
- asosiy ma’lumotlar ko‘zga tashlansin
- oxiri yozishga undasin

❌ ISHLATMA:
- “aksiya”, “taklif”, “foyda”, “eng yaxshi”
- majburlovchi gaplar
- kulgili yoki masxarali jumlalar

MA’LUMOTLAR:
Qayerdan: {form_data.get("from_region")} ({from_districts})
Qayerga: {form_data.get("to_region")} ({to_districts})

Odam soni: {form_data.get("people")}
Ketish vaqti: {form_data.get("time")}

Mashina: {form_data.get("car")}
Yoqilg‘i: {form_data.get("fuel")}

Telefon: {form_data.get("phone")}
Qo‘shimcha telefon: {form_data.get("phone2")}

Izoh: {form_data.get("comment")}

Holatlar:
- Tezkor: {urgent}
- Ayol kishi bor: {has_woman}
- Bagaj bor: {baggage}
- Pochta olinadi: {mail}
- Telegramdan yozish mumkin: {telegram}

VAZIFA:
Yuqoridagi ma’lumotlarga asoslanib {count} ta TURFA, BIR-BIRIGA O‘XSHAMAGAN ELON yoz.

HAR BIR ELON:
- mutlaqo o‘zbekcha
- grammatik jihatdan toza
- “buni haqiqiy shafyor yozgan” degan taassurot bersin
- gavjum guruhda ko‘zga tashlansin
- oxirida aloqa qilishga undasin

HAR BIR ELONNI ALOHIDA BLOK QILIB YOZ.
RAQAMLAMA QILMA.
"""

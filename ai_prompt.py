def build_ai_prompt(form_data: dict, count: int) -> str:
    from_d = ", ".join(form_data.get("from_districts", []))
    to_d = ", ".join(form_data.get("to_districts", []))

    return f"""
SEN TAJRIBALI O‘ZBEK SHAFYORSAN.

QOIDALAR:
- faqat sof o‘zbek tili
- reklama ohangi bo‘lmasin
- tabiiy Telegram e’lon

MA’LUMOT:
Qayerdan: {form_data.get("from_region")} ({from_d})
Qayerga: {form_data.get("to_region")} ({to_d})
Odam: {form_data.get("people")}
Vaqt: {form_data.get("time")}
Mashina: {form_data.get("car")}
Yoqilg‘i: {form_data.get("fuel")}
Telefon: {form_data.get("phone")}
Izoh: {form_data.get("comment")}

VAZIFA:
{count} ta turli e’lon yoz.
Har biri alohida blok bo‘lsin.
"""

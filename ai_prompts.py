from openai import OpenAI

client = OpenAI()

def generate_ai_posts(form: dict, count: int = 5) -> list[str]:
    prompt = f"""
Sen tajribali taksist eʼlon yozuvchisan.
Quyidagi maʼlumotlar asosida {count} xil, bir-biridan farqli,
ammo maʼnosi bir xil bo‘lgan Telegram postlar yoz.

Maʼlumotlar:
- Qayerdan: {form.get('from')}
- Qayerga: {form.get('to')}
- Odamlar: {form.get('people')}
- Vaqt: {form.get('time')}
- Telefon: {form.get('phone')}
- Status
- Aloqa
- mashina rusumi
Talablar:
- Qisqa
- Tabiiy
- Spamga o‘xshamasin
- Emoji kamroq ishlat
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    text = res.output_text

    # AI odatda postlarni \n\n bilan ajratib beradi
    posts = [p.strip() for p in text.split("\n\n") if p.strip()]

    return posts[:count]

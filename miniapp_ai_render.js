function buildPost(data) {
  let text = "";

  text += `🚕 ${data.from} → ${data.to}\n\n`;
  text += `👥 ${data.people}\n`;
  text += `⏰ ${data.time}\n`;

  if (data.urgent === "Ha (tezkor)") {
    text += `⚡ TEZKOR\n`;
  }

  if (data.female === "Ha") {
    text += `👩 Ayol kishi bor\n`;
  }

  text += `🚗 Mashina: ${data.car} (${data.fuel})\n`;

  if (data.package !== "Yo‘q") {
    text += `📦 Pochta: ${data.package}\n`;
  }

  text += `\n📞 ${data.phone}`;

  if (data.telegram) {
    text += `\n💬 ${data.telegram}`;
  }

  return text;
}

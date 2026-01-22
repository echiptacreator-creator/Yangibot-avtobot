const tg = window.Telegram.WebApp;

document.getElementById("send").onclick = () => {
  const payload = {
    from: document.getElementById("from").value,
    to: document.getElementById("to").value,
    people: document.getElementById("people").value,
    time: document.getElementById("time").value,
    phone: document.getElementById("phone").value
  };

  // 🔥 ENG MUHIM QATOR
  tg.sendData(JSON.stringify(payload));

  // optional
  tg.close();
};

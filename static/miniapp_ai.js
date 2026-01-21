const form = document.getElementById("form");
const pageForm = document.getElementById("page-form");
const pagePreview = document.getElementById("page-preview");
const previewList = document.getElementById("preview-list");

const formData = {};

AI_FORM_CONFIG.forEach(f => {
  const field = document.createElement("div");
  field.className = "field";

  const label = document.createElement("label");
  label.innerText = f.label;
  field.appendChild(label);

  if (f.type === "toggle") {
    const wrap = document.createElement("div");
    wrap.className = "toggle";

    ["Yo‘q", "Ha"].forEach(v => {
      const btn = document.createElement("button");
      btn.innerText = v;
      btn.onclick = e => {
        e.preventDefault();
        formData[f.key] = v;
        [...wrap.children].forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      };
      wrap.appendChild(btn);
    });

    field.appendChild(wrap);
  } else {
    let input = f.type === "select"
      ? document.createElement("select")
      : document.createElement("input");

    if (f.type === "select") {
      f.options.forEach(o => {
        const opt = document.createElement("option");
        opt.value = o;
        opt.innerText = o;
        input.appendChild(opt);
      });
    } else {
      input.type = f.type === "phone" ? "tel" : f.type;
    }

    input.onchange = () => formData[f.key] = input.value;
    field.appendChild(input);
  }

  form.appendChild(field);
});

document.getElementById("generate").onclick = () => {
  // fake preview (real AI botda)
  previewList.innerHTML = "";
  for (let i = 1; i <= 5; i++) {
    const card = document.createElement("div");
    card.className = "preview-card";
    card.innerText = `🚕 ${formData.from} → ${formData.to}\n👥 ${formData.people} ta\n⏰ ${formData.time}`;
    previewList.appendChild(card);
  }

  pageForm.classList.add("hidden");
  pagePreview.classList.remove("hidden");
};

document.getElementById("send").onclick = () => {
  Telegram.WebApp.sendData(JSON.stringify({
    type: "ai_form",
    payload: formData
  }));
  Telegram.WebApp.close();
};

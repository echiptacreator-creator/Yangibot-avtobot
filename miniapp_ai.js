const form = document.getElementById("form");

window.AI_FORM_CONFIG.forEach(f => {
  const wrap = document.createElement("div");
  wrap.style.marginBottom = "10px";

  const label = document.createElement("label");
  label.innerText = f.label;
  wrap.appendChild(label);

  let input;

  if (f.type === "select") {
    input = document.createElement("select");
    f.options.forEach(o => {
      const opt = document.createElement("option");
      opt.value = o;
      opt.innerText = o;
      input.appendChild(opt);
    });
  } 
  else if (f.type === "toggle") {
    input = document.createElement("select");
    f.options.forEach(o => {
      const opt = document.createElement("option");
      opt.value = o;
      opt.innerText = o;
      input.appendChild(opt);
    });
  }
  else {
    input = document.createElement("input");
    input.type = f.type === "phone" ? "tel" : f.type;
  }

  input.name = f.key;
  input.required = true;

  wrap.appendChild(input);
  form.appendChild(wrap);
});

document.getElementById("send").onclick = () => {
  const data = {};
  [...form.elements].forEach(el => {
    if (el.name) data[el.name] = el.value;
  });

  Telegram.WebApp.sendData(JSON.stringify({
    type: "ai_form",
    payload: data
  }));

  Telegram.WebApp.close();
};

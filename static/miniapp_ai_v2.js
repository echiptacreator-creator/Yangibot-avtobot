const tg = Telegram.WebApp;
const state = {};

// 🔹 INIT
function init() {
  fillSelect("from_region", Object.keys(REGIONS));
  fillSelect("to_region", Object.keys(REGIONS));
  fillSelect("car", CARS);
}
init();

// 🔹 SELECT TO‘LDIRISH
function fillSelect(id, items) {
  const s = document.getElementById(id);
  s.innerHTML = "";
  items.forEach(i => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = i;
    s.appendChild(o);
  });
}

// 🔹 TOGGLELAR
document.querySelectorAll(".toggle").forEach(t => {
  t.onclick = () => {
    t.classList.toggle("active");
    state[t.dataset.key] = t.classList.contains("active");
  };
});

// 🔹 BOSHQA MASHINA
document.getElementById("car").onchange = e => {
  document
    .getElementById("custom_car")
    .classList.toggle("hidden", e.target.value !== "Boshqa");
};

// 🔹 TUMAN QO‘SHISH (IKKALA TOMON UCHUN)
function addDistrict(type) {
  const regionSelect =
    type === "from"
      ? document.getElementById("from_region")
      : document.getElementById("to_region");

  const region = regionSelect.value;
  if (!region) {
    alert("Avval viloyatni tanlang");
    return;
  }

  const container =
    type === "from"
      ? document.getElementById("from_districts")
      : document.getElementById("to_districts");

  const select = document.createElement("select");
  select.style.marginTop = "8px";

  (REGIONS[region] || []).forEach(d => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    select.appendChild(opt);
  });

  container.appendChild(select);
}

// 🔹 TUMANLARNI O‘QISH
function getDistrictValues(id) {
  return Array.from(
    document.querySelectorAll(`#${id} select`)
  ).map(s => s.value);
}

// 🔹 SUBMIT
function submitForm() {
  const payload = {
    from_region: from_region.value,
    to_region: to_region.value,

    from_districts: getDistrictValues("from_districts"),
    to_districts: getDistrictValues("to_districts"),

    people: people.value,
    time: time.value,
    car: car.value === "Boshqa" ? custom_car.value : car.value,
    fuel: fuel.value,
    phone: phone.value,
    phone2: phone2.value,
    comment: comment.value,

    flags: state
  };

  tg.sendData(
    JSON.stringify({
      action: "ai_post_v2",
      payload
    })
  );

  tg.close();
}

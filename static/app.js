const state = {
  from_districts: [],
  to_districts: [],
  toggles: {}
};

document.querySelectorAll(".toggle").forEach(t => {
  t.onclick = () => {
    t.classList.toggle("active");
    state.toggles[t.dataset.key] = t.classList.contains("active");
  };
});

document.getElementById("car").onchange = e => {
  document.getElementById("car_other").style.display =
    e.target.value === "other" ? "block" : "none";
};

function addDistrict(type) {
  const input = document.createElement("input");
  input.placeholder = "Tuman";
  document.getElementById(type + "_districts").appendChild(input);
}

function collectDistricts(type) {
  return Array.from(
    document.getElementById(type + "_districts").querySelectorAll("input")
  ).map(i => i.value).filter(Boolean);
}

function send() {
  const payload = {
    from_region: from_region.value,
    from_districts: collectDistricts("from"),
    to_region: to_region.value,
    to_districts: collectDistricts("to"),
    people: people.value,
    time: time.value,
    car: car.value === "other" ? car_other.value : car.value,
    fuel: fuel.value,
    phone: phone.value,
    phone_extra: phone_extra.value,
    comment: comment.value,
    ...state.toggles
  };

  Telegram.WebApp.sendData(JSON.stringify(payload));
  Telegram.WebApp.close();
}

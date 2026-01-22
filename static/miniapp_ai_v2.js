const tg = Telegram.WebApp;
const state = {};

function init(){
  fillSelect("from_region", Object.keys(REGIONS));
  fillSelect("to_region", Object.keys(REGIONS));
  fillSelect("car", CARS);
}
init();

function fillSelect(id, items){
  const s=document.getElementById(id);
  items.forEach(i=>{
    const o=document.createElement("option");
    o.value=o.textContent=i;
    s.appendChild(o);
  });
}

document.querySelectorAll(".toggle").forEach(t=>{
  t.onclick=()=>{
    t.classList.toggle("active");
    state[t.dataset.key]=t.classList.contains("active");
  }
});

document.getElementById("car").onchange=e=>{
  document.getElementById("custom_car").classList.toggle("hidden", e.target.value!=="Boshqa");
};

function addDistrict(){
  const div=document.createElement("select");
  REGIONS[from_region.value].forEach(d=>{
    const o=document.createElement("option");
    o.textContent=d;
    div.appendChild(o);
  });
  document.getElementById("districts").appendChild(div);
}

function submitForm(){
  const payload={
    from_region:from_region.value,
    to_region:to_region.value,
    people:people.value,
    time:time.value,
    car:car.value==="Boshqa"?custom_car.value:car.value,
    fuel:fuel.value,
    phone:phone.value,
    phone2:phone2.value,
    comment:comment.value,
    ...state
  };

  tg.sendData(JSON.stringify({action:"ai_post_v2",payload}));
  tg.close();
}
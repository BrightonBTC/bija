setInterval(getUpdates, 10000);
async function getUpdates() {
  const response = await fetch('/upd');
  const d = await response.json();
  console.log(d);
  if("profile" in d){
    update_profile(d["profile"])
  }
}
function update_profile(d){
  console.log(d);
  document.getElementById("pname").value = d['name']
  document.getElementById("pim").value = d['picture']
  document.getElementById("ppic").src = d['picture']
  document.getElementById("pmsg").value = d['about']
}
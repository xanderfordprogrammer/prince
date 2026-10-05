document.getElementById('burger')?.addEventListener('click',()=>document.querySelector('nav .links').classList.toggle('open'));
document.querySelectorAll('form.moto').forEach(f=>{
  const M=JSON.parse(f.dataset.models),T=JSON.parse(f.dataset.types),$=n=>f.querySelector(`[name=${n}]`),out=f.querySelector('.est');
  const fill=()=>{$('model').innerHTML=M[$('brand').value].map(m=>`<option>${m}</option>`).join('');type()};
  const type=()=>{$('motorcycle_type').value=T[$('model').value]||'Standard';est()};
  async function est(){
    if(!out||!$('service_id').value)return;
    const p=new URLSearchParams({service_id:$('service_id').value,brand:$('brand').value,model:$('model').value,type:$('motorcycle_type').value});
    const d=await (await fetch('/api/estimate?'+p)).json();
    out.innerHTML=`Estimated cost: <strong>₱${d.estimate}</strong> <span class="mute">(starting price ₱${d.base}; final cost depends on parts, labor and repair complexity)</span>`;
  }
  $('brand').onchange=fill;$('model').onchange=type;$('motorcycle_type').onchange=est;$('service_id')&&($('service_id').onchange=est);fill();
});

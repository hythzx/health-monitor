'use strict';
const $ = id => document.getElementById(id);
let token = '', page = 'overview', revision = '', original = '', offset = 0, loaded = false, busy = false;
const titles = {overview:['监控概览','查看服务状态，及时发现异常。'],alerts:['预警记录','追踪异常发生与服务恢复。'],config:['配置管理','查看、校验和在线更新监控配置。']};
function notice(text, error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function api(path, options={}){
  const response=await fetch('/api/'+path,{...options,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}});
  if(response.status===401){token='';$('login').showModal();throw new Error('令牌无效或已过期');}
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'请求失败');
  return data;
}
function cell(row,text,cls){const td=document.createElement('td');if(cls){const span=document.createElement('span');span.className=cls;span.textContent=text;td.append(span);}else td.textContent=text;row.append(td);}
function empty(body,cols,text){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=cols;td.className='empty';td.textContent=text;tr.append(td);body.append(tr);}
function ms(value){return typeof value==='number'?(value*1000).toFixed(0)+' ms':'—';}
function time(value){return value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';}
async function overview(){
 const data=await api('status'),services=data.services;
 $('total').textContent=services.length;
 $('healthy').textContent=services.filter(s=>s.healthy===true).length;
 $('unhealthy').textContent=services.filter(s=>s.healthy===false).length;
 $('unknown').textContent=services.filter(s=>s.healthy==null).length;
 const body=$('services');body.replaceChildren();
 services.forEach(s=>{const tr=document.createElement('tr');cell(tr,s.name);cell(tr,s.type.toUpperCase());cell(tr,s.healthy==null?'等待检查':s.healthy?'正常':'异常','badge '+(s.healthy==null?'':s.healthy?'ok':'bad'));cell(tr,ms(s.last_check?.response_time));cell(tr,time(s.last_check?.timestamp));cell(tr,s.last_check?.error_message||'—');body.append(tr);});
 if(!services.length)empty(body,6,'还没有监控服务，请在配置管理中添加。');
 const select=$('service-filter'),value=select.value;select.replaceChildren(new Option('全部服务',''));services.forEach(s=>select.add(new Option(s.name,s.name)));if(value&&!services.some(s=>s.name===value))select.add(new Option(value,value));select.value=value;
}
async function alerts(){
 const q=new URLSearchParams({service:$('service-filter').value,status:$('status-filter').value,offset,limit:50});
 const data=await api('alerts?'+q),body=$('events');body.replaceChildren();
 data.items.forEach(e=>{const tr=document.createElement('tr');cell(tr,time(e.timestamp));cell(tr,e.service);cell(tr,e.status==='UP'?'已恢复':'异常','badge '+(e.status==='UP'?'ok':'bad'));cell(tr,ms(e.response_time));cell(tr,e.message||(e.status==='UP'?'服务恢复正常':'检查失败'));body.append(tr);});
 if(!data.items.length)empty(body,5,'暂无匹配的预警记录。');
 $('event-count').textContent='共 '+data.total+' 条 · 第 '+(Math.floor(offset/50)+1)+' 页';$('prev').disabled=offset===0;$('next').disabled=offset+50>=data.total;
}
function dirty(){const changed=$('editor').value!==original;$('dirty').textContent=changed?'有未保存的修改':'已与服务器同步';return changed;}
async function loadConfig(){const data=await api('config');revision=data.revision;original=data.content;$('editor').value=original;loaded=true;dirty();}
async function refresh(){
 if(!token)return;
 try{await overview();if(page==='alerts')await alerts();$('updated').textContent='更新于 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});}
 catch(e){notice(e.message,true);$('updated').textContent='连接失败';}
}
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=async()=>{
 page=button.dataset.page;for(const name of Object.keys(titles))$(name).hidden=name!==page;
 document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('selected',b===button));
 $('page-title').textContent=titles[page][0];$('page-description').textContent=titles[page][1];notice('');
 try{if(page==='config'&&!loaded)await loadConfig();await refresh();}catch(e){notice(e.message,true);}
});
$('login').addEventListener('cancel',e=>e.preventDefault());
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;try{await api('status');$('login').close();$('token').value='';$('login-error').textContent='';await refresh();if(page==='config')await loadConfig();}catch(err){$('login-error').textContent=err.message;}};
function logout(){token='';loaded=false;original='';revision='';$('editor').value='';$('services').replaceChildren();$('events').replaceChildren();$('login').showModal();}
$('logout').onclick=logout;$('logout-mobile').onclick=logout;
$('refresh').onclick=refresh;
$('editor').oninput=dirty;
$('reload-config').onclick=async()=>{if(dirty()&&!window.confirm('放弃未保存的修改并重新加载？'))return;try{await loadConfig();notice('已重新加载配置');}catch(e){notice(e.message,true);}};
$('validate-config').onclick=async()=>{try{await api('config/validate',{method:'POST',body:JSON.stringify({content:$('editor').value})});notice('配置校验通过，可以保存');}catch(e){notice(e.message,true);}};
$('save-config').onclick=()=>{if(!loaded||busy)return; if(!dirty()){notice('配置没有变化');return;}$('confirm').showModal();};
$('cancel-save').onclick=()=>$('confirm').close();
$('confirm-save').onclick=async()=>{
 if(busy)return;busy=true;$('confirm-save').disabled=true;$('confirm').close();
 try{const content=$('editor').value;const data=await api('config',{method:'PUT',body:JSON.stringify({content,revision})});revision=data.revision;original=data.content;dirty();notice('配置已保存并生效，上一版本已备份');await refresh();}
 catch(e){notice(e.message,true);}finally{busy=false;$('confirm-save').disabled=false;}
};
for(const id of ['service-filter','status-filter'])$(id).onchange=()=>{offset=0;alerts().catch(e=>notice(e.message,true));};
$('prev').onclick=()=>{offset=Math.max(0,offset-50);alerts().catch(e=>notice(e.message,true));};
$('next').onclick=()=>{offset+=50;alerts().catch(e=>notice(e.message,true));};
window.addEventListener('beforeunload',e=>{if(loaded&&dirty()){e.preventDefault();e.returnValue='';}});
$('login').showModal();setInterval(refresh,10000);

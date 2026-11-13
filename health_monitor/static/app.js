'use strict';
const $ = id => document.getElementById(id);
let token = '', page = 'overview', revision = '', original = '', offset = 0, loaded = false, busy = false;
const titles = {overview:['监控概览','查看服务状态，及时发现异常。'],alerts:['预警记录','追踪异常发生与服务恢复。'],config:['配置管理','管理监控项、通知渠道与检查参数。'],history:['历史与日志','查询检查结果、运行错误及通知投递，管理历史保留策略。']};
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
async function loadConfig(){await loadSettings();const data=await api('config');revision=data.revision;original=data.content;$('editor').value=original;loaded=true;dirty();}
async function refresh(){
 if(!token)return;
 try{await overview();if(page==='alerts')await alerts();if(page==='history')await history();$('updated').textContent='更新于 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});}
 catch(e){notice(e.message,true);$('updated').textContent='连接失败';}
}
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=async()=>{
 page=button.dataset.page;for(const name of Object.keys(titles))$(name).hidden=name!==page;
 document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('selected',b===button));
 $('page-title').textContent=titles[page][0];$('page-description').textContent=titles[page][1];notice('');
 try{if(page==='config'&&!loaded)await loadConfig();if(page==='history')await loadRetention();await refresh();}catch(e){notice(e.message,true);}
});
$('login').addEventListener('cancel',e=>e.preventDefault());
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;try{await api('status');$('login').close();$('token').value='';$('login-error').textContent='';await refresh();if(page==='config')await loadConfig();if(page==='history')await loadRetention();}catch(err){$('login-error').textContent=err.message;}};
function logout(){token='';loaded=false;original='';revision='';$('editor').value='';settings=null;$('config-services').replaceChildren();$('config-channels').replaceChildren();$('history-items').replaceChildren();$('item-dialog').close();$('item-extra').value='';$('item-fields').replaceChildren();$('item-name').value='';$('services').replaceChildren();$('events').replaceChildren();$('login').showModal();}
$('logout').onclick=logout;$('logout-mobile').onclick=logout;
$('refresh').onclick=refresh;
$('editor').oninput=dirty;
$('reload-config').onclick=async()=>{if(dirty()&&!window.confirm('放弃未保存的修改并重新加载？'))return;try{await loadConfig();notice('已重新加载配置');}catch(e){notice(e.message,true);}};
$('validate-config').onclick=async()=>{try{await api('config/validate',{method:'POST',body:JSON.stringify({content:$('editor').value})});notice('配置校验通过，可以保存');}catch(e){notice(e.message,true);}};
$('save-config').onclick=()=>{if(!loaded||busy)return; if(!dirty()){notice('配置没有变化');return;}$('confirm').showModal();};
$('cancel-save').onclick=()=>$('confirm').close();
$('confirm-save').onclick=async()=>{
 if(busy)return;busy=true;$('confirm-save').disabled=true;$('confirm').close();
 try{const content=$('editor').value;const data=await api('config',{method:'PUT',body:JSON.stringify({content,revision})});revision=data.revision;original=data.content;dirty();notice('配置已保存并生效');await loadSettings();await refresh();}
 catch(e){notice(e.message,true);}finally{busy=false;$('confirm-save').disabled=false;}
};
for(const id of ['service-filter','status-filter'])$(id).onchange=()=>{offset=0;alerts().catch(e=>notice(e.message,true));};
$('prev').onclick=()=>{offset=Math.max(0,offset-50);alerts().catch(e=>notice(e.message,true));};
$('next').onclick=()=>{offset+=50;alerts().catch(e=>notice(e.message,true));};
window.addEventListener('beforeunload',e=>{if(loaded&&dirty()){e.preventDefault();e.returnValue='';}});
$('login').showModal();setInterval(refresh,10000);

let settings=null, historyOffset=0, editing=null;
const serviceFields={
 restful:[['url','检查地址','url'],['method','请求方法'],['expected_status','期望状态码','number'],['timeout','超时（秒）','number'],['check_interval','检查间隔（秒）','number']],
 redis:[['host','主机'],['port','端口','number'],['password','密码','password'],['database','数据库编号','number']],
 mysql:[['host','主机'],['port','端口','number'],['username','用户名'],['password','密码','password'],['database','数据库']],
 mongodb:[['host','主机'],['port','端口','number'],['username','用户名'],['password','密码','password'],['database','认证数据库']],
 emqx:[['host','主机'],['port','端口','number'],['username','用户名'],['password','密码','password'],['client_id','客户端 ID']]
};
const channelFields={
 http:[['url','Webhook 地址','url'],['method','请求方法'],['template','消息模板（可选）','textarea']],
 email:[['smtp_server','SMTP 主机'],['smtp_port','SMTP 端口','number'],['username','用户名'],['password','密码','password'],['from_email','发件邮箱','email'],['to_emails','收件邮箱（逗号分隔）','list'],['use_tls','使用 STARTTLS','checkbox'],['use_ssl','使用 SSL','checkbox']],
 aliyun_sms:[['access_key_id','Access Key ID'],['access_key_secret','Access Key Secret','password'],['region','区域'],['sign_name','短信签名'],['template_code','模板编号'],['phone_numbers','手机号（逗号分隔）','list']]
};
function fieldsFor(group,type){const fields=(group==='services'?serviceFields:channelFields)[type]||[];return group==='services'&&type!=='restful'?[...fields,['timeout','超时（秒）','number'],['check_interval','检查间隔（秒）','number']]:fields;}
function actionButton(label,handler){const b=document.createElement('button');b.textContent=label;b.onclick=()=>handler().catch(e=>notice(e.message,true));return b;}
async function loadSettings(){settings=await api('settings');renderSettings();}
function renderSettings(){
 for(const [group,id] of [['services','config-services'],['alerts','config-channels']]){
  const body=$(id);body.replaceChildren();
  const entries=group==='services'?Object.entries(settings.config.services||{}):(settings.config.alerts||[]).map(v=>[v.name,v]);
  entries.forEach(([name,value])=>{const tr=document.createElement('tr');cell(tr,name);cell(tr,value.type.toUpperCase());if(group==='services')cell(tr,(value.check_interval||settings.config.global?.check_interval||30)+' 秒');const td=document.createElement('td');td.append(actionButton('编辑',async()=>openItem(group,name)),actionButton('删除',async()=>{
   if(!window.confirm('删除「'+name+'」？历史记录会保留。'))return;
   const config=structuredClone(settings.config);if(group==='services')delete config.services[name];else config.alerts=config.alerts.filter(a=>a.name!==name);
   await saveDocument(config);notice('已删除并生效');
  }));tr.append(td);body.append(tr);});if(!entries.length)empty(body,group==='services'?4:3,'尚未添加，可通过右上角按钮创建。');
 }
 const global=settings.config.global||{};$('global-interval').value=global.check_interval||30;$('global-concurrency').value=global.max_concurrent_checks||10;$('global-level').value=global.log_level||'INFO';
}
async function saveDocument(config){
 if(loaded&&dirty()&&!window.confirm('YAML 有未保存的修改，继续将放弃这些修改。'))throw new Error('已取消保存');
 settings=await api('settings',{method:'PUT',body:JSON.stringify({config,revision:settings.revision})});renderSettings();
 const yaml=await api('config');revision=yaml.revision;original=yaml.content;$('editor').value=original;loaded=true;dirty();await refresh();
}
function openItem(group,name=''){
 editing={group,name};const value=group==='services'?settings.config.services?.[name]:settings.config.alerts?.find(a=>a.name===name);
 $('item-title').textContent=(name?'编辑':'添加')+(group==='services'?'监控项':'通知渠道');$('item-name').value=name;$('item-name').readOnly=!!name;
 const types=Object.keys(group==='services'?serviceFields:channelFields);$('item-type').replaceChildren(...types.map(t=>new Option(t.toUpperCase(),t)));$('item-type').value=value?.type||types[0];$('item-type').disabled=!!name;$('item-error').textContent='';
 renderFields(value||defaultItem(group,$('item-type').value));$('item-dialog').showModal();
}
function defaultItem(group,type){if(group==='alerts'){return type==='http'?{method:'POST'}:type==='email'?{smtp_port:587,use_tls:true,use_ssl:false}:{region:'cn-hangzhou'};}return type==='restful'?{method:'GET',expected_status:200,timeout:5}:{port:{redis:6379,mysql:3306,mongodb:27017,emqx:1883}[type],timeout:5};}
function renderFields(value){
 const body=$('item-fields');body.replaceChildren();const extra=structuredClone(value);delete extra.type;delete extra.name;
 for(const [key,label,type='text'] of fieldsFor(editing.group,$('item-type').value)){
  const field=document.createElement('label');field.textContent=label;const input=document.createElement(type==='textarea'?'textarea':'input');input.id='field-'+key;input.dataset.key=key;input.dataset.kind=type;
  if(type!=='textarea')input.type=type==='list'?'text':type;
  if(type==='checkbox')input.checked=!!value[key];else input.value=type==='list'?(value[key]||[]).join(', '):(value[key]??'');
  if(type==='number'){input.step='any';input.min=key==='database'?'0':'1';}
  field.append(input);body.append(field);delete extra[key];
 }
 $('item-extra').value=JSON.stringify(extra,null,2);
}
$('item-type').onchange=()=>renderFields(defaultItem(editing.group,$('item-type').value));
$('add-service').onclick=()=>openItem('services');$('add-channel').onclick=()=>openItem('alerts');$('cancel-item').onclick=()=>$('item-dialog').close();
$('item-dialog').addEventListener('close',()=>{$('item-extra').value='';$('item-fields').replaceChildren();});
$('item-form').onsubmit=async e=>{e.preventDefault();$('submit-item').disabled=true;try{
 const name=$('item-name').value.trim(),type=$('item-type').value;const value=JSON.parse($('item-extra').value||'{}');if(!value||Array.isArray(value)||typeof value!=='object')throw new Error('其他配置须为 JSON 对象');
 for(const input of $('item-fields').querySelectorAll('[data-key]')){const {key,kind}=input.dataset;if(kind==='checkbox')value[key]=input.checked;else if(input.value!=='')value[key]=kind==='number'?Number(input.value):kind==='list'?input.value.split(/[,，]/).map(v=>v.trim()).filter(Boolean):input.value;else delete value[key];}
 value.type=type;const config=structuredClone(settings.config);
 if(editing.group==='services'){config.services||={};if(!editing.name&&Object.hasOwn(config.services,name))throw new Error('监控项名称已存在');Object.defineProperty(config.services,name,{value,enumerable:true,writable:true,configurable:true});}
 else{config.alerts||=[];if(!editing.name&&config.alerts.some(a=>a.name===name))throw new Error('通知渠道名称已存在');value.name=name;const index=config.alerts.findIndex(a=>a.name===name);if(index<0)config.alerts.push(value);else config.alerts[index]=value;}
 await saveDocument(config);$('item-dialog').close();$('item-extra').value='';$('item-fields').replaceChildren();notice('已保存并生效');
 }catch(err){$('item-error').textContent=err.message;}finally{$('submit-item').disabled=false;}};
$('global-form').onsubmit=async e=>{e.preventDefault();try{const config=structuredClone(settings.config);config.global={...config.global,check_interval:Number($('global-interval').value),max_concurrent_checks:Number($('global-concurrency').value),log_level:$('global-level').value};await saveDocument(config);notice('全局设置已生效');}catch(err){notice(err.message,true);}};
async function history(){
 const q=new URLSearchParams({service:$('history-service').value,search:$('history-search').value,offset:historyOffset,limit:50});for(const key of ['since','until']){const value=$('history-'+key).value;if(value)q.set(key,new Date(value).toISOString());}
 const data=await api('history/'+$('history-kind').value+'?'+q),body=$('history-items');body.replaceChildren();data.items.forEach(item=>{const tr=document.createElement('tr');cell(tr,time(item.timestamp));cell(tr,item.service||item.logger||'—');cell(tr,item.channel?item.channel+' / '+item.status:item.level||item.status);cell(tr,item.message||'检查正常');body.append(tr);});if(!data.items.length)empty(body,4,'暂无匹配记录');$('history-count').textContent='共 '+data.total+' 条 · 第 '+(historyOffset/50+1)+' 页';$('history-prev').disabled=historyOffset===0;$('history-next').disabled=historyOffset+50>=data.total;
}
$('query-history').onclick=()=>{historyOffset=0;history().catch(e=>notice(e.message,true));};$('history-kind').onchange=$('query-history').onclick;
$('history-prev').onclick=()=>{historyOffset=Math.max(0,historyOffset-50);history().catch(e=>notice(e.message,true));};$('history-next').onclick=()=>{historyOffset+=50;history().catch(e=>notice(e.message,true));};
async function loadRetention(){const data=await api('retention');$('retention-days').value=data.retention_days;$('retention-rows').value=data.max_rows;}
$('retention-form').onsubmit=async e=>{e.preventDefault();try{await api('retention',{method:'PUT',body:JSON.stringify({retention_days:Number($('retention-days').value),max_rows:Number($('retention-rows').value)})});notice('保留策略已保存，下次定时清理生效');}catch(err){notice(err.message,true);}};
$('cleanup-history').onclick=async()=>{try{const value=$('cleanup-before').value;if(!value)throw new Error('请先选择清理截止时间');if(!window.confirm('确定删除所选时间之前的历史记录？此操作无法恢复。'))return;const data=await api('history/cleanup',{method:'POST',body:JSON.stringify({kind:$('cleanup-kind').value,before:new Date(value).toISOString(),confirm:true})});notice('已清理 '+Object.values(data.deleted).reduce((a,b)=>a+b,0)+' 条历史记录');historyOffset=0;await history();}catch(err){notice(err.message,true);}};

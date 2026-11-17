"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="xpl-token"]').content;
const state = {catalog:null,runs:[],view:"overview",selected:null,logOffset:0,logText:"",busy:false,detail:null};
const labels = {queued:"等待执行",running:"进行中",cancelling:"停止中",succeeded:"已完成",failed:"失败",cancelled:"已取消",interrupted:"已中断"};
const form = $("run-form");
const field = (name) => form.elements.namedItem(name);
const element = (tag, cls, text) => {const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
function icon(name){const svg=document.createElementNS("http://www.w3.org/2000/svg","svg"),use=document.createElementNS(svg.namespaceURI,"use");svg.setAttribute("class","icon");svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("aria-hidden","true");use.setAttribute("href",`#icon-${name}`);svg.append(use);return svg;}
function toast(message){$("toast").textContent=message;$("toast").hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$("toast").hidden=true,4500);}
async function api(path, options={}){const response=await fetch(path,{...options,headers:{"X-XPL-Token":token,"Content-Type":"application/json",...(options.headers||{})}});const data=await response.json();if(!response.ok)throw new Error(data.error||"请求失败");return data;}
function badge(status){return element("span",`badge ${status}`,labels[status]||({ready:"已配置",pending:"待配置"}[status])||status);}
function localTime(value){return new Date(value).toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});}
function resultText(run){const m=run.metrics;if("success" in m)return m.success===null?"未知":m.success?"成功":"失败";if(m.protocol_total)return `${m.protocol_passed}/${m.protocol_total} 通过`;if(m.complete===false)return "未完成";if(m.success_rate!==undefined)return `${(m.success_rate*100).toFixed(1)}%${m.budget==="smoke"?" · 快速检查":""}`;return run.status==="succeeded"?"未提供指标":"—";}
function renderStats(){
  const active=state.runs.filter(r=>["running","queued","cancelling"].includes(r.status)).length;
  $("stat-active").replaceChildren(document.createTextNode(String(active)),element("span","","项运行"));
  $("stat-total").replaceChildren(document.createTextNode(String(state.runs.length)),element("span","","项记录"));
  $("nav-count").textContent=String(state.runs.length);
  const completed=state.runs.filter(r=>r.status==="succeeded").length;
  $("stat-completed").textContent=completed?`${completed} 项已完成`:"暂无记录";
  const latest=state.runs.find(r=>r.status==="succeeded"&&r.metrics.real_evaluation&&r.metrics.complete&&r.metrics.budget==="50_trials_per_task"&&r.metrics.report_scope==="libero_four_suites"&&Number.isFinite(r.metrics.success_rate));
  $("stat-rate").textContent=latest?`${(100*latest.metrics.success_rate).toFixed(1)}%`:"—";
  $("stat-rate-note").textContent=latest?`${latest.parameters.policy} · seed ${latest.parameters.seed}`:"暂无完整评测";
  $("stat-policies").replaceChildren(document.createTextNode(String(state.catalog.policies.length)),element("span","","个模型入口"));
}
function renderRuns(){const query=$("run-search").value.trim().toLowerCase();const filter=$("status-filter").value;let rows=state.runs.filter(r=>`${r.parameters.label} ${r.parameters.policy} ${r.parameters.task} ${r.id}`.toLowerCase().includes(query));if(filter!=="all")rows=rows.filter(r=>filter==="failed"?["failed","interrupted"].includes(r.status):filter==="running"?["running","cancelling"].includes(r.status):r.status===filter);if(state.view==="overview")rows=rows.slice(0,8);$("run-rows").replaceChildren();for(const r of rows){const p=r.parameters;const tr=element("tr");tr.tabIndex=0;tr.setAttribute("aria-label",`查看 ${p.label||p.policy} 运行详情`);const a=element("td");a.append(element("div","run-name",p.label||`${p.policy} · ${p.task}`),element("div","run-meta",`${p.policy} / ${r.id.slice(0,8)}`));const b=element("td");b.append(element("div","run-task",p.task),element("div","subtle",`${p.benchmark==="protocol"?"协议检查":p.benchmark} · seed ${p.seed}`));const c=element("td");c.append(badge(r.status));const d=element("td","result-rate",resultText(r));if(p.kind==="debug")d.append(element("div","subtle","CPU"));const e=element("td","",localTime(r.created_at));const f=element("td");const button=element("button","row-link");button.append(icon("arrow"));button.setAttribute("aria-label","打开运行详情");f.append(button);tr.append(a,b,c,d,e,f);tr.onclick=()=>openDetail(r.id);tr.onkeydown=e=>{if(e.key==="Enter")openDetail(r.id);};$("run-rows").append(tr);}$("empty-state").hidden=rows.length>0;$("empty-state").querySelector("h3").textContent=state.runs.length?"没有匹配的运行记录":"暂无运行记录";$("record-count").textContent=`${rows.length} / ${state.runs.length} 条记录`;}
function renderCatalog(){
  const cards=$("benchmark-cards");cards.replaceChildren();
  for(const b of state.catalog.benchmarks){
    const card=element("button","benchmark-card"),top=element("div","benchmark-top");
    const mark=element("span","benchmark-initial");mark.append(icon({protocol:"activity",libero:"boxes",RoboDojo:"robot",RoboTwin:"robot",real:"chip"}[b.id]));
    top.append(mark,element("strong","benchmark-name",b.name),badge(b.ready?"ready":"pending"));
    const info=b.id==="libero"?"4 Suites · 40 任务":b.id==="protocol"?"CPU":b.id==="real"?`${b.tasks.length} 个配置`:`${(b.registered_tasks||[]).length} 个已登记任务`;
    card.append(top,element("p","benchmark-description",info));
    card.onclick=()=>openForm({benchmark:b.id,policy:b.policies[0]||state.catalog.policies[0].id,task:b.tasks[0]||""});cards.append(card);
  }
  const grid=$("policy-grid");grid.replaceChildren();
  for(const p of state.catalog.policies){
    const card=element("article","policy-card");card.append(element("h3","",p.id),element("p","",`${p.checkpoints.length} 个 checkpoint`));
    const compatible=state.catalog.benchmarks.filter(b=>b.policies.includes(p.id)&&b.ready);
    card.append(badge(compatible.length?"ready":"pending"));
    if(compatible.length)card.append(element("p","",compatible.map(b=>b.name).join(" · ")));
    grid.append(card);
  }
}
async function refresh(){try{if(!state.catalog){state.catalog=await api("/api/catalog");renderCatalog();}state.runs=(await api("/api/runs")).runs;renderStats();renderRuns();$("connection").classList.remove("offline");$("connection").replaceChildren(element("i"),document.createTextNode("服务在线"));$("error-banner").hidden=true;if($("detail-dialog").open&&state.selected)await refreshDetail();}catch(error){$("connection").classList.add("offline");$("connection").replaceChildren(element("i"),document.createTextNode("连接已断开"));$("error-banner").textContent=`连接失败：${error.message}`;$("error-banner").hidden=false;}}
function selectOptions(select,items,value){select.replaceChildren();for(const item of items){const option=element("option","",typeof item==="string"?item:item.label);option.value=typeof item==="string"?item:item.id;select.append(option);}if(items.length===0){const option=element("option","","尚未配置");option.value="";select.append(option);}if(value!==undefined&&[...select.options].some(o=>o.value===value))select.value=value;}
function updateForm(task,checkpoint){
  const b=state.catalog.benchmarks.find(b=>b.id===field("benchmark").value);
  const p=state.catalog.policies.find(p=>p.id===field("policy").value);
  selectOptions(field("task"),b.task_options||b.tasks,task??field("task").value);
  selectOptions(field("checkpoint"),p.checkpoints,checkpoint??field("checkpoint").value);
  const noCheckpoint=["protocol","real"].includes(b.id);
  $("checkpoint-field").hidden=noCheckpoint;field("checkpoint").required=!noCheckpoint;
  $("gpu-fields").hidden=b.id==="protocol"||b.id==="real";
  $("standard-fields").hidden=!["RoboDojo","RoboTwin"].includes(b.id);
  $("max-steps-field").hidden=b.id!=="real";
  $("episodes-label").textContent=b.id==="protocol"?"协议检查次数":"每任务 Episodes";
  field("episodes").closest("label").hidden=["RoboDojo","RoboTwin","real"].includes(b.id);
  const gaps=[...b.gaps];
  if(!b.policies.includes(p.id))gaps.unshift("当前模型未接入此环境");
  if(!noCheckpoint&&!p.checkpoints.length)gaps.push("无可用 checkpoint");
  if(["RoboDojo","RoboTwin"].includes(b.id)&&!state.catalog.policy_environments[p.id])gaps.push(`尚未配置 ${p.id} 的策略环境`);
  $("preflight").classList.toggle("blocked",gaps.length>0);
  $("preflight").hidden=!gaps.length;
  $("preflight").textContent=gaps.join("\n");
  $("submit-run").disabled=gaps.length>0;
  updateBudget();
}
function updateBudget(){
  const b=state.catalog.benchmarks.find(b=>b.id===field("benchmark").value);
  if(b.id==="libero"){
    const selection=field("task").value;
    const suites=selection==="all"?Object.keys(b.suite_task_counts).filter(x=>x!=="libero_90"):selection==="all_with_90"?Object.keys(b.suite_task_counts):[selection];
    const tasks=suites.reduce((sum,suite)=>sum+(b.suite_task_counts[suite]||0),0), trials=Number(field("episodes").value);
    $("form-hint").textContent=`${suites.length} Suites · ${tasks} 任务 × ${trials} 次 · ${tasks*trials} episodes${trials<50?" · 快速检查":""}`;
  }else if(["RoboDojo","RoboTwin"].includes(b.id)){
    const count=field("task").value==="all"?b.registered_tasks.length:1;
    $("form-hint").textContent=`${count} 个已登记任务 · 环境默认预算`;
  }else $("form-hint").textContent="";
  $("form-hint").hidden=!$("form-hint").textContent;
}
function openForm(values={}){
  if(!state.catalog)return;form.reset();$("form-error").hidden=true;
  const defaults={...state.catalog.defaults,...values};
  selectOptions(field("policy"),state.catalog.policies.map(p=>p.id),defaults.policy);
  selectOptions(field("benchmark"),state.catalog.benchmarks.map(b=>({id:b.id,label:b.name+(b.ready?"":" · 待配置")})),defaults.benchmark);
  const b=state.catalog.benchmarks.find(b=>b.id===field("benchmark").value);
  if(values.episodes===undefined)defaults.episodes=b.default_episodes||3;
  for(const key of ["label","seed","episodes","policy_gpu","env_gpu","robot","action_type","max_steps"]){if(defaults[key]!==undefined&&defaults[key]!==null)field(key).value=defaults[key];}
  updateForm(values.task??b.default_task??defaults.task,defaults.checkpoint);$("run-dialog").showModal();
}
form.onsubmit=async event=>{event.preventDefault();const button=$("submit-run");button.disabled=true;$("form-error").hidden=true;const data=Object.fromEntries(new FormData(form));for(const key of ["seed","episodes","policy_gpu","env_gpu","max_steps"])data[key]=Number(data[key]);try{const run=await api("/api/runs",{method:"POST",body:JSON.stringify(data)});$("run-dialog").close();toast("评测已加入队列");await refresh();await openDetail(run.id);}catch(error){$("form-error").textContent=error.message;$("form-error").hidden=false;button.disabled=false;}};
field("policy").onchange=()=>updateForm();
field("benchmark").onchange=()=>{
  const b=state.catalog.benchmarks.find(b=>b.id===field("benchmark").value);
  field("episodes").value=b.default_episodes||3;
  if(b.policies.length&&!b.policies.includes(field("policy").value))field("policy").value=b.policies[0];
  updateForm(b.default_task);
};
field("task").onchange=updateBudget;field("episodes").oninput=updateBudget;
function activateTab(name){document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));for(const tab of ["logs","params","files"])$("tab-"+tab).hidden=tab!==name;if(name==="files")refreshArtifacts();}
async function openDetail(id){state.selected=id;state.logOffset=0;state.logText="";$("log-output").textContent="等待进程输出…";activateTab("logs");$("detail-dialog").showModal();await refreshDetail();}
async function refreshDetail(){const id=state.selected;const run=await api(`/api/runs/${id}`);if(id!==state.selected)return;state.detail=run;renderEvaluationResults(run);const p=run.parameters;$("detail-id").textContent=`RUN / ${run.id}`;$("detail-title").textContent=p.label||`${p.policy} · ${p.task}`;$("detail-description").textContent=`${p.kind==="debug"?"CPU 协议检查":p.benchmark} · ${localTime(run.created_at)} · revision ${run.revision}`;$("detail-status").replaceChildren(badge(run.status));$("detail-stage").textContent=run.stage;$("cancel-run").hidden=!["queued","running","cancelling"].includes(run.status);$("cancel-run").disabled=run.status==="cancelling";$("detail-error").hidden=!run.error;$("detail-error").textContent=run.error||"";$("parameter-output").textContent=JSON.stringify(p,null,2);const metrics=$("detail-metrics");metrics.replaceChildren();for(const [label,value] of [["结果",resultText(run)],["模型",p.policy],["随机种子",p.seed],["预算",p.benchmark==="real"?`${p.max_steps} 控制步`:p.episodes===null?"由基准配置决定":`${p.episodes} ${p.kind==="debug"?"次检查":"episodes / task"}${p.expected_episodes?` · 共 ${p.expected_episodes} 次`:""}`]]){const item=element("div","detail-metric");item.append(element("span","",label),element("strong","",String(value)));metrics.append(item);}const log=await api(`/api/runs/${id}/logs?offset=${state.logOffset}`);if(id!==state.selected)return;state.logOffset=log.offset;if(log.text){state.logText=(state.logText+log.text).slice(-500000);$("log-output").textContent=state.logText;if($("autoscroll").checked)$("log-output").scrollTop=$("log-output").scrollHeight;}if(!$("tab-files").hidden)await refreshArtifacts();}
async function refreshArtifacts(){if(!state.selected)return;const id=state.selected;const result=await api(`/api/runs/${id}/artifacts`);if(id!==state.selected)return;$("artifact-list").replaceChildren();if(!result.files.length)$("artifact-list").append(element("p","subtle","暂无文件"));for(const file of result.files){const row=element("div","artifact");const link=element("a","",file.path);link.href=`/api/runs/${id}/files/${file.path.split("/").map(encodeURIComponent).join("/")}`;link.target="_blank";link.rel="noopener";row.append(link,element("span","",file.size<1024?`${file.size} B`:`${(file.size/1024).toFixed(1)} KB`));$("artifact-list").append(row);}}
$("cancel-run").onclick=async()=>{try{await api(`/api/runs/${state.selected}/cancel`,{method:"POST",body:"{}"});toast("正在停止");await refresh();}catch(error){toast(error.message);}};
$("clone-run").onclick=()=>{const values=state.detail.parameters;$("detail-dialog").close();openForm({...values,label:values.label?values.label+" · 重跑":""});};
document.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>$(b.dataset.close).close());document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));
document.querySelectorAll(".nav-item").forEach(button=>button.onclick=()=>{state.view=button.dataset.view;document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b===button));const title={overview:"评测概览",history:"运行记录",resources:"资源与接入"}[state.view];$("page-title").textContent=title;$("breadcrumb-view").textContent=title;$("stats-grid").hidden=state.view==="resources";$("content-grid").hidden=state.view==="resources";$("environment-panel").hidden=state.view==="history";$("content-grid").classList.toggle("history",state.view==="history");$("resources-panel").hidden=state.view!=="resources";$("table-title").textContent=state.view==="history"?"全部运行记录":"最近运行";renderRuns();});
$("run-search").oninput=renderRuns;$("status-filter").onchange=renderRuns;$("new-run-btn").onclick=()=>openForm();$("empty-start").onclick=()=>openForm();$("quick-check").onclick=()=>openForm({benchmark:"protocol",policy:"demo_policy",task:"interface_check"});$("refresh-btn").onclick=async()=>{state.catalog=null;await refresh();toast("已刷新");};
refresh();setInterval(()=>{if(!state.busy){state.busy=true;refresh().finally(()=>state.busy=false);}},1500);

function renderEvaluationResults(run){
  const m=run.metrics, box=$("evaluation-results"), body=$("evaluation-rows");
  body.replaceChildren();
  const suites=m.suites||[], tasks=m.coverage==="configured_tasks"?(m.tasks||[]):[];
  box.hidden=!suites.length&&!tasks.length;
  for(const unit of [...suites,...tasks]){
    const row=element("tr");
    const label=unit.suite||unit.task;
    for(const value of [label,unit.episodes!==undefined?`${unit.successes} / ${unit.episodes}`:"未提供统一指标",unit.success_rate!==undefined?`${(100*unit.success_rate).toFixed(1)}%`:"—",unit.suite?(m.budget==="smoke"?"快速检查":unit.suite==="libero_90"?"扩展 / 预训练集":"50 次 / 任务"):"已登记任务 / 外部预算"]){row.append(element("td","",value));}
    body.append(row);
  }
  const note=$("evaluation-note");
  note.textContent=m.complete===false?`已完成 ${suites.length||tasks.length} / ${(m.expected_suites||m.expected_tasks||[]).length} 项`:m.weighted_success_rate!==undefined&&Math.abs(m.weighted_success_rate-m.success_rate)>1e-8?`Suite 平均 ${(m.success_rate*100).toFixed(1)}% · Episode 平均 ${(m.weighted_success_rate*100).toFixed(1)}%`:"";
  note.hidden=!note.textContent;
}

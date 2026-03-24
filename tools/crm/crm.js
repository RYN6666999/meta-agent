/* ═══════════════════════════════════════
   UTILITY
═══════════════════════════════════════ */
function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2,7)}

function toast(msg,dur=2200){
  const t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),dur);
}

/* ═══════════════════════════════════════
   DATA MODEL
═══════════════════════════════════════ */
const STATUS_LABELS={green:'高意願',yellow:'觀察中',red:'冷淡',gray:'無效',null:'根節點'};
const STATUS_ORDER=['green','yellow','red','gray'];

function newNode(){
  return{
    id:uid(),parentId:null,x:0,y:0,
    nodeType:'contact',  // 'contact' | 'note'
    name:'新聯繫人',status:'yellow',collapsed:false,
    info:{
      age:'',zodiac:'',hometown:'',personality:'',interests:'',
      howMet:'',background:'',
      currentJob:'',jobDuration:'',prevJob:'',prevJobLevel:'',
      income:'',salaryTransfer:'',hasProperty:'',familyProperty:'',
      hasInvestment:'',hasInsurance:'',creditCard:'',debt:'',
      invitationMethod:'',knowsVenueFee:'',knowsTuition:'',
      keyQuestions:'',needs:[],canDecide:'',payOnSite:'',
      eventDate:'',eventName:'',referrer:'',recommender:'',
      formNotes:'',
      company:'',phone:'',email:'',lastContact:'',
      source:'',priority:'',tags:[],notes:'',
      role:'',regions:[]
    }
  };
}

let nodes=[];
let events=[];
let tasks=[];
let chatHistory=[];

/* ═══════════════════════════════════════
   UNDO STACK（僅 nodes，最多 50 步）
═══════════════════════════════════════ */
const UNDO_MAX=50;
let undoStack=[];
let _undoRestoring=false;

function pushUndo(){
  if(_undoRestoring)return;
  undoStack.push(JSON.stringify(nodes));
  if(undoStack.length>UNDO_MAX) undoStack.shift();
}

function undoLast(){
  if(!undoStack.length){toast('沒有可恢復的動作');return;}
  _undoRestoring=true;
  nodes=JSON.parse(undoStack.pop());
  saveData(); // persist restored state
  _undoRestoring=false;
  renderNodes();
  deselect();
  toast('↩ 已恢復上一動作');
}

/* ── Migration from crm-v2 (recursive tree) ── */
function migrateOldTree(treeNode,parentId=null,result=[]){
  const{children,...rest}=treeNode;
  result.push({...rest,parentId,x:undefined,y:undefined});
  (children||[]).forEach(c=>migrateOldTree(c,treeNode.id,result));
  return result;
}

function loadData(){
  try{
    const raw=localStorage.getItem(STORE.K.nodes);
    if(raw){nodes=JSON.parse(raw);}
    else{
      const old=localStorage.getItem('crm-v2'); // legacy migration
      if(old){
        const tree=JSON.parse(old);
        nodes=migrateOldTree(tree);
        toast('已從舊格式遷移資料');
      } else {
        nodes=buildDemoData();
      }
    }
  }catch(e){nodes=buildDemoData();}
  if(!nodes||nodes.length===0){
    const starter=newNode('點擊編輯此節點');
    starter.x=200; starter.y=100; starter.parentId=null;
    nodes=[starter];
    STORE.saveNodes();
  }
  try{events=JSON.parse(localStorage.getItem(STORE.K.events)||'[]');}catch(e){events=[];}
  try{tasks=JSON.parse(localStorage.getItem(STORE.K.tasks)||'[]');}catch(e){tasks=[];}
  try{chatHistory=JSON.parse(localStorage.getItem(STORE.K.chat)||'[]');}catch(e){chatHistory=[];}
}

function saveData(){ pushUndo(); STORE.saveNodes(); }

function findNode(id){return nodes.find(n=>n.id===id)||null;}
function getChildren(id){return nodes.filter(n=>n.parentId===id);}
function getRoots(){return nodes.filter(n=>!n.parentId);}

function isHidden(id){
  const n=findNode(id);
  if(!n)return false;
  if(!n.parentId)return false;
  const p=findNode(n.parentId);
  if(!p)return false;
  if(p.collapsed)return true;
  return isHidden(p.id);
}

function gatherSubtree(id){
  const ids=[id];
  const kids=getChildren(id);
  kids.forEach(c=>gatherSubtree(c.id).forEach(x=>ids.push(x)));
  return ids;
}

/* ═══════════════════════════════════════
   CALC — Pure Calculation Layer
   IN: data objects  OUT: numbers/objects
   FORBIDDEN: no DOM, no localStorage
═══════════════════════════════════════ */
const CALC = {
  // IN: sale{saleType,product,amount,batchby,samerank}, myRate:number  OUT: number
  saleIncome(sale, myRate) {
    if (sale.saleType === 'transfer') return sale.amount;
    if (sale.saleType === 'bonus') return sale.amount;
    const isBatch = sale.product === 'asst_mgr_pkg' || sale.product === 'manager_pkg';
    if (isBatch && sale.batchby === 'student')
      return sale.amount * Math.max(0, myRate - (BATCH_ANCHORS[sale.product] || 0));
    if (sale.samerank === 'samerank') return sale.amount * 0.01;
    return sale.amount * myRate;
  },
  // IN: salesData[], myRate, monthPrefix "2026-03"
  // OUT: {gross, transferTotal, income, tax, net, newCount, totalCount, sorted}
  monthSummary(salesData, myRate, monthPrefix) {
    const ms       = salesData.filter(s => s.date && s.date.startsWith(monthPrefix));
    const newSales = ms.filter(s => s.saleType === 'new');
    const transfers= ms.filter(s => s.saleType === 'transfer');
    const bonuses  = ms.filter(s => s.saleType === 'bonus');
    const gross        = newSales.reduce((a,s) => a + s.amount, 0);
    const transferTotal= transfers.reduce((a,s) => a + s.amount, 0);
    const bonusTotal   = bonuses.reduce((a,s) => a + s.amount, 0);
    const income = ms.reduce((a,s) => a + CALC.saleIncome(s, myRate), 0);
    const tax    = income * SALES_TAX;
    const net    = income - tax;
    const sorted = [...ms].sort((a,b) => b.date.localeCompare(a.date));
    return { gross, transferTotal, bonusTotal, income, tax, net, newCount: newSales.length, bonusCount: bonuses.length, totalCount: ms.length, sorted };
  },
  // IN: dailyReports{}, monthKey "2026-03"  OUT: {invite,calls,forms,followup,close}
  monthActuals(dailyReports, monthKey) {
    const t = { invite:0, calls:0, forms:0, followup:0, close:0, consult:0 };
    Object.entries(dailyReports).forEach(([date,r]) => {
      if (date.startsWith(monthKey)) {
        t.invite   += (r['act-invite']   || 0);
        t.calls    += (r['act-calls']    || 0);
        t.forms    += (r['act-forms']    || 0);
        t.followup += (r['act-followup'] || 0);
        t.close    += (r['act-close']    || 0);
        t.consult  += (r['act-consult']  || 0);
      }
    });
    return t;
  },
  // IN: actuals{}, goals{'mg-invite':n,...}
  // OUT: [{k, label, goalK, actual, goal, pct, full}]
  progressItems(actuals, goals) {
    return [
      { k:'invite',   label:'邀約', goalK:'mg-invite'   },
      { k:'calls',    label:'電話', goalK:'mg-calls'    },
      { k:'forms',    label:'問卷', goalK:'mg-forms'    },
      { k:'followup', label:'跟進', goalK:'mg-followup' },
      { k:'close',    label:'成交', goalK:'mg-close'    },
      { k:'consult',  label:'協談', goalK:'mg-consult'  },
    ].map(d => {
      const goal   = goals[d.goalK] || 0;
      const actual = actuals[d.k]   || 0;
      const pct    = goal ? Math.min(100, Math.round(actual / goal * 100)) : 0;
      const full   = goal > 0 && actual >= goal;
      return { ...d, actual, goal, pct, full };
    });
  },
  // IN: salesData[], myRate, monthPrefix, salesTarget  OUT: {income, pct, full}
  salesProgress(salesData, myRate, monthPrefix, salesTarget) {
    const income = salesData
      .filter(s => s.date && s.date.startsWith(monthPrefix))
      .reduce((a,s) => a + CALC.saleIncome(s, myRate), 0);
    const pct  = salesTarget ? Math.min(100, Math.round(income / salesTarget * 100)) : 0;
    const full = salesTarget > 0 && income >= salesTarget;
    return { income, pct, full };
  },
};

/* ═══════════════════════════════════════
   STORE — Data Layer
   Single source of truth for localStorage keys
   FORBIDDEN: no DOM, no calculations
═══════════════════════════════════════ */
const STORE = {
  K: {
    nodes:               'crm-v3',
    events:              'crm-events',
    tasks:               'crm-tasks',
    chat:                'crm-chat',
    sales:               'crm-sales',
    dailyReports:        'crm-daily-reports',
    monthlyGoals:        'crm-monthly-goals',
    monthlySalesTargets: 'crm-monthly-sales-targets',
    theme:               'crm-theme',
    shortcuts:           'crm-shortcuts',
    docs:                'crm-docs',
    cmdMode:             'crm-cmd-mode',
    cmdWhite:            'crm-cmd-white',
    cmdBlack:            'crm-cmd-black',
    profileRank:         'crm-profile-rank',
    obsidianPath:        'crm-obsidian-path',
    aiProvider:          'crm-ai-provider',
    aiModel:             'crm-ai-model',
    apiKey:              'crm-apikey',
    aiEndpoint:          'crm-ai-endpoint',
  },
  saveNodes()               { localStorage.setItem(STORE.K.nodes,               JSON.stringify(nodes)); },
  saveEvents()              { localStorage.setItem(STORE.K.events,              JSON.stringify(events)); },
  saveTasks()               { localStorage.setItem(STORE.K.tasks,               JSON.stringify(tasks)); },
  saveSales()               { localStorage.setItem(STORE.K.sales,               JSON.stringify(salesData)); },
  saveDailyReports()        { localStorage.setItem(STORE.K.dailyReports,        JSON.stringify(dailyReports)); },
  saveMonthlyGoals()        { localStorage.setItem(STORE.K.monthlyGoals,        JSON.stringify(monthlyGoals)); },
  saveMonthlySalesTargets() { localStorage.setItem(STORE.K.monthlySalesTargets, JSON.stringify(monthlySalesTargets)); },
  saveShortcuts()           { localStorage.setItem(STORE.K.shortcuts,           JSON.stringify(sk)); },
  saveDocs()                { localStorage.setItem(STORE.K.docs,                JSON.stringify(docsData)); },
  saveCmd()                 { localStorage.setItem(STORE.K.cmdMode, CMD.mode); localStorage.setItem(STORE.K.cmdWhite, JSON.stringify([...CMD.white])); localStorage.setItem(STORE.K.cmdBlack, JSON.stringify([...CMD.black])); },
  getMyRank()               { return localStorage.getItem(STORE.K.profileRank) || 'director'; },
  getMyRate()               { return RANK_RATES[STORE.getMyRank()] || 0.15; },
};

const COMMANDS = [
  {id:'node.add',        label:'新增聯繫人'},
  {id:'note.add',        label:'新增便條'},
  {id:'event.open',      label:'開啟/新增活動'},
  {id:'event.save',      label:'儲存活動'},
  {id:'event.delete',    label:'刪除活動'},
  {id:'doc.open',        label:'開啟/新增文件'},
  {id:'doc.save',        label:'儲存文件'},
  {id:'doc.delete',      label:'刪除文件'},
  {id:'sales.open',      label:'開啟/新增成交'},
  {id:'sales.save',      label:'儲存成交'},
  {id:'sales.delete',    label:'刪除成交'},
  {id:'backup.export',   label:'匯出備份'},
  {id:'backup.import',   label:'匯入備份'},
  {id:'data.clear',      label:'清除所有資料'},
];
const CMD = {
  mode: localStorage.getItem(STORE.K.cmdMode)||'blacklist',
  white: new Set(JSON.parse(localStorage.getItem(STORE.K.cmdWhite)||'[]')),
  black: new Set(JSON.parse(localStorage.getItem(STORE.K.cmdBlack)||'[]')),
  allowed(id){
    if(this.black.has(id)) return false;
    if(this.mode==='whitelist'){
      if(this.white.size===0) return false;
      return this.white.has(id);
    }
    return true;
  },
  setMode(m){ this.mode=(m==='whitelist')?'whitelist':'blacklist'; STORE.saveCmd(); },
  toggle(id){
    if(this.mode==='whitelist'){
      if(this.white.has(id)) this.white.delete(id); else this.white.add(id);
    } else {
      if(this.black.has(id)) this.black.delete(id); else this.black.add(id);
    }
    STORE.saveCmd();
  },
  reset(){ this.mode='blacklist'; this.white=new Set(); this.black=new Set(); STORE.saveCmd(); }
};
function setCmdMode(m){ CMD.setMode(m); renderSettingsPage(); toast('指令模式已更新'); }
function toggleCmd(id){ CMD.toggle(id); renderSettingsPage(); }
function resetCmdPolicy(){ CMD.reset(); renderSettingsPage(); toast('已恢復預設指令策略'); }

const DRAFT={
  K:'crm-drafts',
  data:{},
  load(){try{this.data=JSON.parse(localStorage.getItem(this.K)||'{}')}catch(e){this.data={}}},
  save(){localStorage.setItem(this.K,JSON.stringify(this.data))},
  set(id,val){this.data[id]=val;this.save()},
  get(id){return this.data[id]},
  clear(){this.data={};this.save()}
};
function initDrafts(){
  DRAFT.load();
  const isSensitive=(el)=>el.type==='password'||el.dataset.nodraft==='true';
  const restore=(root)=>{
    const els=root.querySelectorAll?.('input[id], textarea[id]')||[];
    els.forEach(el=>{
      if(isSensitive(el))return;
      const id=el.id;if(!id)return;
      const v=DRAFT.get(id);
      if(v!==undefined && (el.value===''||el.dataset.restore==='force')){el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}))}
    });
  };
  restore(document);
  const onInput=(e)=>{
    const t=e.target;
    if(!(t instanceof HTMLInputElement||t instanceof HTMLTextAreaElement))return;
    if(!t.id||isSensitive(t))return;
    DRAFT.set(t.id,t.value);
  };
  document.addEventListener('input',onInput,true);
  document.addEventListener('change',onInput,true);
  // Only watch for added nodes at top level to reduce overhead
  const mo=new MutationObserver(muts=>{
    muts.forEach(m=>{m.addedNodes.forEach(n=>{if(n.nodeType===1)restore(n);})});
  });
  mo.observe(document.body,{subtree:false,childList:true});
  window.addEventListener('beforeunload',()=>DRAFT.save());
}

/* ═══════════════════════════════════════
   DEMO DATA
═══════════════════════════════════════ */
function buildDemoData(){
  const mkInfo=(o)=>Object.assign(newNode().info,o);
  const root={id:'root',parentId:null,x:0,y:0,name:'我的人脈',status:null,collapsed:false,info:mkInfo({notes:'根節點'})};
  const zhang={id:'n1',parentId:'root',x:0,y:0,name:'張偉明',status:'green',collapsed:false,info:mkInfo({company:'ABC科技',age:'38',currentJob:'業務總監',income:'月收12萬',hasProperty:'名下一間自住',tags:['客戶','VIP'],lastContact:'2026-03-15',eventDate:'2026-03-25',eventName:'台中聯合分享會',referrer:'自己',needs:['買房','學習']})};
  const li={id:'n2',parentId:'n1',x:0,y:0,name:'李曉華',status:'yellow',collapsed:false,info:mkInfo({company:'ABC科技',currentJob:'行政助理',tags:['介紹人'],lastContact:'2026-02-20'})};
  const wang={id:'n3',parentId:'root',x:0,y:0,name:'王淑芬',status:'yellow',collapsed:false,info:mkInfo({company:'DEF顧問',tags:['潛在客戶'],lastContact:'2026-03-01'})};
  const chen={id:'n4',parentId:'root',x:0,y:0,name:'陳建國',status:'red',collapsed:false,info:mkInfo({company:'GHI集團',tags:['前客戶'],lastContact:'2025-12-01'})};
  const lin={id:'n5',parentId:'n4',x:0,y:0,name:'林志偉',status:'gray',collapsed:false,info:mkInfo({tags:['無效'],lastContact:'2025-10-15'})};
  return[root,zhang,li,wang,chen,lin];
}

/* ═══════════════════════════════════════
   LAYOUT
═══════════════════════════════════════ */
const NODE_W=160,NODE_H_EST=120,GAP_H=40,GAP_V=80;

function subtreeW(id){
  const n=findNode(id);if(!n)return NODE_W+GAP_H;
  const kids=getChildren(id).filter(c=>!n.collapsed);
  if(!kids.length)return NODE_W+GAP_H;
  return kids.reduce((s,c)=>s+subtreeW(c.id),0);
}

function layoutFrom(id,cx,y){
  const n=findNode(id);if(!n)return;
  if(n.x===undefined||n.x===null||n.x===0&&n.y===0&&id!=='root'){
    n.x=cx-NODE_W/2;n.y=y;
  } else if(id==='root'&&n.x===0&&n.y===0){
    n.x=cx-NODE_W/2;n.y=y;
  }
  const kids=getChildren(id);
  if(!kids.length)return;
  const totalW=kids.reduce((s,c)=>s+subtreeW(c.id),0);
  let lx=cx-totalW/2;
  kids.forEach(c=>{
    const cw=subtreeW(c.id);
    layoutFrom(c.id,lx+cw/2,y+NODE_H_EST+GAP_V);
    lx+=cw;
  });
}

function autoLayout(){
  const roots=getRoots();
  const totalW=roots.reduce((s,r)=>s+subtreeW(r.id),0);
  let lx=-(totalW/2);
  roots.forEach(r=>{
    const rw=subtreeW(r.id);
    layoutFrom(r.id,lx+rw/2,0);
    lx+=rw;
  });
}

// Force re-layout: ignore current positions
function forceLayout(){
  function forceFrom(id,cx,y){
    const n=findNode(id);if(!n)return;
    n.x=cx-NODE_W/2; n.y=y;
    const kids=getChildren(id).filter(c=>!n.collapsed);
    if(!kids.length)return;
    const totalW=kids.reduce((s,c)=>s+subtreeW(c.id),0);
    let lx=cx-totalW/2;
    kids.forEach(c=>{
      const cw=subtreeW(c.id);
      forceFrom(c.id,lx+cw/2,y+NODE_H_EST+GAP_V);
      lx+=cw;
    });
  }
  const roots=getRoots();
  const totalW=roots.reduce((s,r)=>s+subtreeW(r.id),0);
  let lx=-(totalW/2);
  roots.forEach(r=>{
    const rw=subtreeW(r.id);
    forceFrom(r.id,lx+rw/2,0);
    lx+=rw;
  });
  saveData(); renderNodes(); fitView();
  toast('排列已整理');
}

/* ═══════════════════════════════════════
   CANVAS STATE
═══════════════════════════════════════ */
let panX=0,panY=0,zoom=1;
let isPanning=false,isDragging=false;
let dragId=null;
let dragStartMX,dragStartMY;
let dragStartPositions=new Map();
let panStartMX,panStartMY,panStartPX,panStartPY;
let didMove=false;
const DRAG_THRESHOLD=4;
let snapTargetId=null;          // id of node currently highlighted as drop target
const SNAP_RADIUS=120;          // screen-pixels snap threshold
let isResizingPanel=false,resizeStartX=0,resizeStartW=380;
let _suppressNextCanvasClick=false;
let _nodeWasMousedDown=false; // true when mousedown landed on a node wrap
let selId=null;
let currentPage='crm';
let clipboard=null;
// n8n-style connect state
let isConnecting=false,connectFromId=null,connectTargetId=null,connectPreviewPath=null;

const container=()=>document.getElementById('canvas-container');

function applyTransform(){
  document.getElementById('canvas').style.transform=`translate(${panX}px,${panY}px) scale(${zoom})`;
}

function updateZoomLabel(){
  const el=document.getElementById('zoom-label');
  if(el)el.textContent=Math.round(zoom*100)+'%';
}

function zoomBy(f){
  const c=container();
  const cx=c.offsetWidth/2,cy=c.offsetHeight/2;
  const nz=Math.max(0.15,Math.min(4,zoom*f));
  panX=cx-(cx-panX)*(nz/zoom);
  panY=cy-(cy-panY)*(nz/zoom);
  zoom=nz;
  applyTransform();updateZoomLabel();
}

function fitView(){
  const vis=nodes.filter(n=>!isHidden(n.id));
  if(!vis.length)return;
  const padding=80;
  const minX=Math.min(...vis.map(n=>n.x));
  const maxX=Math.max(...vis.map(n=>n.x+NODE_W));
  const minY=Math.min(...vis.map(n=>n.y));
  const maxY=Math.max(...vis.map(n=>n.y+NODE_H_EST));
  const c=container();
  const cw=c.offsetWidth,ch=c.offsetHeight;
  const nz=Math.min(1.2,Math.min((cw-padding*2)/(maxX-minX||1),(ch-padding*2)/(maxY-minY||1)));
  zoom=Math.max(0.15,nz);
  panX=(cw-(maxX-minX)*zoom)/2-minX*zoom;
  panY=(ch-(maxY-minY)*zoom)/2-minY*zoom;
  applyTransform();updateZoomLabel();
}

/* ═══════════════════════════════════════
   RENDER NODES
═══════════════════════════════════════ */
// 共用：為節點 wrap 附加拖曳 + click 事件
function _attachNodeDrag(wrap, n){
  // Use Pointer Events so drag works on both mouse and touch/stylus
  wrap.addEventListener('pointerdown',e=>{
    if(e.pointerType==='mouse'&&e.button!==0)return;
    if(e.target.classList.contains('note-content'))return;
    e.stopPropagation();
    wrap.setPointerCapture(e.pointerId); // keeps events on this element during drag
    _nodeWasMousedDown=true;
    selectNode(n.id);
    dragId=n.id;
    dragStartMX=e.clientX;
    dragStartMY=e.clientY;
    dragStartPositions=new Map();
    const subtree=gatherSubtree(n.id);
    subtree.forEach(sid=>{
      const sn=findNode(sid);
      if(sn)dragStartPositions.set(sid,{x:sn.x,y:sn.y});
    });
    isDragging=false;
    didMove=false;
  });
  wrap.addEventListener('click',e=>{
    e.stopPropagation();
    if(isDragging)return;
    // setPointerCapture redirects e.target to wrap; use composedPath to find actual clicked element
    const a=(e.composedPath&&e.composedPath().find(el=>el instanceof Element&&el.dataset&&el.dataset.a))||e.target.closest('[data-a]');
    if(!a)return;
    const act=a.dataset.a,id=a.dataset.id;
    if(act==='open'){openPanel(id);}
    else if(act==='status'){cycleStatus(id);}
    else if(act==='add'){addChild(id);}
    else if(act==='del'){promptDel(id);}
    else if(act==='collapse'){toggleCollapse(id);}
  });
  wrap.addEventListener('dblclick',e=>{
    e.stopPropagation();
    if(n.nodeType==='note')return; // note: click on contenteditable directly
    openPanel(n.id);
  });
}

function renderNodes(){
  const layer=document.getElementById('nodes-layer');
  layer.innerHTML='';
  nodes.forEach(n=>{
    if(isHidden(n.id))return;
    const isRoot=!n.parentId&&n.status===null;
    const kids=getChildren(n.id);
    const hasKids=kids.length>0;

    const wrap=document.createElement('div');
    wrap.dataset.id=n.id;
    wrap.style.cssText=`left:${n.x}px;top:${n.y}px`;

    let collapseHtml='';
    if(hasKids){
      collapseHtml=`<button class="collapse-btn" data-a="collapse" data-id="${n.id}">${n.collapsed?'▼ 展開('+kids.length+')':'▲ 收合'}</button>`;
    }

    // ── 純文字便條 ──────────────────────────
    if(n.nodeType==='note'){
      wrap.className='node-wrap note-node'+(selId===n.id?' selected':'');
      wrap.innerHTML=`
        <div class="node-card note-card">
          <div class="node-drag-handle" title="拖曳移動">⠿</div>
          <div class="note-content"
               contenteditable="true"
               data-id="${n.id}"
               onblur="saveNoteContent(this)"
               onkeydown="if(event.key==='Escape')this.blur()"
               spellcheck="false">${escHtml(n.content||'').replace(/\n/g,'<br>')}</div>
          <div class="node-footer">
            <div class="node-meta" style="color:var(--text-muted);font-size:10px">📝 便條</div>
            <div class="node-actions">
              <button class="act-btn" data-a="add" data-id="${n.id}" title="新增子節點">+</button>
              <button class="act-btn del" data-a="del" data-id="${n.id}" title="刪除">🗑</button>
            </div>
          </div>
          ${collapseHtml}
        </div>`;
      layer.appendChild(wrap);
      // drag events added below
      _attachNodeDrag(wrap, n);
      return; // skip normal card
    }

    // ── 一般聯繫人節點 ───────────────────────
    const meta=n.info.company||(n.info.tags&&n.info.tags[0])||'';
    const ROLE_MAP={潛在客戶:'role-prospect',轉介紹中心:'role-referral',學員:'role-student',從業人員:'role-agent'};
    const roleHtml=n.info.role?`<div class="node-role-pill ${ROLE_MAP[n.info.role]||''}">${n.info.role}</div>`:'';
    const regionsHtml=(n.info.regions&&n.info.regions.length)?`<div class="node-region-tags">${n.info.regions.map(r=>`<span class="node-region-tag">${r}</span>`).join('')}</div>`:'';

    wrap.className='node-wrap'+(n.status&&!isRoot?' status-'+n.status:'')+(selId===n.id?' selected':'');

    let statusHtml='';
    if(isRoot){
      statusHtml=`<div class="node-root-pill">根節點</div>`;
    } else {
      statusHtml=`<div class="status-pill" data-a="status" data-id="${n.id}"><span class="status-dot"></span>${STATUS_LABELS[n.status]||''}</div>`;
    }

    wrap.innerHTML=`
      <div class="node-card">
        <div class="node-drag-handle" title="拖曳移動">⠿</div>
        <div class="node-header">
          <div class="node-avatar">${(n.name||'?')[0]}</div>
          <div class="node-name" data-a="open" data-id="${n.id}" title="${n.name}">${n.name}</div>
        </div>
        ${statusHtml}
        ${roleHtml}
        ${regionsHtml}
        <div class="node-footer">
          <div class="node-meta">${meta}</div>
          <div class="node-actions">
            <button class="act-btn" data-a="add" data-id="${n.id}" title="新增子節點">+</button>
            <button class="act-btn del" data-a="del" data-id="${n.id}" title="刪除">🗑</button>
          </div>
        </div>
        ${collapseHtml}
        <button class="node-port-add" title="拖線建立關係" data-id="${n.id}" onclick="event.stopPropagation()" onpointerdown="startConnect(event,'${n.id}')">+</button>
      </div>`;

    _attachNodeDrag(wrap, n);
    layer.appendChild(wrap);
  });

  setTimeout(drawEdges,0);
  updateStats();
}

/* ═══════════════════════════════════════
   EDGE DRAWING
═══════════════════════════════════════ */
function drawEdges(){
  const svg=document.getElementById('edges-svg');
  svg.innerHTML='';

  // Normal edges
  nodes.forEach(n=>{
    if(!n.parentId)return;
    if(isHidden(n.id))return;
    if(isDragging&&n.id===dragId)return; // skip current drag node's old edge
    const parent=findNode(n.parentId);
    if(!parent||isHidden(parent.id))return;
    if(parent.collapsed)return;
    const pEl=document.querySelector(`.node-wrap[data-id="${parent.id}"]`);
    const nEl=document.querySelector(`.node-wrap[data-id="${n.id}"]`);
    if(!pEl||!nEl)return;
    const px=parent.x+NODE_W/2;
    const py=parent.y+pEl.offsetHeight;
    const cx=n.x+NODE_W/2;
    const cy=n.y;
    const my=(py+cy)/2;
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M ${px} ${py} C ${px} ${my}, ${cx} ${my}, ${cx} ${cy}`);
    path.setAttribute('stroke','#30363d');
    path.setAttribute('stroke-width','1.5');
    path.setAttribute('fill','none');
    svg.appendChild(path);
  });

  // Snap preview edge (dashed, animated)
  if(isDragging&&dragId&&snapTargetId){
    const dn=findNode(dragId);
    const sn=findNode(snapTargetId);
    const snEl=document.querySelector(`.node-wrap[data-id="${snapTargetId}"]`);
    if(dn&&sn&&snEl){
      const px=sn.x+NODE_W/2;
      const py=sn.y+snEl.offsetHeight;
      const cx=dn.x+NODE_W/2;
      const cy=dn.y;
      const my=(py+cy)/2;
      const preview=document.createElementNS('http://www.w3.org/2000/svg','path');
      preview.setAttribute('d',`M ${px} ${py} C ${px} ${my}, ${cx} ${my}, ${cx} ${cy}`);
      preview.setAttribute('stroke','#388bfd');
      preview.setAttribute('stroke-width','2.5');
      preview.setAttribute('stroke-dasharray','8 4');
      preview.setAttribute('fill','none');
      preview.setAttribute('opacity','0.85');
      preview.classList.add('snap-preview-edge');
      svg.appendChild(preview);
    }
  }
}

/* n8n-like connect interactions */
function toCanvasXY(cx,cy){const r=document.getElementById('canvas-container').getBoundingClientRect();return{x:(cx-r.left-panX)/zoom,y:(cy-r.top-panY)/zoom};}
function clearConnectHighlight(){document.querySelectorAll('.node-wrap.connect-target').forEach(el=>el.classList.remove('connect-target'));}
function startConnect(ev,fromId){ev.preventDefault();ev.stopPropagation();if(isDragging)return;isConnecting=true;connectFromId=fromId;connectTargetId=null;const svg=document.getElementById('edges-svg');connectPreviewPath=document.createElementNS('http://www.w3.org/2000/svg','path');connectPreviewPath.setAttribute('stroke','#388bfd');connectPreviewPath.setAttribute('stroke-width','2');connectPreviewPath.setAttribute('fill','none');svg.appendChild(connectPreviewPath);ev.currentTarget.setPointerCapture&&ev.currentTarget.setPointerCapture(ev.pointerId);document.addEventListener('pointermove',onConnectMove);document.addEventListener('pointerup',onConnectEnd);onConnectMove(ev);}
function onConnectMove(ev){if(!isConnecting||!connectFromId||!connectPreviewPath)return;const from=findNode(connectFromId);const fromEl=document.querySelector(`.node-wrap[data-id="${connectFromId}"]`);if(!from||!fromEl)return;const p1x=from.x+NODE_W;const p1y=from.y+fromEl.offsetHeight/2;const c=toCanvasXY(ev.clientX,ev.clientY);const my=(p1y+c.y)/2;connectPreviewPath.setAttribute('d',`M ${p1x} ${p1y} C ${p1x} ${my}, ${c.x} ${my}, ${c.x} ${c.y}`);clearConnectHighlight();connectTargetId=null;const hit=(ev.target.closest&&ev.target.closest('.node-wrap'))||(document.elementFromPoint(ev.clientX,ev.clientY)?.closest?.('.node-wrap'));if(hit){const tid=hit.dataset.id;if(tid&&tid!==connectFromId){const sub=new Set(gatherSubtree(connectFromId));const tn=findNode(tid);if(!sub.has(tid)&&tn&&tn.nodeType!=='note'){connectTargetId=tid;hit.classList.add('connect-target');}}}}
function onConnectEnd(ev){if(!isConnecting)return;document.removeEventListener('pointermove',onConnectMove);document.removeEventListener('pointerup',onConnectEnd);if(connectPreviewPath&&connectPreviewPath.parentNode)connectPreviewPath.remove();clearConnectHighlight();const fromId=connectFromId,toId=connectTargetId;isConnecting=false;connectFromId=null;connectTargetId=null;connectPreviewPath=null;if(fromId&&toId){const sub=new Set(gatherSubtree(fromId));if(sub.has(toId)||fromId===toId){toast('不可形成環');return;}const to=findNode(toId);if(!to)return;to.parentId=fromId;saveData();renderNodes();selectNode(toId);toast('已建立上下階關係');return;}const c=toCanvasXY(ev.clientX,ev.clientY);const n=newNode();n.parentId=fromId;n.x=c.x-NODE_W/2;n.y=c.y-30;nodes.push(n);saveData();renderNodes();openPanel(n.id);toast('已新增子節點');}

/* ═══════════════════════════════════════
   SELECTION
═══════════════════════════════════════ */
function selectNode(id){
  if(selId===id)return;
  selId=id;
  document.querySelectorAll('.node-wrap').forEach(el=>{
    el.classList.toggle('selected',el.dataset.id===id);
  });
}

function deselect(){
  selId=null;
  document.querySelectorAll('.node-wrap.selected').forEach(el=>el.classList.remove('selected'));
}

/* ═══════════════════════════════════════
   NODE OPERATIONS
═══════════════════════════════════════ */
function createNodeAt(cx,cy){
  const n=newNode();
  n.parentId=null;
  n.x=cx-NODE_W/2;
  n.y=cy-30;
  nodes.push(n);
  saveData();
  renderNodes();
  selectNode(n.id);
  openPanel(n.id);
  toast('已新增節點 — 點擊姓名編輯');
}

function createNoteNodeAt(cx,cy){
  const n={
    id:uid(),parentId:null,x:cx-NODE_W/2,y:cy-30,
    nodeType:'note',name:'便條',status:null,collapsed:false,
    content:'',info:{}
  };
  nodes.push(n);
  saveData();
  renderNodes();
  selectNode(n.id);
  // Focus the note content for immediate editing
  setTimeout(()=>{
    const el=document.querySelector(`.node-wrap[data-id="${n.id}"] .note-content`);
    if(el){el.focus();const r=document.createRange();r.selectNodeContents(el);r.collapse(false);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(r);}
  },50);
  toast('已新增文字便條');
}

function headerAddNote(){
  if(!CMD.allowed('note.add')){ toast('此指令已被停用'); return; }
  const c=container();
  const cx=(c.offsetWidth/2-panX)/zoom;
  const cy=(c.offsetHeight/2-panY)/zoom;
  createNoteNodeAt(cx,cy);
}

function saveNoteContent(el){
  const id=el.dataset.id;
  const n=findNode(id);
  if(!n)return;
  n.content=el.innerText.trim();
  saveData();
}

function addChild(parentId){
  const parent=findNode(parentId);
  if(!parent)return;
  const siblings=getChildren(parentId);
  const n=newNode();
  n.parentId=parentId;
  n.x=parent.x+siblings.length*(NODE_W+GAP_H);
  n.y=parent.y+NODE_H_EST+GAP_V;
  parent.collapsed=false;
  nodes.push(n);
  saveData();
  renderNodes();
  selectNode(n.id);
  openPanel(n.id);
}

function headerAddNode(){
  if(!CMD.allowed('node.add')){ toast('此指令已被停用'); return; }
  if(selId){
    addChild(selId);
  } else {
    const c=container();
    const cx=(c.offsetWidth/2-panX)/zoom;
    const cy=(c.offsetHeight/2-panY)/zoom;
    createNodeAt(cx,cy);
  }
}

function cycleStatus(id){
  const n=findNode(id);if(!n)return;
  if(n.status===null)return; // root
  const idx=STATUS_ORDER.indexOf(n.status);
  n.status=STATUS_ORDER[(idx+1)%STATUS_ORDER.length];
  saveData();
  renderNodes();
  updateStats();
  // Keep panel open if it was showing this node
  if(panelNodeId===id) selectNode(id);
}

function toggleCollapse(id){
  const n=findNode(id);if(!n)return;
  n.collapsed=!n.collapsed;
  saveData();
  renderNodes();
}

function promptDel(id){
  const n=findNode(id);if(!n)return;
  const kids=gatherSubtree(id);
  const msg=kids.length>1?`確定刪除「${n.name}」及其 ${kids.length-1} 個子節點？`:`確定刪除「${n.name}」？`;
  if(confirm(msg)){
    kids.forEach(kid=>{nodes=nodes.filter(x=>x.id!==kid);});
    if(selId===id||kids.includes(selId)){selId=null;}
    if(panelNodeId===id){closePanel();}
    saveData();
    renderNodes();
    toast('已刪除');
  }
}

/* ═══════════════════════════════════════
   CLIPBOARD
═══════════════════════════════════════ */
function copySelected(){
  if(!selId)return;
  const n=findNode(selId);if(!n)return;
  clipboard=JSON.parse(JSON.stringify(n));
  toast('已複製：'+n.name);
}
function cutSelected(){
  if(!selId)return;
  copySelected();
  promptDel(selId);
}
function pasteClipboard(){
  if(!clipboard)return;
  const n=JSON.parse(JSON.stringify(clipboard));
  n.id=uid();
  n.parentId=selId||null;
  n.x+=30;n.y+=30;
  nodes.push(n);
  saveData();renderNodes();
  selId=n.id;
  toast('已貼上：'+n.name);
}

/* ═══════════════════════════════════════
   CANVAS INTERACTIONS
═══════════════════════════════════════ */
function initCanvas(){
  const cont=container();

  // Zoom
  cont.addEventListener('wheel',e=>{
    e.preventDefault();
    const rect=cont.getBoundingClientRect();
    const mx=e.clientX-rect.left;
    const my=e.clientY-rect.top;
    const f=e.deltaY<0?1.12:0.9;
    const nz=Math.max(0.15,Math.min(4,zoom*f));
    panX=mx-(mx-panX)*(nz/zoom);
    panY=my-(my-panY)*(nz/zoom);
    zoom=nz;
    applyTransform();updateZoomLabel();
  },{passive:false});

  // Canvas background click/pan detection
  // Use separate flags so pan-drag doesn't block future clicks
  let canvasPanMoved=false;
  cont.addEventListener('pointerdown',e=>{
    if(e.pointerType==='mouse'&&e.button!==0)return;
    // Only start pan when clicking the background (node wraps stopPropagation)
    isPanning=true;
    canvasPanMoved=false;
    panStartMX=e.clientX;panStartMY=e.clientY;
    panStartPX=panX;panStartPY=panY;
    cont.style.cursor='grabbing';
  });
  // Canvas click = deselect only
  cont.addEventListener('click',e=>{
    if(_suppressNextCanvasClick){_suppressNextCanvasClick=false;return;}
    if(canvasPanMoved)return;
    deselect();
    closePanel();
  });

  // Global pointermove (covers mouse + touch + stylus)
  document.addEventListener('pointermove',e=>{
    if(dragId!==null){
      const dx=e.clientX-dragStartMX;
      const dy=e.clientY-dragStartMY;
      if(!isDragging&&Math.hypot(dx,dy)>DRAG_THRESHOLD){
        isDragging=true;didMove=true;
        // Apply floating class to the dragged wrap
        document.querySelector(`.node-wrap[data-id="${dragId}"]`)?.classList.add('dragging');
      }
      if(isDragging){
        dragStartPositions.forEach((pos,id)=>{
          const dn=findNode(id);
          if(dn){
            dn.x=pos.x+dx/zoom;
            dn.y=pos.y+dy/zoom;
            const el=document.querySelector(`.node-wrap[data-id="${id}"]`);
            if(el){el.style.left=dn.x+'px';el.style.top=dn.y+'px';}
          }
        });

        // ── Snap-target detection ──────────────────
        const dn=findNode(dragId);
        if(dn){
          const subtree=gatherSubtree(dragId);
          const snapR=SNAP_RADIUS/zoom; // threshold in canvas units
          const dragCX=dn.x+NODE_W/2;
          const dragCY=dn.y+60;
          let bestId=null,bestDist=snapR;
          nodes.forEach(cand=>{
            if(subtree.includes(cand.id))return;
            const candCX=cand.x+NODE_W/2;
            const candCY=cand.y+60;
            const dist=Math.hypot(dragCX-candCX,dragCY-candCY);
            if(dist<bestDist){bestDist=dist;bestId=cand.id;}
          });
          if(snapTargetId!==bestId){
            if(snapTargetId)document.querySelector(`.node-wrap[data-id="${snapTargetId}"]`)?.classList.remove('snap-target');
            snapTargetId=bestId;
            if(snapTargetId)document.querySelector(`.node-wrap[data-id="${snapTargetId}"]`)?.classList.add('snap-target');
          }
        }

        drawEdges();
      }
      return;
    }
    if(isPanning){
      const dx=e.clientX-panStartMX;
      const dy=e.clientY-panStartMY;
      if(Math.hypot(dx,dy)>DRAG_THRESHOLD)canvasPanMoved=true;
      panX=panStartPX+dx;panY=panStartPY+dy;
      applyTransform();
    }
  });

  // Global pointerup (covers mouse + touch + stylus)
  document.addEventListener('pointerup',e=>{
    if(isResizingPanel){
      isResizingPanel=false;
      document.body.style.cursor='';
      document.getElementById('panel-resize').classList.remove('active');
      return;
    }
    if(dragId!==null){
      const wasDragging=isDragging;
      // Remove visual drag state
      document.querySelector(`.node-wrap[data-id="${dragId}"]`)?.classList.remove('dragging');
      if(isDragging){
        if(snapTargetId){
          // ── Reparent to snap target ──────────────
          const dn=findNode(dragId);
          if(dn){dn.parentId=snapTargetId;}
          document.querySelector(`.node-wrap[data-id="${snapTargetId}"]`)?.classList.remove('snap-target');
          snapTargetId=null;
          saveData();
          renderNodes();
          toast('節點已連接');
        } else {
          // Clear any leftover snap highlight
          if(snapTargetId){document.querySelector(`.node-wrap[data-id="${snapTargetId}"]`)?.classList.remove('snap-target');snapTargetId=null;}
          saveData();
        }
      }
      dragId=null;isDragging=false;
      if(wasDragging) _suppressNextCanvasClick=true;
      return;
    }
    if(isPanning){
      isPanning=false;
      cont.style.cursor='default';
      // canvasPanMoved stays set until next mousedown — checked in click handler
    }
  });

  /* ── Pinch-to-zoom (trackpad / touch) ── */
  let lastPinchDist=null;
  cont.addEventListener('touchstart',e=>{
    if(e.touches.length===2){
      lastPinchDist=Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY);
    }
  },{passive:true});
  cont.addEventListener('touchmove',e=>{
    if(e.touches.length===2&&lastPinchDist){
      e.preventDefault();
      const dist=Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY);
      const f=dist/lastPinchDist;
      const midX=(e.touches[0].clientX+e.touches[1].clientX)/2;
      const midY=(e.touches[0].clientY+e.touches[1].clientY)/2;
      const rect=cont.getBoundingClientRect();
      const mx=midX-rect.left, my=midY-rect.top;
      const nz=Math.max(0.15,Math.min(4,zoom*f));
      panX=mx-(mx-panX)*(nz/zoom);
      panY=my-(my-panY)*(nz/zoom);
      zoom=nz; lastPinchDist=dist;
      applyTransform(); updateZoomLabel();
    }
  },{passive:false});
  cont.addEventListener('touchend',e=>{ if(e.touches.length<2) lastPinchDist=null; },{passive:true});

  /* ── Panel resize handle ── */
  const resizeHandle=document.getElementById('panel-resize');
  resizeHandle.addEventListener('mousedown',e=>{
    isResizingPanel=true;
    resizeStartX=e.clientX;
    resizeStartW=document.getElementById('side-panel').offsetWidth;
    document.body.style.cursor='col-resize';
    resizeHandle.classList.add('active');
    e.preventDefault();
  });
  document.addEventListener('mousemove',e=>{
    if(isResizingPanel){
      const dx=resizeStartX-e.clientX;
      const w=Math.max(280,Math.min(680,resizeStartW+dx));
      document.getElementById('side-panel').style.width=w+'px';
    }
  });
}

/* ═══════════════════════════════════════
   SHORTCUTS SYSTEM
═══════════════════════════════════════ */
const DEFAULT_SHORTCUTS = {
  addSibling:  { key:'Enter',   ctrl:false, label:'新增同層節點 (Enter)',  desc:'平行新增' },
  addChild:    { key:'Tab',     ctrl:false, label:'新增子節點 (Tab)',      desc:'向下新增' },
  delete:      { key:'Delete',  ctrl:false, label:'刪除節點 (Del)',        desc:'刪除' },
  fitView:     { key:'f',       ctrl:false, label:'全覽 (F)',              desc:'全覽' },
  copy:        { key:'c',       ctrl:true,  label:'複製 (⌘C)',            desc:'複製' },
  paste:       { key:'v',       ctrl:true,  label:'貼上 (⌘V)',            desc:'貼上' },
  cut:         { key:'x',       ctrl:true,  label:'剪下 (⌘X)',            desc:'剪下' },
  zoomIn:      { key:'=',       ctrl:true,  label:'放大 (⌘=)',            desc:'放大' },
  zoomOut:     { key:'-',       ctrl:true,  label:'縮小 (⌘-)',            desc:'縮小' },
  escape:      { key:'Escape',  ctrl:false, label:'取消選取 (Esc)',        desc:'Esc' },
};
let sk = JSON.parse(localStorage.getItem(STORE.K.shortcuts)||'null') || JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
function saveShortcuts(){ STORE.saveShortcuts(); }
function resetShortcuts(){ sk=JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS)); saveShortcuts(); renderSkModal(); renderShortcutsHint(); toast('已恢復預設快捷鍵'); }

function matchShortcut(action, e){
  const s=sk[action]; if(!s) return false;
  const ctrl=e.ctrlKey||e.metaKey;
  return e.key.toLowerCase()===s.key.toLowerCase() && ctrl===s.ctrl;
}

function renderShortcutsHint(){
  const el=document.getElementById('shortcuts-hint'); if(!el) return;
  const pairs=[
    ['addSibling'], ['addChild'], ['copy'], ['paste'], ['cut'], ['delete'], ['fitView'], ['escape']
  ];
  el.innerHTML = pairs.map(([a])=>{
    const s=sk[a]; if(!s) return '';
    const k=(s.ctrl?'⌘+':'')+s.key.replace('Delete','Del').replace('Escape','Esc').replace('ArrowUp','↑').replace('ArrowDown','↓');
    return `<span><kbd>${k}</kbd> ${s.desc}</span>`;
  }).join('');
}

/* Shortcuts modal */
let listeningAction=null;
function openSkModal(){
  document.getElementById('sk-modal').classList.add('open');
  renderSkModal();
}
function closeSkModal(){ document.getElementById('sk-modal').classList.remove('open'); listeningAction=null; }
function renderSkModal(){
  const body=document.getElementById('sk-body'); if(!body) return;
  const curTheme=document.documentElement.getAttribute('data-theme')||'dark';
  body.innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-size:11px;font-weight:500;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">背景主題</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
        ${THEMES.map(t=>`
          <div onclick="applyTheme('${t.id}');renderSkModal()" style="padding:10px 6px;border-radius:8px;border:2px solid ${curTheme===t.id?'var(--accent)':'var(--border)'};cursor:pointer;text-align:center;background:var(--surface2);transition:all .15s">
            <div style="font-size:20px;margin-bottom:4px">${t.icon}</div>
            <div style="font-size:11px;color:var(--text-muted)">${t.label}</div>
          </div>`).join('')}
      </div>
    </div>
    <div style="font-size:11px;font-weight:500;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">快捷鍵</div>
    ${Object.entries(sk).map(([action,s])=>`
    <div class="sk-row">
      <div class="sk-action">${s.label}</div>
      <div class="sk-capture${listeningAction===action?' listening':''}" data-action="${action}" onclick="startListening('${action}')">
        ${listeningAction===action ? '按下新按鍵…' : (s.ctrl?'⌘+':'')+s.key.replace('Escape','Esc').replace('Delete','Del')}
      </div>
    </div>`).join('')}`;
}
function startListening(action){
  listeningAction=action;
  renderSkModal();
}
document.addEventListener('keydown',e=>{
  if(listeningAction){
    e.preventDefault(); e.stopPropagation();
    const ctrl=e.ctrlKey||e.metaKey;
    if(e.key==='Escape'&&!ctrl){ listeningAction=null; renderSkModal(); return; }
    sk[listeningAction]={...sk[listeningAction], key:e.key, ctrl};
    saveShortcuts(); renderShortcutsHint();
    listeningAction=null; renderSkModal();
    if(currentPage==='settings') renderSettingsPage();
    return;
  }
  // Normal shortcuts
  const tag=e.target.tagName;
  const inInput=tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT';
  const inContentEditable=e.target.isContentEditable;
  // Cmd+Z — undo (skip if in contenteditable so text-undo still works)
  const ctrl=e.ctrlKey||e.metaKey;
  if(ctrl&&e.key==='z'&&!inContentEditable&&!inInput){
    e.preventDefault();undoLast();return;
  }
  if(inInput)return;
  if(currentPage!=='crm')return;
  if(matchShortcut('copy',e)){e.preventDefault();copySelected();}
  else if(matchShortcut('cut',e)){e.preventDefault();cutSelected();}
  else if(matchShortcut('paste',e)){e.preventDefault();pasteClipboard();}
  else if(matchShortcut('zoomIn',e)){e.preventDefault();zoomBy(1.15);}
  else if(matchShortcut('zoomOut',e)){e.preventDefault();zoomBy(0.87);}
  else if(ctrl&&e.key==='0'){e.preventDefault();fitView();}
  else if(matchShortcut('delete',e)&&selId){e.preventDefault();promptDel(selId);}
  else if(!ctrl&&e.key==='Backspace'&&selId){e.preventDefault();promptDel(selId);}
  else if(matchShortcut('escape',e)){deselect();closePanel();}
  else if(matchShortcut('fitView',e)&&!ctrl){fitView();}
  else if(matchShortcut('addSibling',e)&&selId){e.preventDefault();addSibling(selId);}
  else if(matchShortcut('addChild',e)&&selId){e.preventDefault();addChild(selId);}
});

/* Add sibling node */
function addSibling(id){
  const n=findNode(id); if(!n) return;
  const nn=newNode();
  nn.parentId=n.parentId;
  nn.x=n.x+(NODE_W+40);
  nn.y=n.y;
  nodes.push(nn);
  saveData(); renderNodes();
  openPanel(nn.id);
  toast('已新增同層節點');
}

/* ═══════════════════════════════════════
   STATS
═══════════════════════════════════════ */
function updateStats(){
  const total=nodes.filter(n=>n.status!==null).length;
  const green=nodes.filter(n=>n.status==='green').length;
  const yellow=nodes.filter(n=>n.status==='yellow').length;
  const red=nodes.filter(n=>n.status==='red').length;
  document.getElementById('header-stats').innerHTML=`
    <div class="stat stat-btn" onclick="jumpToStatus('green')" title="查看高意願聯繫人"><span class="stat-dot" style="background:var(--green)"></span>${green} 高意願</div>
    <div class="stat stat-btn" onclick="jumpToStatus('yellow')" title="查看觀察中聯繫人"><span class="stat-dot" style="background:var(--yellow)"></span>${yellow} 觀察中</div>
    <div class="stat stat-btn" onclick="jumpToStatus('red')" title="查看冷淡聯繫人"><span class="stat-dot" style="background:var(--red)"></span>${red} 冷淡</div>
    <div class="stat stat-btn" onclick="jumpToStatus(null)" title="查看全部聯繫人"><span class="stat-dot" style="background:var(--border-hover)"></span>${total} 總計</div>`;
}

function jumpToStatus(status){
  crmStatusFilter=status;
  switchPage('crm');
  setCrmView('status');
}

/* ═══════════════════════════════════════
   SIDE PANEL
═══════════════════════════════════════ */
let panelNodeId=null;

function openPanel(id){
  const n=findNode(id);if(!n)return;
  panelNodeId=id;
  selectNode(id);
  document.getElementById('panel-title').textContent=n.name||'聯繫人資料';
  renderPanel(n);
  document.getElementById('side-panel').classList.add('open');
}

function closePanel(){
  document.getElementById('side-panel').classList.remove('open');
  panelNodeId=null;
}

function savePanel(){
  if(!panelNodeId)return;
  const n=findNode(panelNodeId);if(!n)return;
  const body=document.getElementById('panel-body');
  // name
  const nameEl=body.querySelector('[data-field="name"]');
  if(nameEl)n.name=nameEl.value;
  // info fields
  body.querySelectorAll('[data-info]').forEach(el=>{
    const k=el.dataset.info;
    if(el.type==='checkbox'){/* handled via cb-item */}
    else n.info[k]=el.value;
  });
  // tags
  const tagsEl=body.querySelector('[data-info="tags-input"]');
  if(tagsEl)n.info.tags=tagsEl.value.split(',').map(s=>s.trim()).filter(Boolean);
  // needs checkboxes
  const needsChecked=[];
  body.querySelectorAll('[data-need].checked').forEach(el=>needsChecked.push(el.dataset.need));
  n.info.needs=needsChecked;
  // regions checkboxes
  const regionsChecked=[];
  body.querySelectorAll('[data-region].checked').forEach(el=>regionsChecked.push(el.dataset.region));
  n.info.regions=regionsChecked;

  document.getElementById('panel-title').textContent=n.name||'聯繫人資料';
  saveData();
  // update node card
  const wrap=document.querySelector(`.node-wrap[data-id="${n.id}"]`);
  if(wrap){
    const nameDiv=wrap.querySelector('.node-name');
    if(nameDiv){nameDiv.textContent=n.name;nameDiv.title=n.name;}
    const avatar=wrap.querySelector('.node-avatar');
    if(avatar)avatar.textContent=(n.name||'?')[0];
    const meta=wrap.querySelector('.node-meta');
    if(meta)meta.textContent=n.info.company||(n.info.tags&&n.info.tags[0])||'';
    // update role pill
    const ROLE_MAP={潛在客戶:'role-prospect',轉介紹中心:'role-referral',學員:'role-student',從業人員:'role-agent'};
    let rolePill=wrap.querySelector('.node-role-pill');
    if(n.info.role){
      if(!rolePill){rolePill=document.createElement('div');rolePill.className='node-role-pill';wrap.querySelector('.node-card').insertBefore(rolePill,wrap.querySelector('.node-footer'));}
      rolePill.className='node-role-pill '+(ROLE_MAP[n.info.role]||'');
      rolePill.textContent=n.info.role;
    } else if(rolePill){rolePill.remove();}
    // update region tags
    let regionDiv=wrap.querySelector('.node-region-tags');
    if(n.info.regions&&n.info.regions.length){
      if(!regionDiv){regionDiv=document.createElement('div');regionDiv.className='node-region-tags';wrap.querySelector('.node-card').insertBefore(regionDiv,wrap.querySelector('.node-footer'));}
      regionDiv.innerHTML=n.info.regions.map(r=>`<span class="node-region-tag">${r}</span>`).join('');
    } else if(regionDiv){regionDiv.remove();}
  }
  updateStats();
}

function renderPanel(n){
  const body=document.getElementById('panel-body');
  const inf=n.info;

  const needsOptions=['買房','買車','子女教育','退休規劃','保障規劃','創業資金','學習成長','財富自由'];
  const needsHtml=needsOptions.map(nd=>`<div class="cb-item${(inf.needs||[]).includes(nd)?' checked':''}" data-need="${nd}" onclick="toggleNeed(this,'${nd}')">${nd}</div>`).join('');

  const tagsVal=(inf.tags||[]).join(', ');
  const REGION_OPTIONS=['台北','新北','桃園','新竹','台中','彰化','台南','高雄','其他'];
  const regionsHtml=REGION_OPTIONS.map(r=>`<div class="cb-item${(inf.regions||[]).includes(r)?' checked':''}" data-region="${r}" onclick="toggleRegion(this,'${r}')">${r}</div>`).join('');
  const ROLES=['潛在客戶','轉介紹中心','學員','從業人員'];

  body.innerHTML=`
    <!-- 基本資料 -->
    <div class="field-group">
      <div class="field-label">姓名</div>
      <input class="field-input" data-field="name" value="${escHtml(n.name)}" oninput="savePanel()" placeholder="姓名">
    </div>
    <div class="field-row">
      <div class="field-group">
        <div class="field-label">身份標籤</div>
        <select class="field-input" data-info="role" onchange="savePanel()">
          <option value="">— 未設定 —</option>
          ${ROLES.map(r=>`<option value="${r}"${inf.role===r?' selected':''}>${r}</option>`).join('')}
        </select>
      </div>
      <div class="field-group">
        <div class="field-label">地區（可複選）</div>
        <div class="cb-group" style="flex-wrap:wrap;gap:4px;display:flex">${regionsHtml}</div>
      </div>
    </div>

    <div class="accordion open">
      <div class="acc-header" onclick="toggleAcc(this)">基本資料 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="field-row">
          <div class="field-group"><div class="field-label">年齡</div><input class="field-input" data-info="age" value="${escHtml(inf.age)}" oninput="savePanel()" placeholder="歲"></div>
          <div class="field-group"><div class="field-label">星座</div><input class="field-input" data-info="zodiac" value="${escHtml(inf.zodiac)}" oninput="savePanel()" placeholder="星座"></div>
        </div>
        <div class="field-group"><div class="field-label">家鄉</div><input class="field-input" data-info="hometown" value="${escHtml(inf.hometown)}" oninput="savePanel()" placeholder="家鄉"></div>
        <div class="field-group"><div class="field-label">個性</div><input class="field-input" data-info="personality" value="${escHtml(inf.personality)}" oninput="savePanel()" placeholder="個性特質"></div>
        <div class="field-group"><div class="field-label">興趣</div><input class="field-input" data-info="interests" value="${escHtml(inf.interests)}" oninput="savePanel()" placeholder="興趣愛好"></div>
        <div class="field-group"><div class="field-label">認識方式</div><input class="field-input" data-info="howMet" value="${escHtml(inf.howMet)}" oninput="savePanel()" placeholder="如何認識"></div>
        <div class="field-group"><div class="field-label">背景</div><textarea class="field-input field-textarea" data-info="background" oninput="savePanel()" placeholder="背景說明">${escHtml(inf.background)}</textarea></div>
        <div class="field-group"><div class="field-label">公司</div><input class="field-input" data-info="company" value="${escHtml(inf.company)}" oninput="savePanel()" placeholder="公司名稱"></div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">電話</div><input class="field-input" data-info="phone" value="${escHtml(inf.phone)}" oninput="savePanel()" placeholder="手機"></div>
          <div class="field-group"><div class="field-label">Email</div><input class="field-input" data-info="email" value="${escHtml(inf.email)}" oninput="savePanel()" placeholder="信箱"></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">來源</div><input class="field-input" data-info="source" value="${escHtml(inf.source)}" oninput="savePanel()" placeholder="來源"></div>
          <div class="field-group"><div class="field-label">最後聯絡</div><input class="field-input" type="date" data-info="lastContact" value="${escHtml(inf.lastContact)}" oninput="savePanel()"></div>
        </div>
        <div class="field-group"><div class="field-label">標籤（逗號分隔）</div><input class="field-input" data-info="tags-input" value="${escHtml(tagsVal)}" oninput="savePanel()" placeholder="VIP, 客戶, 介紹人"></div>
        <div class="field-group"><div class="field-label">備注</div><textarea class="field-input field-textarea" data-info="notes" oninput="savePanel()" placeholder="備注說明">${escHtml(inf.notes)}</textarea></div>
      </div>
    </div>

    <div class="accordion">
      <div class="acc-header" onclick="toggleAcc(this)">工作背景 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="field-row">
          <div class="field-group"><div class="field-label">現職</div><input class="field-input" data-info="currentJob" value="${escHtml(inf.currentJob)}" oninput="savePanel()" placeholder="職稱/職務"></div>
          <div class="field-group"><div class="field-label">年資</div><input class="field-input" data-info="jobDuration" value="${escHtml(inf.jobDuration)}" oninput="savePanel()" placeholder="幾年"></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">前職</div><input class="field-input" data-info="prevJob" value="${escHtml(inf.prevJob)}" oninput="savePanel()" placeholder="前職職稱"></div>
          <div class="field-group"><div class="field-label">前職層級</div><input class="field-input" data-info="prevJobLevel" value="${escHtml(inf.prevJobLevel)}" oninput="savePanel()" placeholder="層級"></div>
        </div>
      </div>
    </div>

    <div class="accordion">
      <div class="acc-header" onclick="toggleAcc(this)">財務狀況 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="field-row">
          <div class="field-group"><div class="field-label">收入</div><input class="field-input" data-info="income" value="${escHtml(inf.income)}" oninput="savePanel()" placeholder="月收 / 年收"></div>
          <div class="field-group"><div class="field-label">薪轉</div><select class="field-input" data-info="salaryTransfer" onchange="savePanel()"><option value="">—</option><option${inf.salaryTransfer==='是'?' selected':''}>是</option><option${inf.salaryTransfer==='否'?' selected':''}>否</option></select></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">名下房產</div><input class="field-input" data-info="hasProperty" value="${escHtml(inf.hasProperty)}" oninput="savePanel()" placeholder="有/無/幾間"></div>
          <div class="field-group"><div class="field-label">家庭房產</div><input class="field-input" data-info="familyProperty" value="${escHtml(inf.familyProperty)}" oninput="savePanel()" placeholder="有/無"></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">有無投資</div><select class="field-input" data-info="hasInvestment" onchange="savePanel()"><option value="">—</option><option${inf.hasInvestment==='是'?' selected':''}>是</option><option${inf.hasInvestment==='否'?' selected':''}>否</option></select></div>
          <div class="field-group"><div class="field-label">有無保險</div><select class="field-input" data-info="hasInsurance" onchange="savePanel()"><option value="">—</option><option${inf.hasInsurance==='是'?' selected':''}>是</option><option${inf.hasInsurance==='否'?' selected':''}>否</option></select></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">信用卡</div><input class="field-input" data-info="creditCard" value="${escHtml(inf.creditCard)}" oninput="savePanel()" placeholder="有/無/張數"></div>
          <div class="field-group"><div class="field-label">負債</div><input class="field-input" data-info="debt" value="${escHtml(inf.debt)}" oninput="savePanel()" placeholder="有/無/金額"></div>
        </div>
      </div>
    </div>

    <div class="accordion">
      <div class="acc-header" onclick="toggleAcc(this)">邀約資訊 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="field-group"><div class="field-label">邀約方式</div><input class="field-input" data-info="invitationMethod" value="${escHtml(inf.invitationMethod)}" oninput="savePanel()" placeholder="電話/面邀/介紹"></div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">告知場地費</div><select class="field-input" data-info="knowsVenueFee" onchange="savePanel()"><option value="">—</option><option${inf.knowsVenueFee==='是'?' selected':''}>是</option><option${inf.knowsVenueFee==='否'?' selected':''}>否</option></select></div>
          <div class="field-group"><div class="field-label">告知學費79800</div><select class="field-input" data-info="knowsTuition" onchange="savePanel()"><option value="">—</option><option${inf.knowsTuition==='是'?' selected':''}>是</option><option${inf.knowsTuition==='否'?' selected':''}>否</option></select></div>
        </div>
        <div class="field-group"><div class="field-label">關鍵問題</div><textarea class="field-input field-textarea" data-info="keyQuestions" oninput="savePanel()" placeholder="客戶提出的關鍵問題">${escHtml(inf.keyQuestions)}</textarea></div>
        <div class="field-group">
          <div class="field-label">需求（多選）</div>
          <div class="checkbox-group">${needsHtml}</div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">可自行決定</div><select class="field-input" data-info="canDecide" onchange="savePanel()"><option value="">—</option><option${inf.canDecide==='是'?' selected':''}>是</option><option${inf.canDecide==='否'?' selected':''}>否</option></select></div>
          <div class="field-group"><div class="field-label">當場付款</div><select class="field-input" data-info="payOnSite" onchange="savePanel()"><option value="">—</option><option${inf.payOnSite==='是'?' selected':''}>是</option><option${inf.payOnSite==='否'?' selected':''}>否</option></select></div>
        </div>
      </div>
    </div>

    <div class="accordion">
      <div class="acc-header" onclick="toggleAcc(this)">C單資訊 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="field-row">
          <div class="field-group"><div class="field-label">活動日期</div><input class="field-input" type="date" data-info="eventDate" value="${escHtml(inf.eventDate)}" oninput="savePanel()"></div>
          <div class="field-group"><div class="field-label">活動名稱</div><input class="field-input" data-info="eventName" value="${escHtml(inf.eventName)}" oninput="savePanel()" placeholder="活動名稱"></div>
        </div>
        <div class="field-row">
          <div class="field-group"><div class="field-label">邀約人</div><input class="field-input" data-info="referrer" value="${escHtml(inf.referrer)}" oninput="savePanel()" placeholder="邀約人姓名"></div>
          <div class="field-group"><div class="field-label">推薦人</div><input class="field-input" data-info="recommender" value="${escHtml(inf.recommender)}" oninput="savePanel()" placeholder="推薦人姓名"></div>
        </div>
        <div class="field-group"><div class="field-label">表單備注</div><textarea class="field-input field-textarea" data-info="formNotes" oninput="savePanel()" placeholder="其他說明">${escHtml(inf.formNotes)}</textarea></div>
      </div>
    </div>

    <!-- C單 Export -->
    <div class="accordion">
      <div class="acc-header" onclick="toggleAcc(this)">📋 C單輸出 <span class="acc-chevron">▲</span></div>
      <div class="acc-body">
        <div class="export-box" id="export-preview">${buildCSheet(n)}</div>
        <button class="btn btn-sm" style="width:100%" onclick="copyCSheet()">複製 C單</button>
      </div>
    </div>
  `;
}

function toggleNeed(el,need){
  el.classList.toggle('checked');
  savePanel();
}

function toggleRegion(el,region){
  el.classList.toggle('checked');
  savePanel();
}

function toggleAcc(header){
  const acc=header.closest('.accordion');
  acc.classList.toggle('open');
}

function escHtml(s){
  if(!s&&s!==0)return'';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ═══════════════════════════════════════
   C單 BUILD
═══════════════════════════════════════ */
function toROCDate(dateStr){
  if(!dateStr)return'';
  try{
    const d=new Date(dateStr);
    const y=d.getFullYear()-1911;
    const m=String(d.getMonth()+1).padStart(2,'0');
    const day=String(d.getDate()).padStart(2,'0');
    return`民國${y}年${m}月${day}日`;
  }catch(e){return dateStr;}
}

function buildCSheet(n){
  if(!n)return'';
  const i=n.info;
  const lines=[
    `姓名：${n.name||''}`,
    `年齡：${i.age||''} 歲　星座：${i.zodiac||''}　家鄉：${i.hometown||''}`,
    `個性：${i.personality||''}　興趣：${i.interests||''}`,
    `認識方式：${i.howMet||''}`,
    `背景：${i.background||''}`,
    ``,
    `── 工作 ──`,
    `現職：${i.currentJob||''} / 年資：${i.jobDuration||''}`,
    `前職：${i.prevJob||''} / 層級：${i.prevJobLevel||''}`,
    ``,
    `── 財務 ──`,
    `收入：${i.income||''}　薪轉：${i.salaryTransfer||''}`,
    `名下房產：${i.hasProperty||''}　家庭房產：${i.familyProperty||''}`,
    `投資：${i.hasInvestment||''}　保險：${i.hasInsurance||''}　信用卡：${i.creditCard||''}　負債：${i.debt||''}`,
    ``,
    `── 邀約 ──`,
    `邀約方式：${i.invitationMethod||''}`,
    `告知場地費：${i.knowsVenueFee||''}　告知學費79800：${i.knowsTuition||''}`,
    `需求：${(i.needs||[]).join('、')||''}`,
    `關鍵問題：${i.keyQuestions||''}`,
    `可自行決定：${i.canDecide||''}　當場付款：${i.payOnSite||''}`,
    ``,
    `── C單 ──`,
    `活動日期：${toROCDate(i.eventDate)}`,
    `活動名稱：${i.eventName||''}`,
    `邀約人：${i.referrer||''}　推薦人：${i.recommender||''}`,
    `備注：${i.formNotes||''}`,
  ];
  return lines.join('\n');
}

function copyCSheet(){
  if(!panelNodeId)return;
  const n=findNode(panelNodeId);if(!n)return;
  navigator.clipboard.writeText(buildCSheet(n)).then(()=>toast('C單已複製到剪貼板'));
}

/* ═══════════════════════════════════════
   EVENTS PAGE — MONTHLY CALENDAR
═══════════════════════════════════════ */
let editingEventId=null;
let calYear=new Date().getFullYear();
let calMonth=new Date().getMonth(); // 0-based

function calTodayStr(){return new Date().toISOString().slice(0,10);}

function calPrev(){calMonth--;if(calMonth<0){calMonth=11;calYear--;}renderCalendar();}
function calNext(){calMonth++;if(calMonth>11){calMonth=0;calYear++;}renderCalendar();}
function calGoToday(){const d=new Date();calYear=d.getFullYear();calMonth=d.getMonth();renderCalendar();}

// Alias for switchPage to call
function renderEvents(){renderCalendar();}

function renderCalendar(){
  const label=document.getElementById('cal-month-label');
  if(!label)return;
  const MONTHS=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  label.textContent=`${calYear} 年 ${MONTHS[calMonth]}`;

  const grid=document.getElementById('cal-grid');
  if(!grid)return;

  const today=calTodayStr();
  // First day of month weekday (0=Sun)
  const firstDay=new Date(calYear,calMonth,1).getDay();
  // Days in month
  const daysInMonth=new Date(calYear,calMonth+1,0).getDate();
  // Days in prev month
  const daysInPrev=new Date(calYear,calMonth,0).getDate();

  const cells=[];
  // Leading days from prev month
  for(let i=firstDay-1;i>=0;i--){
    cells.push({day:daysInPrev-i,month:calMonth-1,year:calMonth===0?calYear-1:calYear,other:true});
  }
  // This month
  for(let d=1;d<=daysInMonth;d++){
    cells.push({day:d,month:calMonth,year:calYear,other:false});
  }
  // Trailing days to fill 6 rows × 7
  const needed=42-cells.length;
  for(let d=1;d<=needed;d++){
    cells.push({day:d,month:calMonth+1,year:calMonth===11?calYear+1:calYear,other:true});
  }

  grid.innerHTML=cells.map(c=>{
    const dateStr=`${c.year}-${String(c.month+1).padStart(2,'0')}-${String(c.day).padStart(2,'0')}`;
    const isToday=dateStr===today;
    const dayEvents=events.filter(ev=>ev.date===dateStr);
    const chips=dayEvents.slice(0,3).map(ev=>`<div class="cal-chip" data-type="${ev.type||''}" onclick="event.stopPropagation();openEventModal('${ev.id}')">${escHtml(ev.type||ev.name||'活動')}</div>`).join('');
    const more=dayEvents.length>3?`<div class="cal-more">+${dayEvents.length-3} 更多</div>`:'';
    return`<div class="cal-cell${c.other?' other-month':''}${isToday?' today':''}" onclick="openEventModal(null,'${dateStr}')">
      <div class="cal-day-num">${c.day}</div>
      ${chips}${more}
    </div>`;
  }).join('');
}

const EV_TYPES=['分享會','專場','訓練','二對一'];
function openEventModal(id,defaultDate){
  if(!CMD.allowed('event.open')){ toast('此指令已被停用'); return; }
  editingEventId=id||null;
  const ev=id?events.find(e=>e.id===id):null;
  document.getElementById('event-modal-title').textContent=ev?'編輯活動':'新增活動';
  const dateVal=ev?.date||defaultDate||'';
  const selPax=ev?.participants||[];
  const contactNodes=nodes.filter(n=>n.status!==null&&n.name&&n.name!=='新聯繫人');
  const typeOpts=EV_TYPES.map(t=>`<option value="${t}"${(ev?.type||'分享會')===t?' selected':''}>${t}</option>`).join('');
  const paxTags=contactNodes.length?contactNodes.map(n=>`
    <div class="ev-pax${selPax.includes(n.id)?' selected':''}" data-nid="${n.id}" onclick="this.classList.toggle('selected')">
      <span class="sdot ${n.status||'gray'}"></span>${escHtml(n.name)}
    </div>`).join(''):'<span style="color:var(--text-muted);font-size:12px">尚無人脈節點</span>';
  document.getElementById('event-modal-body').innerHTML=`
    <div class="field-row">
      <div class="field-group"><div class="field-label">類型</div><select class="field-input" id="ev-type">${typeOpts}</select></div>
      <div class="field-group"><div class="field-label">日期</div><input class="field-input" type="date" id="ev-date" value="${dateVal}"></div>
    </div>
    <div class="field-row">
      <div class="field-group"><div class="field-label">時間</div><input class="field-input" type="time" id="ev-time" value="${ev?.time||''}"></div>
      <div class="field-group"><div class="field-label">地點</div><input class="field-input" id="ev-location" value="${escHtml(ev?.location||'')}" placeholder="地點"></div>
    </div>
    <div class="field-group"><div class="field-label">邀約人脈</div><div class="ev-participants">${paxTags}</div></div>
    <div class="field-group"><div class="field-label">備注</div><textarea class="field-input field-textarea" id="ev-notes" placeholder="備注">${escHtml(ev?.notes||'')}</textarea></div>
    ${ev?`<div style="margin-top:8px"><button class="btn btn-danger btn-sm" onclick="deleteEvent('${ev.id}');closeEventModal()">🗑 刪除此活動</button></div>`:''}
  `;
  document.getElementById('event-modal').classList.add('open');
}

function closeEventModal(){
  document.getElementById('event-modal').classList.remove('open');
  editingEventId=null;
}

function saveEvent(){
  if(!CMD.allowed('event.save')){ toast('此指令已被停用'); return; }
  const type=document.getElementById('ev-type').value;
  const participants=[...document.querySelectorAll('#event-modal .ev-pax.selected')].map(el=>el.dataset.nid);
  const ev={
    id:editingEventId||uid(),
    type,
    name:type,
    date:document.getElementById('ev-date').value,
    time:document.getElementById('ev-time').value,
    location:document.getElementById('ev-location').value,
    participants,
    notes:document.getElementById('ev-notes').value,
  };
  if(editingEventId){
    const idx=events.findIndex(e=>e.id===editingEventId);
    if(idx>=0)events[idx]=ev;
  } else {
    events.push(ev);
  }
  localStorage.setItem('crm-events',JSON.stringify(events));
  closeEventModal();
  renderCalendar();
  toast(editingEventId?'活動已更新':'活動已新增');
}

function deleteEvent(id){
  if(!CMD.allowed('event.delete')){ toast('此指令已被停用'); return; }
  if(!confirm('確定刪除此活動？'))return;
  events=events.filter(e=>e.id!==id);
  localStorage.setItem('crm-events',JSON.stringify(events));
  renderCalendar();
  toast('活動已刪除');
}

/* ═══════════════════════════════════════
   AI MODEL SETTINGS
═══════════════════════════════════════ */
const AI_PROVIDERS={
  claude:{
    label:'Claude (Anthropic)',
    models:['claude-sonnet-4-6','claude-opus-4-6','claude-haiku-4-5-20251001','claude-3-5-haiku-20241022'],
    keyPlaceholder:'sk-ant-…'
  },
  openai:{
    label:'GPT (OpenAI)',
    models:['gpt-4o','gpt-4o-mini','gpt-4-turbo','gpt-3.5-turbo'],
    keyPlaceholder:'sk-…'
  },
  gemini:{
    label:'Gemini (Google)',
    models:['gemini-2.0-flash','gemini-1.5-pro','gemini-1.5-flash'],
    keyPlaceholder:'AIza…'
  },
  grok:{
    label:'Grok (xAI)',
    models:['grok-3-beta','grok-3-mini-beta','grok-2-1212'],
    keyPlaceholder:'xai-…'
  },
  custom:{
    label:'自定義',
    models:[],
    keyPlaceholder:'API Key…'
  }
};

function getAiSettings(){
  return{
    provider:localStorage.getItem(STORE.K.aiProvider)||'claude',
    model:localStorage.getItem(STORE.K.aiModel)||'claude-3-5-haiku-20241022',
    apiKey:localStorage.getItem(STORE.K.apiKey)||'',
    endpoint:localStorage.getItem(STORE.K.aiEndpoint)||''
  };
}

function saveAiSettings(){
  const provider=document.getElementById('ai-provider-select')?.value||'claude';
  const model=document.getElementById('ai-model-select')?.value||'';
  const apiKey=document.getElementById('ai-apikey-input')?.value||'';
  const endpoint=document.getElementById('ai-custom-endpoint')?.value||'';
  localStorage.setItem(STORE.K.aiProvider, provider);
  localStorage.setItem(STORE.K.aiModel,    model);
  localStorage.setItem(STORE.K.apiKey,     apiKey);
  localStorage.setItem(STORE.K.aiEndpoint, endpoint);
  updateAiModelBadge();
}

function onAiProviderChange(){
  const provider=document.getElementById('ai-provider-select')?.value||'claude';
  const ms=document.getElementById('ai-model-select');
  if(!ms)return;
  const p=AI_PROVIDERS[provider];
  if(provider==='custom'){
    ms.innerHTML='<option value="">自定義模型名稱</option>';
    ms.removeAttribute('disabled');
    ms.style.display='none';
    // show a text input for model name instead
    let mi=document.getElementById('ai-custom-model-input');
    if(!mi){
      mi=document.createElement('input');
      mi.className='field-input';mi.id='ai-custom-model-input';
      mi.placeholder='模型名稱（如 gpt-4o）';mi.style.flex='1';mi.style.minWidth='160px';
      mi.oninput=saveAiSettings;
      ms.parentNode.insertBefore(mi,ms.nextSibling);
    } else {mi.style.display='';}
    document.getElementById('ai-custom-endpoint-row').style.display='flex';
  } else {
    ms.style.display='';
    const mi=document.getElementById('ai-custom-model-input');
    if(mi)mi.style.display='none';
    ms.innerHTML=p.models.map(m=>`<option value="${m}">${m}</option>`).join('');
    document.getElementById('ai-custom-endpoint-row').style.display='none';
  }
  const ki=document.getElementById('ai-apikey-input');
  if(ki)ki.placeholder=p.keyPlaceholder||'API Key…';
  saveAiSettings();
}

function renderAiSettingsCard(){
  const s=getAiSettings();
  const ps=document.getElementById('ai-provider-select');
  if(ps){ps.value=s.provider;}
  const p=AI_PROVIDERS[s.provider]||AI_PROVIDERS.claude;
  const ms=document.getElementById('ai-model-select');
  if(ms){
    if(s.provider==='custom'){
      ms.style.display='none';
      let mi=document.getElementById('ai-custom-model-input');
      if(mi){mi.style.display='';mi.value=s.model;}
      document.getElementById('ai-custom-endpoint-row').style.display='flex';
      const ep=document.getElementById('ai-custom-endpoint');
      if(ep)ep.value=s.endpoint;
    } else {
      ms.style.display='';
      ms.innerHTML=p.models.map(m=>`<option value="${m}">${m}</option>`).join('');
      if(s.model)ms.value=s.model;
      document.getElementById('ai-custom-endpoint-row').style.display='none';
    }
  }
  const ki=document.getElementById('ai-apikey-input');
  if(ki){ki.value=s.apiKey;ki.placeholder=p.keyPlaceholder||'API Key…';}
  const st=document.getElementById('ai-settings-status');
  if(st)st.textContent=s.apiKey?'✅ API Key 已設定':'⚠ 尚未設定 API Key';
  updateAiModelBadge();
}

function updateAiModelBadge(){
  const s=getAiSettings();
  const badge=document.getElementById('ai-model-badge');
  if(badge){
    const p=AI_PROVIDERS[s.provider]||{label:s.provider};
    badge.textContent=`模型：${p.label} / ${s.model||'未設定'}`;
  }
}

/* ═══════════════════════════════════════
   AI — PERSONA & CONTEXT  (Phase 1)
═══════════════════════════════════════ */
let currentPersona='assistant';

const PERSONA_CONFIG={
  assistant:{
    label:'通用助理',
    rolePrompt:'你是房多多業務智能助理，全方位支援業務員的日常工作。',
    quickPrompts:['今天要跟進誰？','本月業績狀況如何？','知識庫裡有什麼文件？','最近冷掉的客戶有哪些？']
  },
  coach:{
    label:'跟進教練',
    rolePrompt:'你是專業業務跟進教練，專注分析客戶心理與關係進展，提供具體話術、破冰策略與最佳跟進時機。',
    quickPrompts:['幫我想一個高意願客戶的跟進話術','如何重新聯繫冷掉的客戶？','下次拜訪要聊什麼？','如何推進猶豫不決的客戶？']
  },
  analyst:{
    label:'業績分析師',
    rolePrompt:'你是業績數字分析師，精通佣金計算、業績趨勢、目標達成率分析。用數字說話，找出業績瓶頸並提供改善方向。',
    quickPrompts:['本月業績卡在哪裡？','我的稅後收入怎麼算？','離目標還差多少？','哪種成交類型最划算？']
  },
  strategist:{
    label:'人脈策略師',
    rolePrompt:'你是人脈開發策略師，擅長分析人脈樹結構、尋找轉介紹機會、評估網絡廣度與深度，給出最優拓展路徑。',
    quickPrompts:['我的人脈樹有哪些弱點？','誰最有轉介紹潛力？','如何快速拓展新人脈？','分析我的人脈分布']
  },
  secretary:{
    label:'日報小秘書',
    rolePrompt:'你是日報填寫助理。用戶口述今天的工作狀況，你負責提取結構化數字（邀約、電訪、表單、追蹤、成交）並整理成日報格式，再詢問確認。你也可以查詢知識庫中的表單與問卷連結。',
    quickPrompts:['幫我填今天的日報','今天打了10通電話、約到3組','找問卷或表單連結','根據我的目標今天達標了嗎？']
  }
};

function buildSystemPrompt(personaKey){
  const persona=PERSONA_CONFIG[personaKey||'assistant'];
  const login=JSON.parse(localStorage.getItem('crm-login')||'{}');
  const myRank=STORE.getMyRank();
  const myRate=STORE.getMyRate();
  const now=new Date();
  const today=now.toISOString().slice(0,10);
  const monthPrefix=today.slice(0,7);
  const daysLeft=new Date(now.getFullYear(),now.getMonth()+1,0).getDate()-now.getDate();

  const contactNodes=nodes.filter(n=>n.parentId!==null);
  const green=contactNodes.filter(n=>n.status==='green');
  const yellow=contactNodes.filter(n=>n.status==='yellow');
  const red=contactNodes.filter(n=>n.status==='red');
  const stale=contactNodes.filter(n=>{
    if(!n.info||!n.info.lastContact)return false;
    return Math.floor((new Date(today)-new Date(n.info.lastContact))/86400000)>7
      &&(n.status==='green'||n.status==='yellow');
  }).map(n=>`${n.name}（${Math.floor((new Date(today)-new Date(n.info.lastContact))/86400000)}天）`);

  const summary=CALC.monthSummary(salesData,myRate,monthPrefix);
  const salesTarget=monthlySalesTargets[monthPrefix]||300000;
  const salesPct=salesTarget>0?Math.round(summary.income/salesTarget*100):0;
  const todayRpt=dailyReports[today]||{};
  const upcoming=events.filter(ev=>ev.date>=today).slice(0,5).map(ev=>`${ev.date} ${ev.title}`);
  const rankLabels={director:'主任',asst_mgr:'襄理',manager:'經理',shop_partner:'店股東',shop_head:'店長'};

  return `${persona.rolePrompt}

【使用者】${login.name||'業務員'}｜${rankLabels[myRank]||myRank}｜佣金率 ${(myRate*100).toFixed(0)}%
【今日】${today}，月底還有 ${daysLeft} 天
【本月業績】$${summary.income.toLocaleString()} / 目標 $${salesTarget.toLocaleString()}（${salesPct}%）稅後 $${summary.net.toLocaleString()}，成交 ${summary.newCount} 件
【人脈概況】共 ${contactNodes.length} 人｜🟢高意願 ${green.length}（${green.map(n=>n.name).join('、')||'無'}）｜🟡觀察中 ${yellow.length}｜🔴冷淡 ${red.length}
⚠ 超過7天未聯繫：${stale.join('、')||'無'}
【今日活動量】邀約${todayRpt.invite||0} 電訪${todayRpt.calls||0} 表單${todayRpt.forms||0} 追蹤${todayRpt.followup||0} 成交${todayRpt.close||0}
【近期活動】${upcoming.length?upcoming.join('；'):'無'}

【知識庫文件】${docsData.length?docsData.map(d=>{
  const icon={poster:'🖼',form:'📋',link:'🔗',file:'📄'}[d.type]||'📄';
  return `${icon}《${d.name}》${d.url?'→ '+d.url:''}`;
}).join('　'):'尚無文件'}

【可用工具】update_contact_status / add_note / log_contact / get_followup_list / search_docs

請用繁體中文回答，語氣專業親切，重點條列清晰。`;
}

/* ── Tool definitions  (Phase 2) ─────────────────── */
const CRM_TOOLS=[
  {name:'update_contact_status',
   description:'更新聯繫人的跟進狀態',
   input_schema:{type:'object',
     properties:{
       name:{type:'string',description:'聯繫人姓名（支援部分匹配）'},
       status:{type:'string',enum:['green','yellow','red','gray'],
               description:'green=高意願 yellow=觀察中 red=冷淡 gray=無效'}
     },required:['name','status']}},
  {name:'add_note',
   description:'為聯繫人新增備注（自動加日期前綴）',
   input_schema:{type:'object',
     properties:{
       name:{type:'string',description:'聯繫人姓名'},
       note:{type:'string',description:'備注內容'}
     },required:['name','note']}},
  {name:'log_contact',
   description:'記錄今日已與聯繫人接觸，lastContact 更新為今天',
   input_schema:{type:'object',
     properties:{name:{type:'string',description:'聯繫人姓名（部分匹配）'}},
     required:['name']}},
  {name:'get_followup_list',
   description:'取得超過指定天數未聯繫的高/中意願客戶清單',
   input_schema:{type:'object',
     properties:{days:{type:'number',description:'超過幾天，預設7'}}}},
  {name:'search_docs',
   description:'搜尋知識庫文件。可依名稱關鍵字篩選，或列出全部文件清單及連結',
   input_schema:{type:'object',
     properties:{query:{type:'string',description:'搜尋關鍵字，留空則列出全部'}}}}
];

function executeToolCall(name,input){
  const today=new Date().toISOString().slice(0,10);
  switch(name){
    case 'update_contact_status':{
      const n=nodes.find(nd=>nd.name&&nd.name.includes(input.name));
      if(!n)return{error:`找不到：${input.name}`};
      n.status=input.status;saveData();renderNodes();
      const lbl={green:'🟢高意願',yellow:'🟡觀察中',red:'🔴冷淡',gray:'⚪無效'};
      return{ok:true,msg:`已將「${n.name}」更新為 ${lbl[input.status]||input.status}`};
    }
    case 'add_note':{
      const n=nodes.find(nd=>nd.name&&nd.name.includes(input.name));
      if(!n)return{error:`找不到：${input.name}`};
      if(!n.info)n.info={};
      n.info.notes=(n.info.notes?n.info.notes+'\n':'')+`[${today}] ${input.note}`;
      saveData();
      return{ok:true,msg:`已為「${n.name}」新增備注`};
    }
    case 'log_contact':{
      const n=nodes.find(nd=>nd.name&&nd.name.includes(input.name));
      if(!n)return{error:`找不到：${input.name}`};
      if(!n.info)n.info={};
      n.info.lastContact=today;saveData();
      return{ok:true,msg:`已記錄今日聯繫「${n.name}」`};
    }
    case 'get_followup_list':{
      const days=input.days||7;
      const list=nodes.filter(nd=>{
        if(!nd.info||!nd.info.lastContact)return false;
        const d=Math.floor((new Date(today)-new Date(nd.info.lastContact))/86400000);
        return d>=days&&(nd.status==='green'||nd.status==='yellow');
      }).map(nd=>({name:nd.name,status:nd.status,lastContact:nd.info.lastContact,
        days:Math.floor((new Date(today)-new Date(nd.info.lastContact))/86400000)}));
      return{ok:true,list,count:list.length,
        msg:`找到 ${list.length} 位需跟進：${list.map(x=>x.name+'('+x.days+'天)').join('、')}`};
    }
    case 'search_docs':{
      const q=(input.query||'').toLowerCase().trim();
      const results=docsData.filter(d=>!q||d.name.toLowerCase().includes(q));
      if(!results.length)return{ok:true,msg:`知識庫中沒有符合「${q||'所有'}」的文件`,list:[]};
      const icon={poster:'🖼',form:'📋',link:'🔗',file:'📄'};
      const msg=results.map(d=>`${icon[d.type]||'📄'}《${d.name}》${d.url?d.url:''}`).join('\n');
      return{ok:true,count:results.length,msg,list:results.map(d=>({name:d.name,type:d.type,url:d.url||''}))};
    }
    default:return{error:`未知工具：${name}`};
  }
}

function setPersona(key,el){
  currentPersona=key;
  document.querySelectorAll('.persona-pill').forEach(p=>p.classList.remove('active'));
  if(el)el.classList.add('active');
  renderQuickPrompts(key);
}

let _quickPrompts=[];

function renderQuickPrompts(key){
  const bar=document.getElementById('ai-quick-prompts');
  if(!bar)return;
  _quickPrompts=(PERSONA_CONFIG[key]||PERSONA_CONFIG.assistant).quickPrompts;
  bar.innerHTML=_quickPrompts.map((p,i)=>
    `<button class="quick-prompt-chip" onclick="injectPrompt(${i})">${escHtml(p)}</button>`
  ).join('');
}

function injectPrompt(idx){
  const text=typeof idx==='number'?(_quickPrompts[idx]||''):idx;
  const inp=document.getElementById('chat-input');
  if(!inp)return;
  inp.value=text;inp.focus();autoResizeChat(inp);
}

/* Phase 3 — 今日簡報（本地生成 + 可掛 n8n） */
async function generateDailyBriefing(){
  const s=getAiSettings();
  if(!s.apiKey){toast('請先在設定中填入 API Key');switchPage('settings');return;}
  const input=document.getElementById('chat-input');
  input.value='幫我生成今日業務簡報：1)今天優先要做的3件事 2)需跟進的客戶清單 3)距月目標的差距與建議 4)一句給自己的激勵話語。格式清晰條列。';
  await sendChat();
}

/* ═══════════════════════════════════════
   AI PAGE — CHAT
═══════════════════════════════════════ */
function clearChat(){
  chatHistory=[];
  localStorage.setItem(STORE.K.chat,JSON.stringify(chatHistory));
  renderChat();
}

function renderChat(){
  const area=document.getElementById('chat-area');
  if(!area)return;
  if(!chatHistory.length){
    const login=JSON.parse(localStorage.getItem('crm-login')||'{}');
    area.innerHTML=`<div class="chat-msg system">嗨 ${login.name||'業務員'}！選一個角色，或直接輸入問題開始。</div>`;
    return;
  }
  area.innerHTML=chatHistory.map(m=>{
    if(m.role==='tool'){
      return`<div class="chat-msg tool-result"><span class="tool-icon">⚙</span>${escHtml(m.content)}</div>`;
    }
    let html=escHtml(m.content)
      .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
      .replace(/\n/g,'<br>');
    return`<div class="chat-msg ${m.role==='user'?'user':'ai'}">${html}</div>`;
  }).join('');
  area.scrollTop=area.scrollHeight;
}

function chatKeydown(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();}
}

function autoResizeChat(el){
  el.style.height='auto';
  el.style.height=Math.min(el.scrollHeight,120)+'px';
}

function setSendLoading(on){
  const btn=document.getElementById('send-btn');
  if(btn){btn.disabled=on;btn.textContent=on?'…':'發送';}
}

async function sendChat(){
  const input=document.getElementById('chat-input');
  const msg=input.value.trim();
  if(!msg)return;
  const s=getAiSettings();
  input.value='';input.style.height='auto';
  chatHistory.push({role:'user',content:msg});
  renderChat();setSendLoading(true);

  if(!s.apiKey){
    chatHistory.push({role:'assistant',content:'請先在「設定 > AI 模型設定」填入 API Key。'});
    renderChat();setSendLoading(false);
    localStorage.setItem(STORE.K.chat,JSON.stringify(chatHistory));
    return;
  }

  const systemMsg=buildSystemPrompt(currentPersona);

  try{
    if(s.provider==='claude'){
      /* ── Phase 2: Tool-calling loop ── */
      const messages=chatHistory
        .filter(m=>m.role==='user'||m.role==='assistant')
        .map(m=>({role:m.role,content:m.content}));

      let continueLoop=true;
      while(continueLoop){
        const res = s.apiKey
          ? await fetch('https://api.anthropic.com/v1/messages',{
              method:'POST',
              headers:{'Content-Type':'application/json','x-api-key':s.apiKey,
                'anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},
              body:JSON.stringify({model:s.model||'claude-3-5-haiku-20241022',
                max_tokens:1536,system:systemMsg,tools:CRM_TOOLS,messages})
            })
          : await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({provider:'anthropic',body:{model:s.model||'claude-3-5-haiku-20241022',
                max_tokens:1536,system:systemMsg,tools:CRM_TOOLS,messages}})});
        const d=await res.json();
        if(d.error){chatHistory.push({role:'assistant',content:d.error.message});break;}

        if(d.stop_reason==='tool_use'){
          const textBlocks=d.content.filter(b=>b.type==='text');
          const toolBlocks=d.content.filter(b=>b.type==='tool_use');
          if(textBlocks.length){
            chatHistory.push({role:'assistant',content:textBlocks.map(b=>b.text).join('')});
            renderChat();
          }
          messages.push({role:'assistant',content:d.content});
          const toolResults=[];
          for(const tb of toolBlocks){
            const result=executeToolCall(tb.name,tb.input);
            const txt=result.error?`❌ ${result.error}`:`✅ ${result.msg||JSON.stringify(result)}`;
            chatHistory.push({role:'tool',content:`[${tb.name}] ${txt}`});
            renderChat();
            toolResults.push({type:'tool_result',tool_use_id:tb.id,content:JSON.stringify(result)});
          }
          messages.push({role:'user',content:toolResults});
        } else {
          const txt=d.content?.filter(b=>b.type==='text').map(b=>b.text).join('')||'無回應';
          chatHistory.push({role:'assistant',content:txt});
          continueLoop=false;
        }
      }

    } else if(s.provider==='gemini'){
      const msgs=chatHistory
        .filter(m=>m.role==='user'||m.role==='assistant')
        .map(m=>({role:m.role==='user'?'user':'model',parts:[{text:m.content}]}));
      const res = s.apiKey
        ? await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${s.model||'gemini-2.0-flash'}:generateContent?key=${s.apiKey}`,{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({systemInstruction:{parts:[{text:systemMsg}]},contents:msgs})
          })
        : await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({provider:'gemini',body:{model:s.model||'gemini-2.0-flash',
              systemInstruction:{parts:[{text:systemMsg}]},contents:msgs}})});
      const d=await res.json();
      chatHistory.push({role:'assistant',content:d.candidates?.[0]?.content?.parts?.[0]?.text||d.error?.message||'無回應'});

    } else {
      const endpoint=s.provider==='custom'&&s.endpoint?s.endpoint
        :s.provider==='grok'?'https://api.x.ai/v1/chat/completions'
        :'https://api.openai.com/v1/chat/completions';
      const msgs=[{role:'system',content:systemMsg},
        ...chatHistory.filter(m=>m.role==='user'||m.role==='assistant')
          .map(m=>({role:m.role,content:m.content}))];
      const res = (!s.apiKey && endpoint.endsWith('/v1/chat/completions') && s.provider!=='grok' && s.provider!=='custom')
        ? await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({provider:'openai',body:{model:s.model,max_tokens:1536,messages:msgs}})})
        : await fetch(endpoint,{method:'POST',
            headers:{'Content-Type':'application/json','Authorization':`Bearer ${s.apiKey}`},
            body:JSON.stringify({model:s.model,max_tokens:1536,messages:msgs})
          });
      const d=await res.json();
      chatHistory.push({role:'assistant',content:d.choices?.[0]?.message?.content||d.error?.message||'無回應'});
    }
  }catch(e){
    chatHistory.push({role:'assistant',content:`網路錯誤：${e.message}`});
  }
  renderChat();setSendLoading(false);
  localStorage.setItem(STORE.K.chat,JSON.stringify(chatHistory));
}

/* ═══════════════════════════════════════
   PAGE SWITCHING
═══════════════════════════════════════ */
// display type each page needs when visible
const PAGE_DISPLAY={crm:'flex',daily:'block',events:'flex',docs:'block',sales:'block',ai:'flex',settings:'block'};

function switchPage(page){
  currentPage=page;
  // Hide all pages via inline style (bypass CSS specificity issues)
  document.querySelectorAll('.page').forEach(p=>{p.style.display='none';});
  // Show target page with correct display type
  const el=document.getElementById('page-'+page);
  if(el) el.style.display=PAGE_DISPLAY[page]||'block';
  // Update tab highlights
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  const idx={crm:0,daily:1,events:2,docs:3,sales:4,ai:5,settings:6}[page]??0;
  document.querySelectorAll('.tab-btn')[idx]?.classList.add('active');
  if(page==='crm'){setTimeout(()=>{drawEdges();},50);}
  if(page==='daily'){renderDailyPage();}
  if(page==='events'){renderCalendar();}
  if(page==='docs'){renderDocs();}
  if(page==='sales'){renderSales();}
  if(page==='ai'){renderChat();updateAiModelBadge();renderQuickPrompts(currentPersona);}
  if(page==='settings'){renderSettingsPage();}
}

/* ══════════════════════════════════════
   SALES / 業績 PAGE
══════════════════════════════════════ */
const SALES_TAX = 0.1211;
const TRANSFER_AMOUNT = 75440;
const RANK_RATES = {
  director:    0.15, // 主任
  asst_mgr:    0.20, // 襄理
  manager:     0.25, // 經理
  shop_partner:0.25, // 店股東
  shop_head:   0.25, // 店長
};
const RANK_LABELS = {
  director:'主任(15%)', asst_mgr:'襄理(20%)', manager:'經理(25%)',
  shop_partner:'店股東(25%)', shop_head:'店長(25%)',
};
function getMyRank(){ return STORE.getMyRank(); }
function getMyRate(){ return STORE.getMyRate(); }

// 批貨產品可見性：襄理含以下者不顯示
const BATCH_RESTRICTED_RANKS = new Set(['director', 'asst_mgr']);
function canSeeBatchProduct(productId){
  if(productId !== 'asst_mgr_pkg' && productId !== 'manager_pkg') return true;
  return !BATCH_RESTRICTED_RANKS.has(STORE.getMyRank());
}

// 批貨 anchor：利潤 = (我的職級% - anchor) × 批貨金額
// 升至襄理批貨(6×79800)：anchor=20%；升至經理批貨(15×79800)：anchor=15%
const BATCH_ANCHORS = { asst_mgr_pkg: 0.20, manager_pkg: 0.15 };

const SALES_PRODUCTS = {
  student:  { name:'學員',       price:79800,           color:'#3b82f6', bg:'rgba(59,130,246,.12)' },
  member:   { name:'會員服務',   price:200000,          color:'#8b5cf6', bg:'rgba(139,92,246,.12)' },
  vip:      { name:'VIP買房服務',price:300000,          color:'#f59e0b', bg:'rgba(245,158,11,.12)' },
  asst_mgr_pkg: { name:'襄理批貨', price:79800*6,       color:'#10b981', bg:'rgba(16,185,129,.12)' },
  manager_pkg:  { name:'經理批貨', price:79800*15,      color:'#ef4444', bg:'rgba(239,68,68,.12)'  },
  consult:  { name:'協談獎金',   price:Math.round(79800*0.03), color:'#06b6d4', bg:'rgba(6,182,212,.12)', perPerson:true, noSamerank:true },
};

let salesData = JSON.parse(localStorage.getItem(STORE.K.sales)||'[]');
let salesYear  = new Date().getFullYear();
let salesMonth = new Date().getMonth(); // 0-based

function saveSalesData(){ STORE.saveSales(); }
function salesPrevMonth(){ salesMonth--; if(salesMonth<0){salesMonth=11;salesYear--;} renderSales(); }
function salesNextMonth(){ salesMonth++; if(salesMonth>11){salesMonth=0;salesYear++;} renderSales(); }
function salesGoToday(){ salesYear=new Date().getFullYear(); salesMonth=new Date().getMonth(); renderSales(); }

function fmtMoney(n){ return 'NT$ '+Math.round(n).toLocaleString('zh-TW'); }
function parseMoneyText(s){
  if(s==null) return NaN;
  const cleaned = String(s).replace(/[^\d.-]/g,'');
  if(!cleaned) return NaN;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : NaN;
}

function renderSales(){
  const label = document.getElementById('sales-month-label');
  if(!label) return;
  const MONTHS=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  label.textContent = `${salesYear} 年 ${MONTHS[salesMonth]}`;

  const myRate  = STORE.getMyRate();
  const prefix  = `${salesYear}-${String(salesMonth+1).padStart(2,'0')}`;
  // ── CALC handles all arithmetic ──
  const { gross, transferTotal, bonusTotal, income, tax, net, newCount, bonusCount, totalCount, sorted } =
    CALC.monthSummary(salesData, myRate, prefix);

  const body = document.getElementById('sales-body');
  if(!body) return;

  const rankLabel = RANK_LABELS[STORE.getMyRank()] || '主任(15%)';

  const kpiHtml = `
  <div class="kpi-bar">
    <div class="kpi-card kpi-total">
      <div class="kpi-label">業績量（新業績）</div>
      <div class="kpi-value">${fmtMoney(gross)}</div>
      <div class="kpi-sub">${newCount} 筆 · 舊單轉讓 ${fmtMoney(transferTotal)}</div>
    </div>
    <div class="kpi-card kpi-net">
      <div class="kpi-label">我的所得 <span style="font-size:10px;font-weight:400">${rankLabel}</span></div>
      <div class="kpi-value">${fmtMoney(income)}</div>
      <div class="kpi-sub">稅金 ${fmtMoney(tax)}</div>
    </div>
    <div class="kpi-card kpi-count">
      <div class="kpi-label">稅後實得</div>
      <div class="kpi-value">${fmtMoney(net)}</div>
      <div class="kpi-sub">${totalCount} 筆成交</div>
    </div>
    <div class="kpi-card kpi-bonus">
      <div class="kpi-label">協談獎金合計</div>
      <div class="kpi-value">${fmtMoney(bonusTotal)}</div>
      <div class="kpi-sub">${bonusCount} 筆協談</div>
      ${(()=>{ // 近7天協談趨勢（金額）
        const today = new Date();
        const days = [];
        for(let i=6;i>=0;i--){ const d=new Date(today); d.setDate(today.getDate()-i); days.push(d.toISOString().slice(0,10)); }
        const sums = days.map(ds => salesData.filter(s=>s.saleType==='bonus'&&s.date===ds).reduce((a,s)=>a+s.amount,0));
        const max = Math.max(1,...sums);
        const bars = sums.map(v=>`<div title="${v?fmtMoney(v):'—'}" style="flex:1;height:${Math.max(2,Math.round(v/max*28))}px;background:${v>0?'var(--accent)':'var(--surface2)'};border:1px solid var(--border);border-bottom:0;border-radius:3px 3px 0 0"></div>`).join('');
        return `<div style="display:flex;align-items:flex-end;gap:3px;height:30px;margin-top:8px">${bars}</div>`;
      })()}
    </div>
  </div>`;

  const prodHtml = `
  <div>
    <div class="prod-section-title">快速新增成交</div>
    <div class="prod-grid">
      <div class="prod-card" style="--prod-color:#f97316" onclick="openSaleModal('transfer')">
        <span class="prod-add-icon">＋</span>
        <div class="prod-name">舊單轉讓</div>
        <div class="prod-price" style="color:#f97316">${fmtMoney(TRANSFER_AMOUNT)}</div>
        <div class="prod-desc">固定金額</div>
      </div>
      ${Object.entries(SALES_PRODUCTS).filter(([id])=>canSeeBatchProduct(id)).map(([id,p])=>`
        <div class="prod-card" style="--prod-color:${p.color}" onclick="openSaleModal('${id}')">
          <span class="prod-add-icon">＋</span>
          <div class="prod-name">${p.name}</div>
          <div class="prod-price">${fmtMoney(p.price)}${p.perPerson?'／人':''}</div>
          ${id==='asst_mgr_pkg'?'<div class="prod-desc">79,800 × 6</div>':
            id==='manager_pkg'?'<div class="prod-desc">79,800 × 15</div>':
            id==='consult'?'<div class="prod-desc">79,800 × 3%</div>':''}
        </div>`).join('')}
    </div>
  </div>`;

  const logHtml = `
  <div>
    <div class="prod-section-title">成交記錄</div>
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      <div style="display:grid;grid-template-columns:88px 1fr 110px 100px 100px 90px 32px;gap:8px;padding:6px 12px;font-size:11px;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border)">
        <span>日期</span><span>客戶</span><span>類別</span><span>業績量</span><span>所得</span><span>稅後</span><span></span>
      </div>
      ${sorted.length ? sorted.map(s=>{
        const isTransfer = s.saleType==='transfer';
        const p = isTransfer
          ? {name:'舊單轉讓',color:'#f97316',bg:'rgba(249,115,22,.12)'}
          : (SALES_PRODUCTS[s.product]||{name:s.product,color:'var(--accent)',bg:'var(--surface2)'});
        const rowIncome = CALC.saleIncome(s, myRate);
        const rowNet    = rowIncome * (1 - SALES_TAX);
        const clientNames = (s.clients||[]).map(id=>{ const n=findNode(id); return n?n.name:'—'; }).join('、')||'—';
        return `<div onclick="openSaleEditModal('${s.id}')" style="display:grid;grid-template-columns:88px 1fr 110px 100px 100px 90px 32px;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px;align-items:center;transition:background .1s;cursor:pointer" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''">
          <span>${s.date}</span>
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${clientNames}">${clientNames}</span>
          <span><span class="sale-badge" style="--prod-color:${p.color};--prod-bg:${p.bg}">${p.name}</span></span>
          <span class="sale-amount">${fmtMoney(s.amount)}</span>
          <span style="font-weight:600;color:var(--accent);font-variant-numeric:tabular-nums">${fmtMoney(rowIncome)}</span>
          <span class="sale-net">${fmtMoney(rowNet)}</span>
          <button class="sale-del" onclick="event.stopPropagation();deleteSale('${s.id}')">✕</button>
        </div>`;
      }).join('') : '<div class="sale-empty">本月尚無成交記錄</div>'}
    </div>
  </div>`;

  body.innerHTML = kpiHtml + prodHtml + logHtml;
}

let _editingSaleId = null;
let _saleManualAmount = false;

function onSaleAmountFocus(){
  const el=document.getElementById('sale-amount-display'); if(!el) return;
  const n=parseMoneyText(el.value);
  if(Number.isFinite(n)) el.value=String(Math.round(n));
}
function onSaleAmountBlur(){
  const el=document.getElementById('sale-amount-display'); if(!el) return;
  const n=parseMoneyText(el.value);
  if(Number.isFinite(n)) el.value=fmtMoney(n);
}
function onSaleAmountInput(){
  _saleManualAmount = true;
  updateSalePreviewFromInputs();
}
function getSaleAmountFromInput(){
  const el=document.getElementById('sale-amount-display'); if(!el) return 0;
  const n=parseMoneyText(el.value);
  return Number.isFinite(n) ? Math.max(0, Math.round(n)) : 0;
}
function setSaleAmountToInput(amount){
  const el=document.getElementById('sale-amount-display'); if(!el) return;
  el.value = fmtMoney(amount);
}

function openSaleModal(productId){
  if(!CMD.allowed('sales.open')){ toast('此指令已被停用'); return; }
  _editingSaleId = null;
  _saleManualAmount = false;
  document.getElementById('sale-modal-title-text').textContent='新增成交';
  const isTransfer = productId === 'transfer';
  const today = new Date().toISOString().slice(0,10);
  document.getElementById('sale-date').value = today;
  document.getElementById('sale-notes').value = '';
  document.getElementById('sale-qty').value = '1';
  // 根據職級隱藏批貨選項
  const productSel = document.getElementById('sale-product');
  productSel.querySelectorAll('option[value="asst_mgr_pkg"], option[value="manager_pkg"]')
    .forEach(opt => { opt.style.display = canSeeBatchProduct(opt.value) ? '' : 'none'; });
  // Set sale type
  const typeRadios = document.querySelectorAll('input[name="sale-type"]');
  typeRadios.forEach(r=>{ r.checked = isTransfer ? r.value==='transfer' : r.value==='new'; });
  onSaleTypeChange();
  if(!isTransfer && productId && canSeeBatchProduct(productId))
    document.getElementById('sale-product').value = productId;
  // Render pax tags
  const contactNodes = nodes.filter(n=>n.status!==null&&n.name);
  document.getElementById('sale-pax').innerHTML = contactNodes.length
    ? contactNodes.map(n=>`<div class="ev-pax" data-nid="${n.id}" onclick="this.classList.toggle('selected')">
        <span class="sdot ${n.status||'gray'}"></span>${escHtml(n.name)}</div>`).join('')
    : '<span style="color:var(--text-muted);font-size:12px">尚無人脈節點</span>';
  onSaleProductChange();
  document.getElementById('sale-modal').classList.add('open');
}
function closeSaleModal(){ document.getElementById('sale-modal').classList.remove('open'); }

function openSaleEditModal(id){
  if(!CMD.allowed('sales.open')){ toast('此指令已被停用'); return; }
  const s = salesData.find(x=>x.id===id);
  if(!s){ toast('找不到此筆成交'); return; }
  _editingSaleId = id;
  _saleManualAmount = true;
  document.getElementById('sale-modal-title-text').textContent='編輯成交';

  document.getElementById('sale-date').value = s.date || new Date().toISOString().slice(0,10);
  document.getElementById('sale-notes').value = s.notes || '';
  document.getElementById('sale-qty').value = String(s.qty || 1);

  const isTransfer = s.saleType === 'transfer';
  const typeRadios = document.querySelectorAll('input[name="sale-type"]');
  typeRadios.forEach(r=>{ r.checked = isTransfer ? r.value==='transfer' : r.value==='new'; });

  // 根據職級隱藏批貨選項
  const productSel = document.getElementById('sale-product');
  productSel.querySelectorAll('option[value="asst_mgr_pkg"], option[value="manager_pkg"]')
    .forEach(opt => { opt.style.display = canSeeBatchProduct(opt.value) ? '' : 'none'; });

  if(!isTransfer){
    document.getElementById('sale-product').value = s.product || 'student';
    document.querySelectorAll('input[name="sale-batchby"]').forEach(r=>{ r.checked = (r.value === (s.batchby||'self')); });
    document.querySelectorAll('input[name="sale-samerank"]').forEach(r=>{ r.checked = (r.value === (s.samerank||'self')); });
  }

  onSaleTypeChange();

  // Render pax tags (with selection)
  const contactNodes = nodes.filter(n=>n.status!==null&&n.name);
  const selected = new Set((s.clients||[]).map(String));
  document.getElementById('sale-pax').innerHTML = contactNodes.length
    ? contactNodes.map(n=>`<div class="ev-pax${selected.has(String(n.id))?' selected':''}" data-nid="${n.id}" onclick="this.classList.toggle('selected')">
        <span class="sdot ${n.status||'gray'}"></span>${escHtml(n.name)}</div>`).join('')
    : '<span style="color:var(--text-muted);font-size:12px">尚無人脈節點</span>';

  setSaleAmountToInput(s.amount || 0);
  updateSalePreviewFromInputs();
  document.getElementById('sale-modal').classList.add('open');
}

function onSaleTypeChange(){
  const isTransfer = document.querySelector('input[name="sale-type"]:checked')?.value === 'transfer';
  document.getElementById('sale-product-group').style.display = isTransfer ? 'none' : '';
  document.getElementById('sale-qty-group').style.display = 'none';
  if(isTransfer){
    if(!_saleManualAmount) setSaleAmountToInput(TRANSFER_AMOUNT);
    const badge=document.getElementById('sale-modal-product-badge');
    badge.textContent='舊單轉讓';
    badge.style.cssText='background:rgba(249,115,22,.15);color:#f97316';
    updateSalePreviewFromInputs();
  } else {
    onSaleProductChange();
  }
}

function onSaleProductChange(){
  const isTransfer = document.querySelector('input[name="sale-type"]:checked')?.value === 'transfer';
  if(isTransfer){ onSaleTypeChange(); return; }
  const pid = document.getElementById('sale-product').value;
  const p = SALES_PRODUCTS[pid];
  if(!p) return;
  const qty = p.perPerson ? (parseInt(document.getElementById('sale-qty').value)||1) : 1;
  document.getElementById('sale-qty-group').style.display = p.perPerson ? '' : 'none';

  const isBatch = (pid === 'asst_mgr_pkg' || pid === 'manager_pkg');
  // 批貨對象 toggle
  document.getElementById('sale-batchby-group').style.display = isBatch ? '' : 'none';
  // 傘下同階業績 toggle（非批貨才顯示）
  document.getElementById('sale-samerank-group').style.display = (!isBatch && !p.perPerson && !p.noSamerank) ? '' : 'none';

  const autoAmount = p.price * qty;
  if(!_saleManualAmount) setSaleAmountToInput(autoAmount);
  updateSalePreviewFromInputs();
  const badge = document.getElementById('sale-modal-product-badge');
  badge.textContent = p.name;
  badge.style.cssText = `background:${p.bg};color:${p.color}`;
}

function updateSalePreviewFromInputs(){
  const isTransfer = document.querySelector('input[name="sale-type"]:checked')?.value === 'transfer';
  const amount = getSaleAmountFromInput();
  const myRate = getMyRate();
  let myIncome = 0;
  let incomeLabel = fmtMoney(0);

  if(isTransfer){
    myIncome = amount;
    incomeLabel = fmtMoney(myIncome);
  } else {
    const pid = document.getElementById('sale-product').value;
    const p = SALES_PRODUCTS[pid];
    if(!p) return;
    if(pid === 'consult'){ myIncome = amount; incomeLabel = `${fmtMoney(myIncome)} (協談獎金)`; document.getElementById('sale-income-preview').textContent = incomeLabel; document.getElementById('sale-tax-preview').textContent = fmtMoney(myIncome * SALES_TAX); document.getElementById('sale-net-preview').textContent = fmtMoney(myIncome * (1-SALES_TAX)); return; }
    const isBatch = (pid === 'asst_mgr_pkg' || pid === 'manager_pkg');
    if(isBatch){
      const batchby = document.querySelector('input[name="sale-batchby"]:checked')?.value || 'self';
      if(batchby === 'student'){
        const anchor = BATCH_ANCHORS[pid] || 0;
        const diff = Math.max(0, myRate - anchor);
        myIncome = amount * diff;
        const batchLabel = pid==='asst_mgr_pkg'
          ? `升至襄理 anchor 20%`
          : `升至經理 anchor 15%`;
        incomeLabel = `${fmtMoney(myIncome)} (${(myRate*100).toFixed(0)}%−${(anchor*100).toFixed(0)}%=${(diff*100).toFixed(0)}% · ${batchLabel})`;
      } else {
        myIncome = amount * myRate;
        incomeLabel = fmtMoney(myIncome);
      }
    } else {
      const samerank = document.querySelector('input[name="sale-samerank"]:checked')?.value || 'self';
      if(samerank === 'samerank'){
        myIncome = amount * 0.01;
        incomeLabel = `${fmtMoney(myIncome)} (傘下同階 1%)`;
      } else {
        myIncome = amount * myRate;
        incomeLabel = fmtMoney(myIncome);
      }
    }
  }

  document.getElementById('sale-income-preview').textContent = incomeLabel;
  document.getElementById('sale-tax-preview').textContent = fmtMoney(myIncome * SALES_TAX);
  document.getElementById('sale-net-preview').textContent = fmtMoney(myIncome * (1-SALES_TAX));
}

function saveSale(){
  if(!CMD.allowed('sales.save')){ toast('此指令已被停用'); return; }
  const isTransfer = document.querySelector('input[name="sale-type"]:checked')?.value === 'transfer';
  const pid = isTransfer ? 'transfer' : document.getElementById('sale-product').value;
  const p = SALES_PRODUCTS[pid];
  const qty = (!isTransfer && p?.perPerson) ? (parseInt(document.getElementById('sale-qty').value)||1) : 1;
  const amount = getSaleAmountFromInput();
  const clients = [...document.querySelectorAll('#sale-pax .ev-pax.selected')].map(el=>el.dataset.nid);
  const date = document.getElementById('sale-date').value;
  if(!date){ toast('請選擇日期'); return; }
  if(!amount){ toast('請填寫業績金額'); return; }
  const isBatch = (pid === 'asst_mgr_pkg' || pid === 'manager_pkg');
  const batchby = isBatch ? (document.querySelector('input[name="sale-batchby"]:checked')?.value||'self') : 'self';
  const samerank = (!isBatch && !isTransfer && !p?.noSamerank) ? (document.querySelector('input[name="sale-samerank"]:checked')?.value||'self') : 'self';
  const saleType = isTransfer ? 'transfer' : (pid==='consult' ? 'bonus' : 'new');
  const sale = {
    id: _editingSaleId || uid(), saleType,
    product: pid, amount, qty, clients,
    batchby, samerank,
    date, notes: document.getElementById('sale-notes').value,
  };
  if(_editingSaleId){
    const idx = salesData.findIndex(x=>x.id===_editingSaleId);
    if(idx>=0) salesData[idx]=sale;
    else salesData.push(sale);
  } else {
    salesData.push(sale);
  }
  saveSalesData();
  closeSaleModal();
  renderSales();
  toast(_editingSaleId ? '成交已更新' : (isTransfer ? '舊單轉讓已記錄' : '新業績成交 🎉'));
}

function deleteSale(id){
  if(!CMD.allowed('sales.delete')){ toast('此指令已被停用'); return; }
  if(!confirm('確定刪除此筆成交？')) return;
  salesData = salesData.filter(s=>s.id!==id);
  saveSalesData();
  renderSales();
  toast('已刪除');
}

/* ══════════════════════════════════════
   CRM VIEW MODES
══════════════════════════════════════ */
let crmView='tree'; // 'tree'|'region'|'status'|'contact'
let crmStatusFilter=null; // null=全部, 'green'|'yellow'|'red'|'gray'
let crmSortAsc=true;

function setCrmView(v){
  crmView=v;
  document.querySelectorAll('.crm-view-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('vbtn-'+v)?.classList.add('active');
  const sortBtn=document.getElementById('crm-sort-dir-btn');
  const canvas=document.getElementById('canvas-container');
  const listCont=document.getElementById('crm-list-container');
  const hint=document.getElementById('shortcuts-hint');
  if(v==='tree'){
    canvas.style.display='';
    listCont.style.display='none';
    sortBtn.style.display='none';
    if(hint) hint.style.display='';
    setTimeout(()=>{drawEdges();},50);
  } else {
    canvas.style.display='none';
    listCont.style.display='flex';
    listCont.style.flexDirection='column';
    sortBtn.style.display='';
    sortBtn.textContent=(crmSortAsc?'↑ 升冪':'↓ 降冪');
    if(hint) hint.style.display='none';
    renderCrmListView();
  }
}

function toggleCrmSortDir(){
  crmSortAsc=!crmSortAsc;
  document.getElementById('crm-sort-dir-btn').textContent=(crmSortAsc?'↑ 升冪':'↓ 降冪');
  renderCrmListView();
}

function renderCrmListView(){
  const el=document.getElementById('crm-list-view');
  if(!el)return;
  const nonRoot=nodes.filter(n=>n.parentId!==null||n.status!==null);
  const STATUS_ORDER_LIST=['green','yellow','red','gray'];
  const STATUS_LABELS_LIST={green:'高意願',yellow:'觀察中',red:'冷淡',gray:'無效'};

  let groups=[];
  if(crmView==='region'){
    const allRegions=[...new Set(nonRoot.flatMap(n=>n.info.regions&&n.info.regions.length?n.info.regions:['未設定']))];
    allRegions.sort((a,b)=>crmSortAsc?a.localeCompare(b,'zh-TW'):b.localeCompare(a,'zh-TW'));
    groups=allRegions.map(r=>({
      label:r,
      items:nonRoot.filter(n=>(n.info.regions&&n.info.regions.includes(r))||((!n.info.regions||!n.info.regions.length)&&r==='未設定'))
    }));
  } else if(crmView==='status'){
    const order=crmSortAsc?STATUS_ORDER_LIST:[...STATUS_ORDER_LIST].reverse();
    const filteredOrder=crmStatusFilter?order.filter(s=>s===crmStatusFilter):order;
    groups=filteredOrder.map(s=>({
      label:STATUS_LABELS_LIST[s]||s,
      items:nonRoot.filter(n=>n.status===s)
    }));
  } else if(crmView==='contact'){
    const sorted=[...nonRoot].sort((a,b)=>{
      const da=a.info.lastContact||'';
      const db=b.info.lastContact||'';
      return crmSortAsc?da.localeCompare(db):db.localeCompare(da);
    });
    groups=[{label:'全部（依最近聯繫排序）',items:sorted}];
  }

  const ROLE_MAP={潛在客戶:'role-prospect',轉介紹中心:'role-referral',學員:'role-student',從業人員:'role-agent'};

  const STATUS_COLORS={green:'var(--green)',yellow:'var(--yellow)',red:'var(--red)',gray:'var(--gray)'};
  el.innerHTML=groups.filter(g=>g.items.length).map(g=>`
    <div class="crm-list-group-header">${g.label} (${g.items.length})</div>
    ${g.items.map(n=>`
      <div class="crm-list-row" onclick="switchPage('crm');setTimeout(()=>openPanel('${n.id}'),80)">
        <div class="crm-list-avatar" style="background:${STATUS_COLORS[n.status]||'var(--accent)'}">${(n.name||'?')[0]}</div>
        <div>
          <div class="crm-list-name">${escHtml(n.name)}</div>
          <div class="crm-list-meta">${escHtml(n.info.company||'')}${n.info.lastContact?' · '+n.info.lastContact:''}</div>
        </div>
        <div class="crm-list-tags">
          ${n.info.role?`<span class="node-role-pill ${ROLE_MAP[n.info.role]||''}">${n.info.role}</span>`:''}
          ${(n.info.regions||[]).map(r=>`<span class="node-region-tag">${r}</span>`).join('')}
        </div>
      </div>`).join('')}
  `).join('');
}

/* ══════════════════════════════════════
   DAILY REPORT PAGE
══════════════════════════════════════ */
let dailyReports=JSON.parse(localStorage.getItem(STORE.K.dailyReports)||'{}');
let monthlyGoals=JSON.parse(localStorage.getItem(STORE.K.monthlyGoals)||'{}');
let monthlySalesTargets=JSON.parse(localStorage.getItem(STORE.K.monthlySalesTargets)||'{}');

function saveDailyReports(){ STORE.saveDailyReports(); }
function saveMonthlyGoals(){ STORE.saveMonthlyGoals(); }
function saveMonthlySalesTargets(){ STORE.saveMonthlySalesTargets(); }

function saveMonthSalesTarget(){
  const mkey=getMonthKey();
  const el=document.querySelector('[data-mst="mg-sales"]');
  if(!el)return;
  monthlySalesTargets[mkey]=parseInt(el.value.replace(/[^\d]/g,''))||0;
  saveMonthlySalesTargets();
  // 不在輸入時重建 DOM，只更新業績進度條
  const sp=CALC.salesProgress(salesData,STORE.getMyRate(),mkey,monthlySalesTargets[mkey]||0);
  const bar=document.querySelector('[data-mst="mg-sales"]')?.closest('.daily-kpi-card')?.querySelector('[data-progress-bar]');
  if(bar){bar.style.width=sp.pct+'%';}
}

function getMonthKey(dateStr){
  const d=dateStr||getDailyDateStr();
  return d.slice(0,7); // "2026-03"
}

// calcMonthActuals removed — use CALC.monthActuals(dailyReports, monthKey)

function saveMonthlyGoalInputs(){
  const mkey=getMonthKey();
  const goals=monthlyGoals[mkey]||(monthlyGoals[mkey]={});
  ['mg-invite','mg-calls','mg-forms','mg-followup','mg-close','mg-consult'].forEach(k=>{
    const el=document.querySelector(`[data-mg="${k}"]`);
    if(el)goals[k]=parseInt(el.value)||0;
  });
  saveMonthlyGoals();
  // 只更新進度條數值，不重建 DOM（避免焦點跳掉）
  updateMonthlyProgressBars();
}
function updateMonthlyProgressBars(){
  const mkey=getMonthKey();
  const goals=monthlyGoals[mkey]||{};
  const actuals=CALC.monthActuals(dailyReports,mkey);
  const items=CALC.progressItems(actuals,goals);
  items.forEach(it=>{
    const card=document.querySelector(`[data-mg="${it.goalK}"]`)?.closest('.daily-kpi-card');
    if(!card)return;
    const bar=card.querySelector('[data-progress-bar]');
    const label=card.querySelector('[data-progress-label]');
    if(bar)bar.style.width=it.pct+'%';
    if(label)label.textContent=`實績 ${it.actual} · ${it.pct}%`;
    card.classList.toggle('exceeded',it.full);
  });
}

function renderMonthlyProgress(){
  const mkey  = getMonthKey();
  const goals = monthlyGoals[mkey] || {};
  // ── CALC handles all arithmetic ──
  const actuals = CALC.monthActuals(dailyReports, mkey);
  const items   = CALC.progressItems(actuals, goals);
  const sp      = CALC.salesProgress(salesData, STORE.getMyRate(), mkey, monthlySalesTargets[mkey]||0);

  const container = document.getElementById('monthly-goal-body');
  if(!container) return;
  container.innerHTML = `
    <div class="daily-kpi-card${sp.full?' exceeded':''}" style="grid-column:1/-1;display:flex;align-items:center;gap:12px;margin-bottom:10px;padding:10px 14px">
      <div style="font-size:13px;font-weight:600;white-space:nowrap">💰 本月業績目標</div>
      <div style="display:flex;align-items:center;gap:6px;flex:1">
        <span style="font-size:12px;color:var(--text-muted)">NT$</span>
        <input data-mst="mg-sales" data-nodraft="true" type="number" min="0" value="${monthlySalesTargets[mkey]||0}"
          style="width:110px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:3px 8px;font-size:14px;font-weight:700"
          oninput="saveMonthSalesTarget()"
          onblur="renderMonthlyProgress()">
        <div style="flex:1;height:6px;background:var(--surface2);border-radius:3px;overflow:hidden;border:1px solid var(--border)">
          <div data-progress-bar style="height:100%;width:${sp.pct}%;background:${sp.full?'var(--green)':'var(--accent)'};border-radius:3px;transition:width .3s"></div>
        </div>
        <span style="font-size:12px;color:var(--text-muted);white-space:nowrap">實績 ${fmtMoney(sp.income)} · ${sp.pct}%</span>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px">
      ${items.map(it=>`
        <div class="daily-kpi-card${it.full?' exceeded':''}">
          <div class="daily-kpi-label">${it.label}目標</div>
          <div style="display:flex;align-items:center;gap:6px;margin:4px 0">
            <input data-mg="${it.goalK}" data-nodraft="true" type="number" min="0" value="${it.goal}"
              style="width:60px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:3px 6px;font-size:14px;font-weight:700;text-align:center"
              oninput="saveMonthlyGoalInputs()"
              onblur="renderMonthlyProgress()">
          </div>
          <div style="height:5px;background:var(--surface2);border-radius:3px;overflow:hidden;border:1px solid var(--border);margin-bottom:3px">
            <div data-progress-bar style="height:100%;width:${it.pct}%;background:${it.full?'var(--green)':'var(--accent)'};border-radius:3px;transition:width .3s"></div>
          </div>
          <div class="daily-kpi-target" data-progress-label>實績 ${it.actual} · ${it.pct}%</div>
        </div>`).join('')}
    </div>`;
}

function getDailyDateStr(){
  const el=document.getElementById('daily-date-input');
  return el?el.value:new Date().toISOString().slice(0,10);
}

function dailyToday(){
  const el=document.getElementById('daily-date-input');
  if(el){el.value=new Date().toISOString().slice(0,10);renderDailyPage();}
}
function dailyPrev(){
  const el=document.getElementById('daily-date-input');
  if(!el)return;
  const d=new Date(el.value||new Date());d.setDate(d.getDate()-1);
  el.value=d.toISOString().slice(0,10);renderDailyPage();
}
function dailyNext(){
  const el=document.getElementById('daily-date-input');
  if(!el)return;
  const d=new Date(el.value||new Date());d.setDate(d.getDate()+1);
  el.value=d.toISOString().slice(0,10);renderDailyPage();
}

function saveDailyReport(){
  const dateStr=getDailyDateStr();
  const body=document.getElementById('daily-body');
  if(!body)return;
  const report=dailyReports[dateStr]||{};
  // Goals
  ['goal-invite','goal-calls','goal-forms','goal-followup','goal-close','goal-consult'].forEach(k=>{
    const el=body.querySelector(`[data-daily="${k}"]`);
    if(el)report[k]=parseInt(el.value)||0;
  });
  // Activity
  ['act-invite','act-calls','act-forms','act-followup','act-close','act-consult'].forEach(k=>{
    const el=body.querySelector(`[data-daily="${k}"]`);
    if(el)report[k]=parseInt(el.value)||0;
  });
  // Follow-up checked
  const fuChecked=[...body.querySelectorAll('.daily-fu-check.checked')].map(el=>el.dataset.nid);
  report.fuChecked=fuChecked;
  // Notes
  const notesEl=body.querySelector('[data-daily="notes"]');
  if(notesEl)report.notes=notesEl.value;
  dailyReports[dateStr]=report;
  saveDailyReports();
  renderDailyProgress();
  renderMonthlyProgress();
  toast('日報已儲存');
}

function renderDailyProgress(){
  const dateStr=getDailyDateStr();
  const report=dailyReports[dateStr]||{};
  const kpiItems=[
    {label:'邀約數',actKey:'act-invite',  goalKey:'goal-invite'},
    {label:'電話數',actKey:'act-calls',   goalKey:'goal-calls'},
    {label:'問卷數',actKey:'act-forms',   goalKey:'goal-forms'},
    {label:'跟進數',actKey:'act-followup',goalKey:'goal-followup'},
    {label:'成交數',actKey:'act-close',   goalKey:'goal-close'},
    {label:'協談數',actKey:'act-consult', goalKey:'goal-consult'},
  ];
  const kpiGrid=document.querySelector('.daily-kpi-grid');
  if(!kpiGrid)return;
  kpiGrid.innerHTML=kpiItems.map(item=>{
    const goalEl=document.querySelector(`[data-daily="${item.goalKey}"]`);
    const goal=goalEl?parseInt(goalEl.value)||0:(report[item.goalKey]||0);
    const act=report[item.actKey]||0;
    const pct=goal?Math.min(100,Math.round(act/goal*100)):0;
    const cls=act>=goal&&goal>0?'exceeded':'';
    return`<div class="daily-kpi-card ${cls}">
      <div class="daily-kpi-label">${item.label}</div>
      <div class="daily-kpi-val">${act}</div>
      <div class="daily-kpi-target">目標 ${goal} · ${pct}%</div>
    </div>`;
  }).join('');
}

function renderDailyPage(){
  const el=document.getElementById('daily-date-input');
  if(el&&!el.value)el.value=new Date().toISOString().slice(0,10);
  const dateStr=getDailyDateStr();
  const report=dailyReports[dateStr]||{};
  const body=document.getElementById('daily-body');
  if(!body)return;

  // Follow-up nodes: all non-root CRM nodes
  const fuNodes=nodes.filter(n=>n.status!==null&&n.name&&n.name!=='新聯繫人');
  const fuChecked=report.fuChecked||[];

  const kpiItems=[
    {label:'邀約數',  actKey:'act-invite',  goalKey:'goal-invite'},
    {label:'電話數',  actKey:'act-calls',   goalKey:'goal-calls'},
    {label:'問卷數',  actKey:'act-forms',   goalKey:'goal-forms'},
    {label:'跟進數',  actKey:'act-followup',goalKey:'goal-followup'},
    {label:'成交數',  actKey:'act-close',   goalKey:'goal-close'},
    {label:'協談數',  actKey:'act-consult', goalKey:'goal-consult'},
  ];

  const mkey=getMonthKey(dateStr);
  const mLabel=mkey.replace('-','年')+'月';

  body.innerHTML=`
    <!-- Monthly Goal -->
    <div class="daily-section">
      <div class="daily-section-header">
        <span>🗓 ${mLabel}目標</span>
        <span style="font-size:11px;color:var(--text-muted)">設定後自動儲存</span>
      </div>
      <div class="daily-section-body" id="monthly-goal-body"></div>
    </div>

    <!-- KPI Overview -->
    <div class="daily-section">
      <div class="daily-section-header">
        <span>📊 今日目標達成</span>
      </div>
      <div class="daily-section-body">
        <div class="daily-kpi-grid">
          ${kpiItems.map(item=>{
            const goal=report[item.goalKey]||0;
            const act=report[item.actKey]||0;
            const pct=goal?Math.min(100,Math.round(act/goal*100)):0;
            const cls=act>=goal&&goal>0?'exceeded':act>0?'':'';
            return`<div class="daily-kpi-card ${cls}">
              <div class="daily-kpi-label">${item.label}</div>
              <div class="daily-kpi-val">${act}</div>
              <div class="daily-kpi-target">目標 ${goal} · ${pct}%</div>
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>

    <!-- Daily Goals -->
    <div class="daily-section">
      <div class="daily-section-header"><span>🎯 今日目標設定</span></div>
      <div class="daily-section-body">
        <div class="daily-activity-grid">
          ${[{k:'goal-invite',label:'邀約目標'},{k:'goal-calls',label:'電話目標'},{k:'goal-forms',label:'問卷目標'},{k:'goal-followup',label:'跟進目標'},{k:'goal-close',label:'成交目標'},{k:'goal-consult',label:'協談目標'}].map(item=>`
            <div class="daily-act-item">
              <div class="daily-act-label">${item.label}</div>
              <input class="daily-act-input" data-nodraft="true" type="number" min="0" data-daily="${item.k}" value="${report[item.k]||0}" oninput="renderDailyProgress(this)">
            </div>`).join('')}
        </div>
      </div>
    </div>

    <!-- Activity Log -->
    <div class="daily-section">
      <div class="daily-section-header"><span>📞 今日實績記錄</span></div>
      <div class="daily-section-body">
        <div class="daily-activity-grid">
          ${[{k:'act-invite',label:'邀約數'},{k:'act-calls',label:'電話數'},{k:'act-forms',label:'問卷數'},{k:'act-followup',label:'跟進數'},{k:'act-close',label:'成交數'},{k:'act-consult',label:'協談數'}].map(item=>`
            <div class="daily-act-item">
              <div class="daily-act-label">${item.label}</div>
              <input class="daily-act-input" type="number" min="0" data-daily="${item.k}" value="${report[item.k]||0}">
            </div>`).join('')}
        </div>
      </div>
    </div>

    <!-- Follow-up Targets -->
    <div class="daily-section">
      <div class="daily-section-header">
        <span>👥 今日跟進對象</span>
        <span style="font-size:11px;color:var(--text-muted)">${fuChecked.length}/${fuNodes.length} 已跟進</span>
      </div>
      <div class="daily-section-body">
        <div class="daily-fu-search">
          <input type="text" placeholder="搜尋人脈…" id="daily-fu-search-input" oninput="filterDailyFu(this.value)">
        </div>
        <div class="daily-fu-list" id="daily-fu-list">
          ${fuNodes.length?fuNodes.map(n=>{
            const done=fuChecked.includes(n.id);
            const regions=(n.info.regions||[]).join('、');
            return`<div class="daily-fu-item${done?' done':''}" data-nid="${n.id}">
              <div class="daily-fu-check${done?' checked':''}" data-nid="${n.id}" onclick="toggleDailyFu(event,'${n.id}')">
                ${done?'✓':''}
              </div>
              <span class="sdot ${n.status||'gray'}" style="width:8px;height:8px;border-radius:50%;flex-shrink:0"></span>
              <span class="daily-fu-name" onclick="switchPage('crm');setTimeout(()=>openPanel('${n.id}'),80)">${escHtml(n.name)}</span>
              ${n.info.role?`<span class="daily-fu-role">${n.info.role}</span>`:''}
              ${regions?`<span class="daily-fu-region">${regions}</span>`:''}
              <span style="font-size:11px;color:var(--text-muted)">${n.info.lastContact||''}</span>
            </div>`;
          }).join(''):'<span style="color:var(--text-muted);font-size:13px">尚無人脈節點</span>'}
        </div>
      </div>
    </div>

    <!-- Notes -->
    <div class="daily-section">
      <div class="daily-section-header"><span>📝 今日反思 / 備注</span></div>
      <div class="daily-section-body">
        <textarea class="daily-notes-input" data-daily="notes" placeholder="今天做了什麼？有什麼收穫？明天重點是什麼？">${escHtml(report.notes||'')}</textarea>
      </div>
    </div>
  `;
  // Render monthly goals after body is set
  renderMonthlyProgress();
}

function toggleDailyFu(e,nid){
  e.stopPropagation();
  const dateStr=getDailyDateStr();
  const report=dailyReports[dateStr]||(dailyReports[dateStr]={});
  if(!report.fuChecked)report.fuChecked=[];
  const idx=report.fuChecked.indexOf(nid);
  if(idx>=0)report.fuChecked.splice(idx,1);
  else report.fuChecked.push(nid);
  saveDailyReports();
  // Update DOM
  const item=document.querySelector(`.daily-fu-item[data-nid="${nid}"]`);
  const check=document.querySelector(`.daily-fu-check[data-nid="${nid}"]`);
  if(item&&check){
    const done=report.fuChecked.includes(nid);
    item.classList.toggle('done',done);
    check.classList.toggle('checked',done);
    check.textContent=done?'✓':'';
  }
  // Update count
  const total=document.querySelectorAll('.daily-fu-item').length;
  const doneCount=report.fuChecked.length;
  const header=document.querySelector('.daily-section-header span[style]');
  if(header)header.textContent=`${doneCount}/${total} 已跟進`;
}

function filterDailyFu(q){
  const ql=q.toLowerCase();
  document.querySelectorAll('.daily-fu-item').forEach(el=>{
    const name=el.querySelector('.daily-fu-name')?.textContent||'';
    el.style.display=(!q||name.toLowerCase().includes(ql))?'':'none';
  });
}

/* ══════════════════════════════════════
   DOCS PAGE
══════════════════════════════════════ */
let docsData=JSON.parse(localStorage.getItem(STORE.K.docs)||'[]');
const DOC_ICONS={poster:'🖼',form:'📋',link:'🔗',file:'📄'};

function saveDocs(){ STORE.saveDocs(); }

function renderDocs(){
  const grid=document.getElementById('docs-grid');
  if(!grid)return;
  if(!docsData.length){
    grid.innerHTML='<div style="color:var(--text-muted);font-size:13px;grid-column:1/-1;text-align:center;padding:40px 0">尚無文件，點擊「新增文件」開始</div>';
    return;
  }
  grid.innerHTML=docsData.map(d=>`
    <div class="doc-card">
      ${d.type==='poster'&&d.imgData
        ?`<img class="doc-card-img" src="${d.imgData}" alt="${escHtml(d.name)}">`
        :`<div class="doc-card-img">${DOC_ICONS[d.type]||'📄'}</div>`}
      <div class="doc-card-body">
        <div class="doc-card-name">${escHtml(d.name)}</div>
        <div class="doc-card-type">${DOC_ICONS[d.type]||''} ${{poster:'海報圖片',form:'問卷連結',link:'其他連結',file:'文件檔案'}[d.type]||d.type}</div>
        ${d.url?`<div class="doc-card-link" onclick="window.open('${escHtml(d.url)}','_blank')">${escHtml(d.url)}</div>`:''}
      </div>
      <button class="doc-card-del" onclick="deleteDoc('${d.id}')">✕</button>
    </div>`).join('');
}

let _docFileData=null; // base64 of current file in modal

/* ── Modal open/close ── */
function openDocModal(prefill){
  if(!CMD.allowed('doc.open')){ toast('此指令已被停用'); return; }
  _docFileData=null;
  document.getElementById('doc-name').value=prefill?.name||'';
  document.getElementById('doc-url').value=prefill?.url||'';
  document.getElementById('doc-file-input').value='';
  document.getElementById('doc-img-preview').style.display='none';
  document.getElementById('doc-file-label').textContent='點擊選擇 或 拖曳檔案至此';
  document.getElementById('doc-file-icon').textContent='⬆';
  if(prefill?.type)document.getElementById('doc-type').value=prefill.type;
  onDocTypeChange();
  document.getElementById('doc-add-modal').classList.add('open');
}
function closeDocModal(){document.getElementById('doc-add-modal').classList.remove('open');}

function onDocTypeChange(){
  const t=document.getElementById('doc-type').value;
  const isLink=t==='form'||t==='link';
  const isFile=t==='poster'||t==='file';
  document.getElementById('doc-url-group').style.display=isLink?'':'none';
  document.getElementById('doc-file-group').style.display=isFile?'':'none';
  // accept filter
  const inp=document.getElementById('doc-file-input');
  inp.accept=t==='poster'?'image/*':'*/*';
}

/* ── Modal file dropzone ── */
function modalFileOver(e){
  e.preventDefault();e.stopPropagation();
  document.getElementById('doc-file-dropzone').classList.add('drag-over');
}
function modalFileLeave(e){
  document.getElementById('doc-file-dropzone').classList.remove('drag-over');
}
function modalFileDrop(e){
  e.preventDefault();e.stopPropagation();
  document.getElementById('doc-file-dropzone').classList.remove('drag-over');
  const f=e.dataTransfer.files[0];
  if(f)_loadDocFile(f);
}
function modalFileChange(input){
  const f=input.files[0];if(f)_loadDocFile(f);
}
function _loadDocFile(f){
  const isImg=/^image\//.test(f.type);
  // auto-set name if empty
  const nameEl=document.getElementById('doc-name');
  if(!nameEl.value)nameEl.value=f.name.replace(/\.[^.]+$/,'');
  // auto-switch type
  const typeEl=document.getElementById('doc-type');
  if(isImg&&typeEl.value!=='poster')typeEl.value='poster';
  else if(!isImg&&typeEl.value==='poster')typeEl.value='file';
  onDocTypeChange();

  const reader=new FileReader();
  reader.onload=ev=>{
    _docFileData=ev.target.result;
    document.getElementById('doc-file-label').textContent=f.name;
    document.getElementById('doc-file-icon').textContent=isImg?'🖼':'📄';
    if(isImg){
      const prev=document.getElementById('doc-img-preview');
      prev.src=_docFileData;prev.style.display='block';
    }
  };
  reader.readAsDataURL(f);
}

/* ── Docs page full-page drop zone ── */
function docsOnDragOver(e){
  e.preventDefault();e.stopPropagation();
  document.getElementById('docs-dropzone').classList.add('drag-over');
  document.getElementById('docs-dropzone-hint').classList.add('active');
}
function docsOnDragLeave(e){
  // only fire if leaving the dropzone itself (not a child)
  if(e.currentTarget.contains(e.relatedTarget))return;
  document.getElementById('docs-dropzone').classList.remove('drag-over');
  document.getElementById('docs-dropzone-hint').classList.remove('active');
}
function docsOnDrop(e){
  e.preventDefault();e.stopPropagation();
  document.getElementById('docs-dropzone').classList.remove('drag-over');
  document.getElementById('docs-dropzone-hint').classList.remove('active');
  const files=[...e.dataTransfer.files];
  if(!files.length)return;
  if(files.length===1){
    // single file → open modal pre-filled
    const f=files[0];
    const isImg=/^image\//.test(f.type);
    openDocModal({name:f.name.replace(/\.[^.]+$/,''),type:isImg?'poster':'file'});
    setTimeout(()=>_loadDocFile(f),50);
  } else {
    // multiple files → auto-create all immediately
    let count=0;
    files.forEach(f=>{
      const isImg=/^image\//.test(f.type);
      const reader=new FileReader();
      reader.onload=ev=>{
        docsData.push({id:uid(),name:f.name.replace(/\.[^.]+$/,''),
          type:isImg?'poster':'file',url:'',
          imgData:isImg?ev.target.result:null,
          fileData:!isImg?ev.target.result:null,
          fileName:f.name,fileSize:f.size});
        count++;
        if(count===files.length){saveDocs();renderDocs();toast(`已新增 ${count} 個文件`);}
      };
      reader.readAsDataURL(f);
    });
  }
}

function saveDoc(){
  if(!CMD.allowed('doc.save')){ toast('此指令已被停用'); return; }
  const name=document.getElementById('doc-name').value.trim();
  if(!name){toast('請輸入文件名稱');return;}
  const type=document.getElementById('doc-type').value;
  const url=document.getElementById('doc-url').value.trim();
  const isImg=type==='poster';
  const d={id:uid(),name,type,url,
    imgData:isImg?_docFileData:null,
    fileData:(!isImg&&type==='file')?_docFileData:null,
    fileName:document.getElementById('doc-file-label').textContent};
  docsData.push(d);
  saveDocs();closeDocModal();renderDocs();
  toast('文件已新增');
}

function deleteDoc(id){
  if(!CMD.allowed('doc.delete')){ toast('此指令已被停用'); return; }
  if(!confirm('確定刪除此文件？'))return;
  docsData=docsData.filter(d=>d.id!==id);
  saveDocs();renderDocs();toast('已刪除');
}

/* ── Obsidian ── */
function saveObsidianPath(){
  const p=document.getElementById('obsidian-path').value.trim();
  localStorage.setItem(STORE.K.obsidianPath, p);
  const s=document.getElementById('obsidian-status');
  if(s)s.textContent=p?`已儲存路徑：${p}`:'';
}
function openObsidianVault(){
  const p=localStorage.getItem(STORE.K.obsidianPath)||'';
  if(!p){toast('請先設定 Obsidian Vault 路徑');return;}
  window.open('obsidian://open?path='+encodeURIComponent(p),'_blank');
}

/* ── Settings page ── */
function renderSettingsPage(){
  // Load obsidian path
  const obsEl=document.getElementById('obsidian-path');
  if(obsEl) obsEl.value=localStorage.getItem(STORE.K.obsidianPath)||'';
  renderAiSettingsCard();
  // Theme grid
  const curTheme=document.documentElement.getAttribute('data-theme')||'dark';
  const tg=document.getElementById('settings-theme-grid');
  if(tg) tg.innerHTML=THEMES.map(t=>`
    <div class="theme-tile${curTheme===t.id?' active':''}" onclick="applyTheme('${t.id}');renderSettingsPage()">
      <div class="theme-tile-icon">${t.icon}</div>
      <div class="theme-tile-label">${t.label}</div>
    </div>`).join('');
  // Shortcuts
  const sb=document.getElementById('settings-sk-body');
  if(sb) sb.innerHTML=`<div style="display:flex;flex-direction:column;gap:4px">
    ${Object.entries(sk).map(([action,s])=>`
    <div class="sk-row">
      <div class="sk-action">${s.label}</div>
      <div class="sk-capture${listeningAction===action?' listening':''}" data-action="${action}" onclick="startListening('${action}');renderSettingsPage()">
        ${listeningAction===action?'按下新按鍵…':(s.ctrl?'⌘+':'')+s.key.replace('Escape','Esc').replace('Delete','Del')}
      </div>
    </div>`).join('')}
  </div>`;
  const cm=document.getElementById('cmd-mode-select');
  if(cm) cm.value=CMD.mode;
  const cf=document.getElementById('cmd-filter');
  const q=(cf?.value||'').trim().toLowerCase();
  const list=document.getElementById('cmd-list');
  if(list){
    const rows=COMMANDS.filter(c=>!q||c.label.toLowerCase().includes(q)||c.id.includes(q)).map(c=>{
      const allowed=CMD.allowed(c.id);
      return `<div style="display:flex;align-items:center;justify-content:space-between;border:1px solid var(--border);background:var(--surface);border-radius:8px;padding:8px 10px;margin-bottom:6px">
        <div style="display:flex;flex-direction:column">
          <div style="font-weight:600;font-size:13px">${c.label}</div>
          <div style="font-size:11px;color:var(--text-subtle)">${c.id}</div>
        </div>
        <label class="cb-item" style="cursor:pointer">
          <input type="checkbox" ${allowed?'checked':''} onchange="toggleCmd('${c.id}')" style="margin-right:6px">
          <span>${allowed?'允許':'停用'}</span>
        </label>
      </div>`;
    }).join('');
    list.innerHTML = rows || `<div style="color:var(--text-muted);font-size:12px">無符合的指令</div>`;
  }
}

/* ── Backup (完整備份：全部模組) ── */
function exportAll(){
  if(!CMD.allowed('backup.export')){ toast('此指令已被停用'); return; }
  const data={
    version:'crm-v4',
    exportedAt:new Date().toISOString(),
    nodes,
    events,
    tasks,
    salesData,
    dailyReports,
    monthlyGoals,
    monthlySalesTargets,
  };
  const json=JSON.stringify(data,null,2);
  const b=new Blob([json],{type:'application/json'});
  const u=URL.createObjectURL(b);
  const a=document.createElement('a');
  a.href=u;
  a.download=`fdd-crm-backup-${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(u);
  toast(`備份匯出完成（${Math.round(json.length/1024)} KB）`);
}

function importAll(ev){
  if(!CMD.allowed('backup.import')){ toast('此指令已被停用'); return; }
  const f=ev.target.files[0];if(!f)return;
  const r=new FileReader();
  r.onload=e=>{
    try{
      const d=JSON.parse(e.target.result);
      if(!d.nodes&&!d.salesData){toast('匯入失敗：不是有效的備份檔案');return;}
      if(!confirm(`確定匯入備份？\n匯出時間：${d.exportedAt||'未知'}\n將覆蓋目前所有資料。`))return;
      if(d.nodes)             { nodes=d.nodes;                    saveData(); }
      if(d.events)            { events=d.events;                  STORE.saveEvents(); }
      if(d.tasks)             { tasks=d.tasks;                    STORE.saveTasks(); }
      if(d.salesData)         { salesData=d.salesData;            STORE.saveSales(); }
      if(d.dailyReports)      { dailyReports=d.dailyReports;      STORE.saveDailyReports(); }
      if(d.monthlyGoals)      { monthlyGoals=d.monthlyGoals;      STORE.saveMonthlyGoals(); }
      if(d.monthlySalesTargets){ monthlySalesTargets=d.monthlySalesTargets; STORE.saveMonthlySalesTargets(); }
      renderNodes();
      toast('✅ 備份匯入成功');
    }catch(err){toast('匯入失敗：'+err.message);}
  };
  r.readAsText(f);ev.target.value='';
}
function clearAllData(){
  if(!CMD.allowed('data.clear')){ toast('此指令已被停用'); return; }
  if(!confirm('確定清除所有資料？此操作無法復原。'))return;
  [STORE.K.nodes, STORE.K.events, STORE.K.tasks, STORE.K.chat].forEach(k => localStorage.removeItem(k));
  nodes=[];events=[];tasks=[];chatHistory=[];
  loadData();renderNodes();renderSettingsPage();
  toast('已清除所有資料');
}

/* ── Google Calendar — GIS Token Flow (純瀏覽器，不需後端) ── */
const GCAL={
  SCOPE:'https://www.googleapis.com/auth/calendar.readonly',
  tokenClient:null,
  getClientId(){ return localStorage.getItem('gcal-client-id')||''; },
  getToken(){
    try{ return JSON.parse(localStorage.getItem('gcal-token')||'null'); }
    catch(e){ return null; }
  },
  isTokenValid(){
    const t=this.getToken();
    return t && t.access_token && Date.now() < (t.expires_at||0);
  },
  saveToken(resp){
    const t={access_token:resp.access_token, expires_at:Date.now()+(resp.expires_in||3600)*1000};
    localStorage.setItem('gcal-token',JSON.stringify(t));
  },
  clearToken(){
    localStorage.removeItem('gcal-token');
    localStorage.removeItem('gcal-client-id');
  },
  updateStatus(){
    const el=document.getElementById('gcal-status');
    if(!el)return;
    if(this.isTokenValid()) el.textContent='✅ 已連結';
    else if(this.getClientId()) el.textContent='未連結（點擊重新授權）';
    else el.textContent='未連結';
  },
  initClient(cid){
    if(!window.google?.accounts?.oauth2){ toast('GIS 尚未載入，請稍後再試'); return; }
    this.tokenClient=window.google.accounts.oauth2.initTokenClient({
      client_id:cid,
      scope:this.SCOPE,
      callback:(resp)=>{
        if(resp.error){ toast('Google 授權失敗：'+resp.error); return; }
        GCAL.saveToken(resp);
        GCAL.updateStatus();
        toast('✅ Google 日曆已連結');
        fetchGcalEvents();
      }
    });
  },
  requestToken(){
    if(!this.tokenClient){ toast('尚未初始化，請重新整理頁面'); return; }
    this.tokenClient.requestAccessToken({prompt:''});
  }
};

function startGoogleOAuth(){
  let cid=GCAL.getClientId();
  if(!cid){
    cid=(prompt('請輸入 Google OAuth Client ID（到 Google Cloud Console > 憑證 取得）')||'').trim();
    if(!cid){ toast('未提供 Client ID'); return; }
    localStorage.setItem('gcal-client-id',cid);
  }
  GCAL.initClient(cid);
  GCAL.requestToken();
}

function resetGoogleClientId(){
  GCAL.clearToken();
  GCAL.updateStatus();
  toast('已清除 Google 日曆連結');
}

function handleOAuthReturn(){ /* 舊 code flow 已棄用，GIS token flow 不需要 */ }

async function fetchGcalEvents(){
  if(!GCAL.isTokenValid()){ GCAL.updateStatus(); return; }
  const token=GCAL.getToken().access_token;
  const now=new Date();
  const timeMin=new Date(now.getFullYear(),now.getMonth(),1).toISOString();
  const timeMax=new Date(now.getFullYear(),now.getMonth()+2,1).toISOString();
  try{
    const res=await fetch(
      `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(timeMin)}&timeMax=${encodeURIComponent(timeMax)}&singleEvents=true&orderBy=startTime&maxResults=50`,
      {headers:{Authorization:`Bearer ${token}`}}
    );
    if(res.status===401){ GCAL.clearToken(); GCAL.updateStatus(); toast('Google Token 已過期，請重新連結'); return; }
    const d=await res.json();
    const gcalEvents=(d.items||[]).map(ev=>({
      id:'gcal-'+ev.id,
      title:ev.summary||'(無標題)',
      date:(ev.start?.date||ev.start?.dateTime||'').slice(0,10),
      allDay:!!ev.start?.date,
      source:'gcal'
    })).filter(ev=>ev.date);
    // merge into events array (avoid duplicates)
    gcalEvents.forEach(ge=>{
      if(!events.find(e=>e.id===ge.id)) events.push(ge);
    });
    renderCalendar();
    toast(`已同步 ${gcalEvents.length} 筆 Google 日曆事件`);
  }catch(err){
    console.error('[gcal]',err);
    toast('Google 日曆同步失敗');
  }
}

// Load GIS script lazily when settings page opens
function ensureGisLoaded(cb){
  if(window.google?.accounts?.oauth2){ cb&&cb(); return; }
  const s=document.createElement('script');
  s.src='https://accounts.google.com/gsi/client';
  s.async=true;
  s.defer=true;
  s.onload=()=>{
    const cid=GCAL.getClientId();
    if(cid) GCAL.initClient(cid);
    cb&&cb();
  };
  document.head.appendChild(s);
}

/* ═══════════════════════════════════════
   INIT
═══════════════════════════════════════ */
/* ═══════════════════════════════════════
   THEME
═══════════════════════════════════════ */
const THEMES = [
  { id:'dark',       label:'深色',      icon:'🌑' },
  { id:'dark-blue',  label:'深藍',      icon:'🌌' },
  { id:'light',      label:'淺色',      icon:'☀️' },
  { id:'light-warm', label:'暖色',      icon:'🌤' },
  { id:'sage-gold',  label:'清新金綠',   icon:'🛫'  },
  { id:'impact',     label:'Impact',    icon:'⚡'  },
  { id:'neuo',       label:'浮凸 2.5D',  icon:'🪨'  },
];
function applyTheme(id){
  document.documentElement.setAttribute('data-theme', id);
  localStorage.setItem(STORE.K.theme, id);
  const isLight = id==='light'||id==='light-warm'||id==='sage-gold'||id==='neuo';
  document.documentElement.style.setProperty('--node-shadow', isLight ? '0 2px 8px rgba(0,0,0,.12)' : '0 2px 8px rgba(0,0,0,.4)');
}
function loadTheme(){
  applyTheme(localStorage.getItem(STORE.K.theme)||'dark');
}


function init(){
  loadTheme();
  loadData();
  initDrafts();
  // Init GIS lazily; if token already valid, refresh calendar events
  ensureGisLoaded(()=>{
    GCAL.updateStatus();
    if(GCAL.isTokenValid()) fetchGcalEvents();
  });
  // Initialize page display via JS (not CSS class) to avoid specificity conflicts
  document.querySelectorAll('.page').forEach(p=>{p.style.display='none';});
  const initPage=document.getElementById('page-crm');
  if(initPage)initPage.style.display=PAGE_DISPLAY['crm']||'flex';

  const needsLayout=nodes.some(n=>n.x===undefined||n.x===null);
  if(needsLayout){
    autoLayout();
    saveData();
  }

  initCanvas();
  renderNodes();
  renderShortcutsHint();

  requestAnimationFrame(()=>{
    requestAnimationFrame(()=>{ fitView(); });
  });

  updateStats();
  updateAiModelBadge();
}

document.addEventListener('DOMContentLoaded',init);

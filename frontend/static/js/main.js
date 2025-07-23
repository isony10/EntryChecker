/* ===== EntryChecker main.js – 2025-07-20 ===== */

/* ───────── 1. 규칙 정의 & 헬퍼 ───────── */
let logicTree = { id: 0, type: 'group', op: 'AND', items: [] };
let nextId = 1;
const ruleTitles = {
  weekend_txn: '주말·공휴일 거래',
  amount_over: '금액 조건',
  keyword_search: '특정 키워드',
  party_freq: '거래처별 거래 횟수',
  round_million: '백만단위 이하 모두 0',
  uniform_account: '동일 계정 전표세트',
  unbalanced_set: '차/대변 불일치 세트'
};
function newGroup(){ return { id: nextId++, type:'group', op:'AND', items:[] }; }
function newCond(rule){
  const tmpl = genRule(rule) || {};
  const cond = { id: nextId++, type:'cond', rule };
  if(tmpl.type==='amount'){
    cond.op = tmpl.op;
    cond.value = tmpl.value;
    cond.target = tmpl.target;
  }else if(tmpl.type==='input'){
    cond.value = tmpl.value;
  }else if(tmpl.type==='count'){
    cond.op = tmpl.op;
    cond.value = tmpl.value;
  }
  return cond;
}
const rules = [];

/* id → 새 규칙 템플릿 */
function genRule(id){
  switch(id){
    case 'weekend_txn':
      return { id, name:'주말·공휴일 거래', type:'boolean', enabled:true };
    case 'amount_over':
      return { id, name:'금액 조건', type:'amount', op:'>', value:0, target:'debit', enabled:true };
    case 'keyword_search':
      return { id, name:'특정 키워드', type:'input', value:'', enabled:true };
    case 'party_freq':
      return { id, name:'거래처별 거래 횟수', type:'count', op:'>=', value:0, enabled:true };
    case 'round_million':
      return { id, name:'백만단위 이하 모두 0', type:'boolean', enabled:true };
    case 'uniform_account':
      return { id, name:'동일 계정 전표세트', type:'boolean', enabled:true };
    case 'unbalanced_set':
      return { id, name:'차/대변 불일치 세트', type:'boolean', enabled:true };
    default: return null;
  }
}

/* ───────── 2. DOM 캐싱 ───────── */
const $file      = document.getElementById('file-upload');
const $run       = document.getElementById('run-analysis');
const $ruleList  = document.getElementById('rule-list');
const $ruleCards = document.getElementById('rule-cards');
const $logicTree = document.getElementById('logic-tree');
const $log       = document.getElementById('log-content');
const $tableWrap = document.getElementById('table-container');
const $chkSet    = document.getElementById('chk-whole-voucher');
const $chkOnly   = document.getElementById('chk-show-matching-only');
const $loading   = document.getElementById('loading');

/* ───────── 3. UI – 규칙 카드 렌더 ───────── */
function renderRules(){
  $ruleCards.innerHTML='';
  rules.forEach((r,i)=>{
    const card=document.createElement('div');
    card.className=`border p-3 rounded-lg mb-2 flex items-start gap-2 cursor-pointer
                    ${r.enabled?'bg-blue-50 border-blue-400':'bg-white'}`
    card.onclick=e=>{
      // 클릭이 카드 내부 컨트롤이 아니라면 토글
      if(!['INPUT','SELECT','BUTTON'].includes(e.target.tagName)){ r.enabled=!r.enabled; renderRules(); }
    };

    /* 좌측 활성 아이콘 */
    const bullet=`<span class="mt-1 text-sm w-4">${r.enabled?'🟢':'⚪'}</span>`;

    /* 본문(타이틀 + 컨트롤) */
    let body=`<div class="flex-1">
                <h4 class="font-medium">${r.name}</h4>`;
    // 입력/연산자 컨트롤
    if(r.type==='amount'){
      body+=`
        <div class="flex items-center gap-2 mt-1" onclick="event.stopPropagation();">
          <select class="border rounded px-1 py-0.5 text-sm"
                  onchange="rules[${i}].op=this.value">
            ${['>','>=','==','<=','<'].map(op=>`<option ${op===r.op?'selected':''}>${op}</option>`).join('')}
          </select>
          <input type="number" class="border rounded w-24 px-1 py-0.5 text-sm"
                 value="${r.value}"
                 oninput="rules[${i}].value=parseFloat(this.value||0)">
        </div>`;
    }else if(r.type==='count'){
      body+=`
        <div class="flex items-center gap-2 mt-1" onclick="event.stopPropagation();">
          <select class="border rounded px-1 py-0.5 text-sm"
                  onchange="rules[${i}].op=this.value">
            ${['>','>=','==','<=','<'].map(op=>`<option ${op===r.op?'selected':''}>${op}</option>`).join('')}
          </select>
          <input type="number" class="border rounded w-20 px-1 py-0.5 text-sm"
                 value="${r.value}"
                 oninput="rules[${i}].value=parseFloat(this.value||0)">
        </div>`;
    }else if(r.type==='input'){
      body+=`
        <input type="text" class="border rounded w-full mt-1 px-1 py-0.5 text-sm"
               value="${r.value}"
               onclick="event.stopPropagation();"
               oninput="rules[${i}].value=this.value">`;
    }
    body+='</div>';

    /* 삭제 버튼 */
    const del=`<button class="text-red-500 text-sm hover:underline"
                     onclick="event.stopPropagation(); rules.splice(${i},1); renderRules();">
                 삭제
               </button>`;

    card.innerHTML=bullet+body+del;
    $ruleCards.appendChild(card);
  });
}

/* 조건 추가 버튼 */
const $btnAddCond = document.getElementById('add-condition-btn');
if($btnAddCond){
  $btnAddCond.onclick=()=>{
    const selEl=document.getElementById('condition-select');
    if(!selEl) return;
    const sel=selEl.value;

    logicTree.items.push(newCond(sel));
    renderTree();
  };
}
document.getElementById('add-group-btn').onclick = () => {
  logicTree.items.push(newGroup());
  renderTree();
};

function renderTree(){
  $logicTree.innerHTML='';
  $logicTree.appendChild(renderGroup(logicTree));
}

function renderGroup(g){
  const wrap=document.createElement('div');
  wrap.className='border p-2 rounded';
  wrap.dataset.groupId=g.id;

  // header
  const header=document.createElement('div');
  header.className='flex items-center gap-2 mb-1';
  const sel=document.createElement('select');
  ['AND','OR'].forEach(op=>{
    const o=document.createElement('option');
    o.value=op; o.textContent=op; if(g.op===op) o.selected=true; sel.appendChild(o);
  });
  sel.onchange=()=>{ g.op=sel.value; };

  header.appendChild(sel);
  if(g!==logicTree){
    const del=document.createElement('button');
    del.textContent='삭제';
    del.className='text-xs text-red-500';
    del.onclick=()=>{ deleteItem(logicTree,g.id); renderTree(); };
    header.appendChild(del);
  }
  wrap.appendChild(header);

  const items=document.createElement('div');
  items.className='pl-4 space-y-1';
  items.dataset.groupId=g.id;
  g.items.forEach(it=>items.appendChild(renderItem(it)));
  wrap.appendChild(items);

  new Sortable(items,{
    group:'nested',
    animation:150,
    filter:'input,select,textarea',
    preventOnFilter:false,
    onEnd:evt=>{
      const from=findGroupById(logicTree, parseInt(evt.from.dataset.groupId));
      const to=findGroupById(logicTree, parseInt(evt.to.dataset.groupId));
      const [moved]=from.items.splice(evt.oldIndex,1);
      to.items.splice(evt.newIndex,0,moved);
    }
  });

  return wrap;
}

function renderItem(item){
  if(item.type==='group') return renderGroup(item);
  const d=document.createElement('div');
  d.className='border rounded px-2 py-1 flex items-center gap-2';
  d.dataset.itemId=item.id;

  const label=document.createElement('span');
  label.textContent=ruleTitles[item.rule]||item.rule;
  d.appendChild(label);

  if(item.rule==='amount_over'){
    const dcSel=document.createElement('select');
    [['debit','차변'],['credit','대변']].forEach(([v,t])=>{
      const o=document.createElement('option');
      o.value=v; o.textContent=t; if(item.target===v) o.selected=true;
      dcSel.appendChild(o);
    });
    dcSel.onchange=()=>{ item.target=dcSel.value; };

    const sel=document.createElement('select');
    ['>','>=','==','<=','<'].forEach(op=>{
      const o=document.createElement('option');
      o.value=op; o.textContent=op; if(item.op===op) o.selected=true;
      sel.appendChild(o);
    });
    sel.onchange=()=>{ item.op=sel.value; };
    const inp=document.createElement('input');
    inp.type='number';
    inp.className='border rounded w-20 px-1 py-0.5 text-xs';
    inp.value=item.value;
    inp.oninput=()=>{ item.value=parseFloat(inp.value||0); };
    d.appendChild(dcSel);
    d.appendChild(sel);
    d.appendChild(inp);
  }else if(item.rule==='party_freq'){
    const sel=document.createElement('select');
    ['>','>=','==','<=','<'].forEach(op=>{
      const o=document.createElement('option');
      o.value=op; o.textContent=op; if(item.op===op) o.selected=true;
      sel.appendChild(o);
    });
    sel.onchange=()=>{ item.op=sel.value; };
    const inp=document.createElement('input');
    inp.type='number';
    inp.className='border rounded w-20 px-1 py-0.5 text-xs';
    inp.value=item.value;
    inp.oninput=()=>{ item.value=parseFloat(inp.value||0); };
    d.appendChild(sel);
    d.appendChild(inp);
  }else if(item.rule==='keyword_search'){
    const inp=document.createElement('input');
    inp.type='text';
    inp.className='border rounded px-1 py-0.5 text-xs flex-1';
    inp.value=item.value||'';
    inp.oninput=()=>{ item.value=inp.value; };
    d.appendChild(inp);
  }

  const del=document.createElement('button');
  del.textContent='삭제';
  del.className='text-xs text-red-500 ml-2';
  del.onclick=()=>{ deleteItem(logicTree,item.id); renderTree(); };
  d.appendChild(del);
  return d;
}

function findGroupById(tree,id){
  if(tree.id===id) return tree;
  for(const it of tree.items){
    if(it.type==='group'){
      const r=findGroupById(it,id);
      if(r) return r;
    }
  }
  return null;
}

function deleteItem(tree,id){
  for(let i=0;i<tree.items.length;i++){
    const it=tree.items[i];
    if(it.id===id){ tree.items.splice(i,1); return true; }
    if(it.type==='group' && deleteItem(it,id)) return true;
  }
  return false;
}

function collectRuleIds(tree,set=new Set()){
  for(const it of tree.items){
    if(it.type==='cond') set.add(it.rule);
    else if(it.type==='group') collectRuleIds(it,set);
  }
  return set;
}

function collectValues(tree,vals={}){
  for(const it of tree.items){
    if(it.type==='cond'){
      if(it.rule==='keyword_search') vals[it.rule]=it.value;
      else if(it.rule==='amount_over')
        vals[it.rule]={op:it.op,value:it.value,target:it.target};
      else if(it.rule==='party_freq')
        vals[it.rule]={op:it.op,value:it.value};
    }else if(it.type==='group') collectValues(it,vals);
  }
  return vals;
}

/* ───────── 4. 로그 ───────── */
function log(msg,type='info'){
  const p=document.createElement('p');
  p.textContent=`> ${msg}`;
  if(type==='error')  p.classList.add('text-red-400');
  if(type==='success')p.classList.add('text-green-400');
  $log.prepend(p);
}

/* ───────── 5. 테이블 렌더 ───────── */
let dataHeaders=[], journalData=[];
function renderTable(rows,hi=new Set(),ruleMap={}){
  if(!rows.length){ $tableWrap.innerHTML='<p class="text-gray-500">표시할 데이터가 없습니다.</p>'; return; }

  const tbl=document.createElement('table');
  tbl.className='w-full text-sm text-left border';
  const headers=dataHeaders.filter(h=>h!=='프로젝트코드');
  const head=`<thead class="bg-gray-100">
                <tr>${headers.map(h=>`<th class="p-2 border-b">${h}</th>`).join('')}</tr>
              </thead>`;
  const body=`<tbody>
      ${rows.map((row,idx)=>{
        const cls=hi.has(idx)?'highlight':'';
        return `<tr class="border-b hover:bg-gray-50 ${cls}">
                  ${headers.map(c=>`<td class="p-2">${row[c]??''}</td>`).join('')}
                </tr>`;
      }).join('')}
    </tbody>`;
  tbl.innerHTML=head+body;
  $tableWrap.innerHTML=''; $tableWrap.appendChild(tbl);
}

/* ───────── 6. 파일 선택 ───────── */
$file.onchange=e=>{
  const f=e.target.files[0]; if(!f) return;
  log(`파일 선택: ${f.name}`,'info');

  if(/\.(csv)$/i.test(f.name)){
    Papa.parse(f,{
      header:true,
      complete:res=>{
        journalData=res.data; dataHeaders=res.meta.fields;
        renderTable(journalData); log('CSV 파싱 완료','success');
      },
      error:err=>log(`CSV 파싱 오류: ${err.message}`,'error')
    });
  }else{ fetchAndRender(f,[],{}, 'AND', logicTree); }
};

/* ───────── 7. 분석 실행 ───────── */
$run.onclick=()=>{ analyze(); };
async function analyze(){
  const f=$file.files[0]; if(!f){ log('파일을 먼저 선택하세요.','error'); return; }

  const activeRules=[...collectRuleIds(logicTree)];
  if(!activeRules.length){ log('활성화된 규칙이 없습니다.','error'); return; }

  const vals=collectValues(logicTree);

  await fetchAndRender(
    f,
    activeRules,
    vals,
    'AND',
    logicTree
  );
}

/* ───────── 8. 서버 호출 & 결과 처리 ───────── */
async function fetchAndRender(file,active,vals,logic='AND',tree={}){
  const fd=new FormData();
  fd.append('file',file);
  fd.append('active_rules',JSON.stringify(active));
  fd.append('values',JSON.stringify(vals));
  fd.append('logic_op',logic);
  fd.append('logic_tree', JSON.stringify(tree));

  $loading.classList.remove('hidden');
  try{
    const res=await fetch('/analyze',{method:'POST',body:fd});
    if(!res.ok) throw new Error(await res.text());
    const data=await res.json();

    dataHeaders=data.headers; journalData=data.rows;

    /* 하이라이트 셋 */
    const flagged=new Set(data.flagged_indices);
    let hi=new Set(flagged);
    if($chkSet.checked){
      const keys=new Set([...flagged].map(i=>`${journalData[i]['전표일자']}|${journalData[i]['전표번호']}`));
      journalData.forEach((r,i)=>{ if(keys.has(`${r['전표일자']}|${r['전표번호']}`)) hi.add(i); });
    }

    /* 표시할 행 선택 */
    let rows=journalData.map((r,i)=>({__idx:i,...r}));
    if($chkOnly.checked){
      rows=rows.filter(r=>hi.has(r.__idx));
    }

    const hiDisp=new Set();
    rows.forEach((r,i)=>{ if(hi.has(r.__idx)) hiDisp.add(i); });
    rows=rows.map(r=>{ const c={...r}; delete c.__idx; return c; });

    const rMap={}; for(const k in data.rule_map) rMap[+k]=data.rule_map[k];
    renderTable(rows,hiDisp,rMap);
    log(`분석 완료 – ${hiDisp.size}행 하이라이트`,'success');
  }catch(e){ log('분석 오류: '+e.message,'error'); }
  finally{ $loading.classList.add('hidden'); }
}


/* ───────── 9. 초기 렌더 ───────── */
renderTree();

/* ===== EntryChecker main.js – 2025‑07‑15 ===== */

const rules = [
  { id: 'weekend_txn', name: '주말·공휴일 거래', type: 'boolean', enabled: false },
  { id: 'amount_over_debit', name: '차변 금액 조건', type: 'amount', op: '>', value: 10000000, enabled: false },
  { id: 'amount_over_credit', name: '대변 금액 조건', type: 'amount', op: '>', value: 10000000, enabled: false },
  { id: 'keyword_search', name: '특정 키워드', type: 'input', value: '가지급금,대여금', enabled: false }
];

const fileInput       = document.getElementById('file-upload');
const runBtn          = document.getElementById('run-analysis');
const ruleList        = document.getElementById('rule-list');
const tableContainer  = document.getElementById('table-container');
const logContent      = document.getElementById('log-content');
const chkWholeVoucher = document.getElementById('chk-whole-voucher');
const loadingBadge    = document.getElementById('loading');

let dataHeaders = [];
let journalData = [];

/* ---------- 규칙 카드 렌더 ---------- */
function renderRules() {
  ruleList.innerHTML = '';

  rules.forEach((r, i) => {
    const card = document.createElement('div');
    card.className = `rule-card p-4 border rounded-lg cursor-pointer ${r.enabled ? 'active' : ''}`;
    card.onclick = () => { r.enabled = !r.enabled; renderRules(); };

    /* 카드 내부 HTML */
    let html = `<h4 class="font-bold">${i + 1}. ${r.name}</h4>`;

    /* ① 금액 조건 (차변·대변) ― 연산자 + 값 입력 */
if (r.type === 'amount') {
  html += `
    <div class="mt-2 flex gap-2 items-center">
      <select class="border rounded p-1"
              onchange="rules[${i}].op=this.value;"
              onclick="event.stopPropagation();"
              onmousedown="event.stopPropagation();">
        ${['>', '>=', '==', '<=', '<'].map(op =>
          `<option value="${op}" ${op === r.op ? 'selected' : ''}>${op}</option>`
        ).join('')}
      </select>
      <input type="number" class="border rounded p-1 w-24"
             value="${r.value}"
             onclick="event.stopPropagation();"
             oninput="rules[${i}].value=parseFloat(this.value || 0)">
      원
    </div>`;
  }

    /* ② 텍스트 입력형 (키워드) */
    else if (r.type === 'input') {
      html += `
        <input type="text" class="border rounded p-1 mt-2 w-full"
               value="${r.value}"
               onclick="event.stopPropagation();"
               oninput="rules[${i}].value=this.value">`;
    }

    card.innerHTML = html;
    ruleList.appendChild(card);
  });
}

/* ---------- 로그 ---------- */
function log(msg, type='info') {
  const p = document.createElement('p');
  p.textContent = '> ' + msg;
  if (type === 'error')   p.classList.add('text-red-400');
  if (type === 'success') p.classList.add('text-green-400');
  logContent.prepend(p);
}

/* ---------- 테이블 ---------- */
function renderTable(rows, highlightSet=new Set(), ruleMap={}) {
  if (!rows.length) {
    tableContainer.innerHTML = '<p class="text-gray-500">표시할 데이터가 없습니다.</p>';
    return;
  }

  const table = document.createElement('table');
  table.className = 'w-full text-sm text-left border';

  /* 헤더 */
  const thead = document.createElement('thead');
  thead.className = 'bg-gray-100';
  let headRow = '<tr><th class="p-2 border-b w-12">조건</th>';
  dataHeaders.forEach(h => headRow += `<th class="p-2 border-b">${h}</th>`);
  headRow += '</tr>';
  thead.innerHTML = headRow;
  table.appendChild(thead);

  /* 본문 */
  const tbody = document.createElement('tbody');
  rows.forEach((row, idx) => {
    const cond = (ruleMap[idx] || []).join(',');
    const hi   = highlightSet.has(idx) ? 'highlight' : '';
    let tr = `<tr class="border-b hover:bg-gray-50 ${hi}"><td class="p-2 text-center">${cond}</td>`;
    dataHeaders.forEach(col => tr += `<td class="p-2">${row[col] ?? ''}</td>`);
    tr += '</tr>';
    tbody.insertAdjacentHTML('beforeend', tr);
  });
  table.appendChild(tbody);

  tableContainer.innerHTML = '';
  tableContainer.appendChild(table);
}

/* ---------- 파일 선택 ---------- */
fileInput.addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;

  log(`파일 선택: ${file.name}`, 'info');

  if (/\\.csv$/i.test(file.name)) {
    Papa.parse(file, {
      header: true,
      complete: res => {
        journalData = res.data;
        dataHeaders = res.meta.fields;
        renderTable(journalData);
        log('CSV 파싱 완료', 'success');
      },
      error: err => log(`CSV 파싱 오류: ${err.message}`, 'error')
    });
  } else {
    // Excel: 규칙 없이 백엔드 호출 → 미리보기
    await fetchAndRender(file, [], {},'AND');
  }
});

/* ---------- 분석 실행 ---------- */
runBtn.addEventListener('click', async () => {
  const logicOp = document.getElementById('logic-op').value;
  const file = fileInput.files[0];
  if (!file) { log('파일을 먼저 선택하세요.', 'error'); return; }

  const active = rules.filter(r => r.enabled).map(r => r.id);
  if (!active.length) { log('활성화 규칙이 없습니다.', 'error'); return; }

  const vals = {};
  rules.forEach(r => {
    if (!r.enabled) return;
    if (r.type === 'input')   vals[r.id] = r.value;
    if (r.type === 'amount')  vals[r.id] = { op: r.op, value: r.value };
  });

  await fetchAndRender(file, active, vals, logicOp);
});

/* ---------- 공통 fetch ---------- */
async function fetchAndRender(file, activeRules, ruleVals, logicOp = 'AND') {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('active_rules', JSON.stringify(activeRules));
  fd.append('values', JSON.stringify(ruleVals));
  fd.append('logic_op',     logicOp);

  loadingBadge.classList.remove('hidden');
  try {
    const res = await fetch('/analyze', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    dataHeaders = data.headers;
    journalData = data.rows;

    /* 하이라이트 셋 만들기 */
    let hiSet = new Set(data.flagged_indices);
    if (chkWholeVoucher.checked && hiSet.size) {
      const keys = new Set([...hiSet].map(i =>
          `${journalData[i]['전표일자']}|${journalData[i]['전표번호']}`));
      journalData.forEach((row, idx) => {
        const key = `${row['전표일자']}|${row['전표번호']}`;
        if (keys.has(key)) hiSet.add(idx);
      });
    }

    /* rule_map → key가 문자열이라 Number로 변환 */
    const rMap = {};
    for (const k in data.rule_map) rMap[+k] = data.rule_map[k];

    renderTable(journalData, hiSet, rMap);
    log(`분석 완료 – ${[...hiSet].length}행 하이라이트`, 'success');
  } catch (e) {
    log('분석 오류: ' + e.message, 'error');
  } finally {
    loadingBadge.classList.add('hidden');
  }
}

/* 규칙 카드 초기화 */
renderRules();

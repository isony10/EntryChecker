import pandas as pd
import numpy as np
import re
import holidays

KR_HOLIDAYS = holidays.KR()  # 대한민국 공휴일

def _parse_dates(series):
    """YYYYMMDD ‧ 엑셀 직렬값 ‧ 문자열 등 어떤 형태든 datetime64로."""
    # 이미 datetime 형이면 그대로
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    s = series.copy()

    # 숫자형: 엑셀 직렬값 or 8자리(YYYYMMDD)
    if pd.api.types.is_numeric_dtype(s):
        s_str = s.astype('Int64').astype(str)
        dt = pd.Series(pd.NaT, index=s.index)

        # 8자리 → YYYYMMDD 포맷
        ymd_mask = s_str.str.fullmatch(r'\d{8}')
        if ymd_mask.any():
            dt.loc[ymd_mask] = pd.to_datetime(
                s_str[ymd_mask], format='%Y%m%d', errors='coerce'
            )

        # 그 외 숫자 → 엑셀 직렬값
        serial_mask = ~ymd_mask
        if serial_mask.any():
            dt.loc[serial_mask] = pd.to_datetime(
                s[serial_mask], unit='D', origin='1899-12-30', errors='coerce'
            )
        return dt

    # 문자열
    raw = s.astype(str).str.strip().str.replace(r'[./]', '-', regex=True)
    dt = pd.to_datetime(raw, errors='coerce')
    ymd_mask = dt.isna() & raw.str.fullmatch(r'\d{8}')
    if ymd_mask.any():
        dt.loc[ymd_mask] = pd.to_datetime(raw[ymd_mask], format='%Y%m%d', errors='coerce')
    return dt

def flag_weekend_txn(df, date_col='전표일자'):
    """
    토·일 또는 한국 공휴일이면 True. 그 외는 False.
    """
    dt = _parse_dates(df[date_col])

    is_weekend = dt.dt.weekday.isin([5, 6])          # 토(5), 일(6)
    is_holiday = dt.apply(lambda d: d.date() in KR_HOLIDAYS if pd.notna(d) else False)
    return is_weekend | is_holiday         # 둘 중 하나면 강조



def flag_amount_over(df, op, thr, is_debit=True):
    col = '차변금액' if is_debit else '대변금액'

    if   op == '>':  return df[col] >  thr
    elif op == '>=': return df[col] >= thr
    elif op == '==': return df[col] == thr
    elif op == '<=': return df[col] <= thr
    elif op == '<':  return df[col] <  thr
    else:            return pd.Series(False, index=df.index)

def flag_keyword(df, keywords):
    kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
    if not kw_list:
        return pd.Series(False, index=df.index)

    pattern = '|'.join(map(re.escape, kw_list))
    # 계정과목 + 적요 열 모두 검색, 대소문자 무시
    subject = df['계정과목'].astype(str)
    desc    = df.get('적요', pd.Series('', index=df.index)).astype(str)

    return subject.str.contains(pattern, case=False, na=False) | \
           desc.str.contains(pattern, case=False, na=False)

def flag_party_freq(df, op, thr):
    """전표세트 기준 거래 횟수 조건."""
    if '거래처코드' not in df.columns:
        return pd.Series(False, index=df.index)

    tmp = df[['거래처코드', '전표일자', '전표번호']].dropna(subset=['거래처코드'])
    sets = tmp.drop_duplicates()
    counts = sets.groupby('거래처코드').size()
    freq = df['거래처코드'].map(counts).fillna(0)

    if   op == '>':  return freq >  thr
    elif op == '>=': return freq >= thr
    elif op == '==': return freq == thr
    elif op == '<=': return freq <= thr
    elif op == '<':  return freq <  thr
    else:            return pd.Series(False, index=df.index)

def flag_round_million(df):
    """차/대변 금액이 1,000,000원 단위일 때."""
    debit = df['차변금액'].abs()
    credit = df['대변금액'].abs()
    m_debit = (debit != 0) & (debit % 1_000_000 == 0)
    m_credit = (credit != 0) & (credit % 1_000_000 == 0)
    return m_debit | m_credit

def flag_uniform_account(df):
    """전표세트 내 계정과목이 모두 동일한 경우."""
    if not {'전표일자', '전표번호', '계정과목'}.issubset(df.columns):
        return pd.Series(False, index=df.index)
    grouped = df.groupby(['전표일자', '전표번호'])['계정과목'].nunique()
    target_sets = set(grouped[grouped == 1].index)
    idx = list(zip(df['전표일자'], df['전표번호']))
    return pd.Series([(k in target_sets) for k in idx], index=df.index)

def flag_unbalanced_set(df):
    """전표세트 차변 합과 대변 합이 일치하지 않음."""
    if not {'전표일자', '전표번호', '차변금액', '대변금액'}.issubset(df.columns):
        return pd.Series(False, index=df.index)
    sums = df.groupby(['전표일자', '전표번호'])[['차변금액', '대변금액']].sum()
    bad_sets = set(sums.index[sums['차변금액'] != sums['대변금액']])
    idx = list(zip(df['전표일자'], df['전표번호']))
    return pd.Series([(k in bad_sets) for k in idx], index=df.index)

def analyze_journal(
    df,
    active_rules,
    rule_values,
    logic_op: str = 'AND',
    logic_tree: dict | None = None,
):

    # ───────────────── 1. 숫자 열 변환 ──────────────────
    df['차변금액'] = pd.to_numeric(df.get('차변금액', 0), errors='coerce').fillna(0)
    df['대변금액'] = pd.to_numeric(df.get('대변금액', 0), errors='coerce').fillna(0)

    # ───────────────── 2. 규칙별 mask 계산 ──────────────────
    masks = []  # 모든 mask 리스트 (순서 유지)
    rule_map = {i: [] for i in df.index}  # index → [규칙 번호]
    rule_no = 1  # 1부터 부여
    rule_masks: dict[str, pd.Series] = {}

    if not (logic_tree and logic_tree.get('items')):
        # 주말·공휴일
        if 'weekend_txn' in active_rules:
            m = flag_weekend_txn(df)
            rule_masks['weekend_txn'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 금액 조건
        if 'amount_over' in active_rules:
            cond = rule_values.get('amount_over', {})
            op = cond.get('op', '>')
            thr = float(cond.get('value', 0))
            target = cond.get('target', 'debit')
            m = flag_amount_over(df, op, thr, is_debit=(target != 'credit'))
            rule_masks['amount_over'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 키워드 조건
        if 'keyword_search' in active_rules:
            cond = rule_values.get('keyword_search', {})
            kw = cond.get('value', '') if isinstance(cond, dict) else cond
            mode = cond.get('mode', 'include') if isinstance(cond, dict) else 'include'
            m = flag_keyword(df, kw)
            if mode == 'exclude':
                m = ~m
            rule_masks['keyword_search'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 거래처 빈도 조건
        if 'party_freq' in active_rules:
            cond = rule_values.get('party_freq', {})
            op = cond.get('op', '>=')
            thr = float(cond.get('value', 0))
            m = flag_party_freq(df, op, thr)
            rule_masks['party_freq'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 백만단위 이하 모두 0
        if 'round_million' in active_rules:
            m = flag_round_million(df)
            rule_masks['round_million'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 동일 계정과목 세트
        if 'uniform_account' in active_rules:
            m = flag_uniform_account(df)
            rule_masks['uniform_account'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

        # 차변대변 불일치 세트
        if 'unbalanced_set' in active_rules:
            m = flag_unbalanced_set(df)
            rule_masks['unbalanced_set'] = m
            masks.append(m)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
        rule_no += 1

    # ───────────────── 3. 모든 mask 결합 ────────────────────
    def eval_node(node) -> pd.Series:
        nonlocal rule_no
        if not node:
            return pd.Series(False, index=df.index)
        if node.get('type') == 'cond':
            rule = node.get('rule')
            if rule == 'weekend_txn':
                m = flag_weekend_txn(df)
            elif rule == 'amount_over':
                op = node.get('op', '>')
                thr = float(node.get('value', 0))
                target = node.get('target', 'debit')
                m = flag_amount_over(df, op, thr, is_debit=(target != 'credit'))
            elif rule == 'keyword_search':
                kw = node.get('value', '')
                mode = node.get('mode', 'include')
                m = flag_keyword(df, kw)
                if mode == 'exclude':
                    m = ~m
            elif rule == 'party_freq':
                op = node.get('op', '>=')
                thr = float(node.get('value', 0))
                m = flag_party_freq(df, op, thr)
            elif rule == 'round_million':
                m = flag_round_million(df)
            elif rule == 'uniform_account':
                m = flag_uniform_account(df)
            elif rule == 'unbalanced_set':
                m = flag_unbalanced_set(df)
            else:
                m = pd.Series(False, index=df.index)
            for idx in m[m].index:
                rule_map[idx].append(rule_no)
            rule_no += 1
            return m

        items = [eval_node(it) for it in node.get('items', [])]
        if not items:
            return pd.Series(False, index=df.index)
        op = node.get('op', 'AND').upper()
        result = items[0].copy()
        for m in items[1:]:
            if op == 'OR':
                result = result | m
            else:
                result = result & m
        return result

    if logic_tree and logic_tree.get('items'):
        final_mask = eval_node(logic_tree)
    elif not masks:
        final_mask = pd.Series(False, index=df.index)
    elif logic_op.upper() == 'OR':
        final_mask = masks[0]
        for m in masks[1:]:
            final_mask = final_mask | m
    else:  # 기본 AND
        final_mask = masks[0]
        for m in masks[1:]:
            final_mask = final_mask & m

    flagged = list(final_mask[final_mask].index)

    df_disp = df.copy()
    for col in ('차변금액', '대변금액'):
        if col in df_disp.columns:
            df_disp[col] = df_disp[col].apply(lambda v: f"{int(round(v)):,}")

    # ───────────────── 4. 결과 패키징 ──────────────────────
    return {
        "headers": list(df.columns),
        "rows": df_disp.to_dict('records'),
        "flagged_indices": flagged,
        "rule_map": {str(k): v for k, v in rule_map.items()}
    }



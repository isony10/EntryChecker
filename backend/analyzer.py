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

def analyze_journal(df, active_rules, rule_values, logic_op: str = 'AND'):

    # ───────────────── 1. 숫자 열 변환 ──────────────────
    df['차변금액'] = pd.to_numeric(df.get('차변금액', 0), errors='coerce').fillna(0)
    df['대변금액'] = pd.to_numeric(df.get('대변금액', 0), errors='coerce').fillna(0)

    # ───────────────── 2. 규칙별 mask 계산 ──────────────────
    masks     = []                  # 모든 mask 리스트
    rule_map  = {i: [] for i in df.index}   # index → [규칙 번호]
    rule_no   = 1                   # 1부터 부여

    # 주말·공휴일
    if 'weekend_txn' in active_rules:
        m = flag_weekend_txn(df)
        masks.append(m)
        for idx in m[m].index: rule_map[idx].append(rule_no)
    rule_no += 1

    # 차변 금액 조건
    if 'amount_over_debit' in active_rules:
        cond = rule_values.get('amount_over_debit', {})
        op   = cond.get('op', '>')
        thr  = float(cond.get('value', 0))
        m = flag_amount_over(df, op, thr, is_debit=True)   # ← 차변
        masks.append(m)
        for idx in m[m].index: rule_map[idx].append(rule_no)
    rule_no += 1

    # 대변 금액 조건
    if 'amount_over_credit' in active_rules:
        cond = rule_values.get('amount_over_credit', {})
        op   = cond.get('op', '>')
        thr  = float(cond.get('value', 0))
        m = flag_amount_over(df, op, thr, is_debit=False)  # ← 대변
        masks.append(m)
        for idx in m[m].index: rule_map[idx].append(rule_no)
    rule_no += 1

    # 키워드 조건
    if 'keyword_search' in active_rules:
        kw = rule_values.get('keyword_search', '')
        m  = flag_keyword(df, kw)
        masks.append(m)
        for idx in m[m].index: rule_map[idx].append(rule_no)

    # ───────────────── 3. 모든 mask 결합 ────────────────────
    if not masks:
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



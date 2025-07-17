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
    return dt.dt.weekday.isin([5, 6]) | is_holiday         # 둘 중 하나면 강조



def flag_amount_over(df, op, threshold):
    series = (df['차변금액'] , df['대변금액'])
    if   op == '>':  return (series[0] >  threshold) | (series[1] >  threshold)
    if   op == '>=': return (series[0] >= threshold) | (series[1] >= threshold)
    if   op == '=':  return (series[0] == threshold) | (series[1] == threshold)
    if   op == '<=': return (series[0] <= threshold) | (series[1] <= threshold)
    if   op == '<':  return (series[0] <  threshold) | (series[1] <  threshold)
    return pd.Series(False, index=df.index)   # 예외 대응

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

def analyze_journal(df, active_rules, rule_values):
    # 숫자 열 안전 변환
    df['차변금액'] = pd.to_numeric(df['차변금액'], errors='coerce').fillna(0)
    df['대변금액'] = pd.to_numeric(df['대변금액'], errors='coerce').fillna(0)

    flags      = pd.Series(False, index=df.index)
    rule_map   = {i: [] for i in df.index}  # index → [rule 번호]

    # rule 번호는 1부터
    def add_rule(series, num):
        nonlocal flags, rule_map
        match_idx = series[series].index
        flags |= series
        for idx in match_idx:
            rule_map[idx].append(num)

    rule_num = 1
    if 'weekend_txn' in active_rules:
        add_rule(flag_weekend_txn(df), rule_num)
    rule_num += 1


    if 'amount_over' in active_rules:
        cond = rule_values.get('amount_over', {})
        op   = cond.get('op', '>')
        thr  = float(cond.get('value', 0))
        add_rule(flag_amount_over(df, op, thr), rule_num)
    rule_num += 1

    if 'keyword_search' in active_rules:
        kw = rule_values.get('keyword_search', '')
        add_rule(flag_keyword(df, kw), rule_num)

    flagged_idx = flags[flags].index.tolist()
    headers = list(df.columns)
    rows    = df.to_dict('records')

    return {
        "headers": headers,
        "rows": rows,
        "flagged_indices": flagged_idx,
        "rule_map": {str(k): v for k, v in rule_map.items()}  # JSON 직렬화 위해 str key
    }

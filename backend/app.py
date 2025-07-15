import os
from flask import Flask, request, render_template, jsonify
from flask import Response
import pandas as pd
import math
import json
from analyzer import analyze_journal

app = Flask(__name__,
            static_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static'),
            template_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend', 'templates'))

@app.route('/')
def index():
    return render_template('index.html')

# NaN 제거 함수
def clean_nan(obj):
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

#CSV 읽기 함수
def read_csv_flexible(file):
    """
    쉼표·세미콜론·탭 어떤 구분자여도 DataFrame 을 반환.
    인코딩도 CP949 → UTF‑8 순으로 시도.
    """
    enc_try = ['cp949', 'utf-8-sig', 'utf-8']
    for enc in enc_try:
        try:
            # 구분자 자동 감지 (engine='python' 필요)
            df = pd.read_csv(
                file, encoding=enc, sep=None, engine='python'
            )
            if not df.empty and len(df.columns) > 0:
                return df
        except Exception:
            file.seek(0)  # 실패하면 포인터 리셋
            continue
    raise ValueError("CSV 읽기에 실패했습니다. 구분자/인코딩 확인 필요.")

@app.route('/analyze', methods=['POST'])
def analyze():
    file = request.files['file']
    filename = file.filename
    active_rules = json.loads(request.form['active_rules'])
    rule_values = json.loads(request.form['values'])

    try:
        if filename.endswith('.csv'):
            try:
                file.seek(0)             # 파일 객체 포인터 맨 앞으로
                df = read_csv_flexible(file)
            except Exception as e:
                return f"File read error: {e}", 400
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file, engine='openpyxl')
        else:
            return "Unsupported file type", 400

        result = analyze_journal(df, active_rules, rule_values)
        cleaned = clean_nan(result)

        return Response(json.dumps(cleaned, ensure_ascii=False), mimetype='application/json')

    except Exception as e:
        return f"File read error: {str(e)}", 400

if __name__ == '__main__':
    app.run(debug=True, port=8000)

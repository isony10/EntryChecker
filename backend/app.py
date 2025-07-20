import sys
import os
from flask import Flask, request, render_template, jsonify
from flask import Response
import pandas as pd
import math
import json
if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.analyzer import analyze_journal

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
    logic_op    = request.form.get('logic_op', 'AND')
    logic_tree  = json.loads(request.form.get('logic_tree', '{}'))

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

        result = analyze_journal(df, active_rules, rule_values, logic_op, logic_tree)
        cleaned = clean_nan(result)

        return Response(json.dumps(cleaned, ensure_ascii=False), mimetype='application/json')

    except Exception as e:
        return f"File read error: {str(e)}", 400


@app.route('/submit_logic', methods=['POST'])
def submit_logic():
    data = request.get_json(silent=True) or {}
    return jsonify({'received': data})

if __name__ == '__main__':
    app.run(debug=True, port=8000)

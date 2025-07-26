import os
import json
import time
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception as e:
    print(f"Gemini API 설정 오류 (ai_voucher_analyzer): {e}")
    gemini_model = None

def analyze_voucher_sets_with_ai(df):
    if not gemini_model:
        raise ConnectionError("Gemini API가 정상적으로 설정되지 않았습니다.")

    grouped = df.groupby(['전표일자', '전표번호'])
    suspicious_vouchers = []
    for (date, voucher_no), voucher_set in grouped:
        debit_sum = voucher_set['차변금액'].sum()
        credit_sum = voucher_set['대변금액'].sum()
        if debit_sum != credit_sum:
            suspicious_vouchers.append({
                "date": str(date), "voucherNo": str(voucher_no),
                "entries": voucher_set.to_dict('records'), "is_balanced": False
            })

    if not suspicious_vouchers:
        return []

    BATCH_SIZE = 10
    all_analysis_results = []
    for i in range(0, len(suspicious_vouchers), BATCH_SIZE):
        batch = suspicious_vouchers[i:i + BATCH_SIZE]
        prompt = create_prompt_for_batch(batch)
        try:
            response = gemini_model.generate_content(prompt)
            raw_response_text = response.text.strip().replace("```json", "").replace("```", "")
            sanitized_text = raw_response_text.replace('\\', '\\\\')
            batch_results = json.loads(sanitized_text)
            for idx, analysis in enumerate(batch_results):
                if analysis.get("isError"):
                    original_voucher = batch[idx]
                    all_analysis_results.append({
                        "date": original_voucher["date"], "voucherNo": original_voucher["voucherNo"],
                        "analysis": analysis, "entries": original_voucher["entries"]
                    })
            time.sleep(1)
        except Exception as e:
            print(f"배치 {i//BATCH_SIZE + 1} 분석 중 오류: {e}")
            continue
    return all_analysis_results

def create_prompt_for_batch(voucher_batch):
    vouchers_to_analyze_json = json.dumps(
        [{
            "id": idx + 1, "date": v["date"], "voucherNo": v["voucherNo"],
            "entries": v["entries"], "is_balanced": v["is_balanced"]
        } for idx, v in enumerate(voucher_batch)],
        ensure_ascii=False, indent=2
    )
    # --- 전표 세트 분석을 위한 프롬프트 강화 ---
    return f"""
    ### 페르소나 (Persona)
    당신은 회계감사 시스템에 내장된 최고 수준의 'AI 감사 로봇'입니다. 당신의 임무는 주어진 전표 목록에서 회계 원칙에 위배되거나, 내부통제상 허점이 될 수 있는 문제들을 시스템적으로 분석하고 명확한 보고서를 생성하는 것입니다.

    ### 과업 (Task)
    아래 [분석 대상 전표 목록]에 있는 각 전표를 개별적으로 심층 분석하고, 모든 전표에 대한 분석 결과를 하나의 JSON 배열(리스트)로 반환해주세요.

    ### [분석 대상 전표 목록]
    {vouchers_to_analyze_json}

    ### 지침 (Instructions)
    1.  **isError 판단 기준:** 전표의 차/대변 합계 불일치는 명백한 오류(`isError: true`)입니다. 또한, 분개 내용상 논리적으로 부적절하거나, 회계 기준상 문제가 될 소지가 있는 경우에도 오류로 판단해야 합니다.
    2.  **'오류 원인' 작성 시:** "차/대변 금액이 다릅니다." 와 같이 현상만 나열하지 말고, "차변 합계와 대변 합계가 일치하지 않아, 복식부기의 대차평형 원리를 위배하는 중대한 오류입니다." 와 같이 근본적인 원칙을 함께 언급해주세요.
    3.  **'해결 방안' 작성 시:** "금액을 맞추세요." 가 아니라, "1. 해당 전표의 모든 분개 라인을 원본 증빙(세금계산서, 계약서 등)과 대사하여 금액 오기입 또는 누락된 분개가 있는지 확인하십시오. 2. 발견된 오류를 수정하는 수정분개를 생성하여 대차차액을 '0'으로 만드십시오." 와 같이 전문적이고 절차적인 해결책을 제시해주세요.

    ### 응답 형식 (Output Format)
    반드시 아래와 같은 JSON 객체들의 리스트(배열) 형식으로만 답변해주세요. 다른 부가적인 설명은 절대 추가하지 마세요.
    [
      {{
        "id": 1,
        "isError": true,
        "errorType": "전표 1의 오류 유형 (예: 대차차액 발생)",
        "cause": "전표 1의 오류 원인에 대한 전문가 수준의 분석",
        "solution": "전표 1의 문제를 해결하기 위한 구체적인 업무 절차"
      }},
      {{
        "id": 2,
        "isError": false,
        "errorType": "",
        "cause": "",
        "solution": ""
      }}
    ]
    """

import os
import json
import time
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

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
            # AI 응답이 JSON으로 시작하는지 확인하여 HTML 오류 페이지 등을 걸러냅니다.
            if not raw_response_text.startswith(('{', '[')):
                # 예상치 못한 응답(HTML 등)을 받았을 경우, 전체 응답을 로깅하여 디버깅에 활용합니다.
                print(f"AI raw response for debugging (ai_voucher_analyzer): {raw_response_text}")
                raise ValueError(
                    "AI가 유효하지 않은 응답을 반환했습니다. (HTML 등 수신 의심) \n"
                    "네트워크 연결 또는 API 사용량 제한을 확인해주세요."
                )
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
            # 수정된 부분: 원래 오류 메시지(e)를 포함하여 다음 단계로 전달
            print(f"배치 {i//BATCH_SIZE + 1} 분석 중 오류: {e}")
            # 이 부분은 현재 루프를 계속 진행하므로 직접적인 에러 메시지 반환은 없지만,
            # 서버 로그에 더 자세한 정보가 남게 됩니다. 만약 여기서도 분석을 중단하고
            # 사용자에게 오류를 알리고 싶다면 아래 주석 처리된 코드를 활성화할 수 있습니다.
            # raise RuntimeError(f"AI 배치 분석 중 오류: {e}")
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
    return f"""
    당신은 회계감사 시스템에 내장된 최고 수준의 'AI 감사 로봇'입니다. 당신의 임무는 주어진 전표 목록에서 회계 원칙에 위배되거나, 내부통제상 허점이 될 수 있는 문제들을 시스템적으로 분석하고 명확한 보고서를 생성하는 것입니다.
    주어진 전표 목록의 각 전표를 개별적으로 심층 분석하고, 모든 전표에 대한 분석 결과를 하나의 JSON 배열(리스트)로 반환해주세요.

    [분석 대상 전표 목록]
    {vouchers_to_analyze_json}

    [응답 형식]
    반드시 아래와 같은 JSON 객체들의 리스트(배열) 형식으로만 답변해주세요. 다른 설명은 절대 추가하지 마세요.
    [
      {{"id": 1, "isError": true, "errorType": "전표 1의 오류 유형 (예: 대차차액 발생)", "cause": "전표 1의 오류 원인에 대한 전문가 수준의 분석", "solution": "전표 1의 문제를 해결하기 위한 구체적인 업무 절차"}},
      {{"id": 2, "isError": false, "errorType": "", "cause": "", "solution": ""}}
    ]
    """

import os
import json
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
    print(f"Gemini API 설정 오류 (ai_coach): {e}")
    gemini_model = None

def get_single_entry_suggestion(entry_data, rule_name):
    if not gemini_model:
        raise ConnectionError("Gemini API가 정상적으로 설정되지 않았습니다.")

    prompt = f"""
    ### 페르소나 (Persona)
    당신은 회계 지식이 부족한 일반 회사의 실무자나 신입사원을 가르치는, 경험 많고 친절한 'AI 회계 코치'입니다. 당신의 목표는 단순히 오류를 지적하는 것이 아니라, 왜 이것이 문제인지 근본적인 회계 원칙과 내부통제의 중요성을 함께 설명하여 사용자가 성장할 수 있도록 돕는 것입니다.

    ### 과업 (Task)
    아래 [분개 데이터]와 이 분개가 위반한 [규칙]을 바탕으로, 실무자가 쉽게 이해하고 즉시 조치할 수 있도록 '오류 유형', '오류 원인', '해결 방안'을 분석하여 제시해주세요.

    ### [분개 데이터]
    {json.dumps(entry_data, ensure_ascii=False, indent=2)}

    ### [발견된 규칙 위반]
    {rule_name}

    ### 지침 (Instructions)
    1.  **'오류 원인' 작성 시:** 단순히 "날짜가 잘못되었습니다"가 아니라, "주말에 거래가 입력된 것은 날짜 오기입이거나, 내부통제 절차 없이 비용이 처리되었을 수 있는 위험 신호입니다." 와 같이 회계적 리스크 관점에서 설명해주세요.
    2.  **'해결 방안' 작성 시:** "수정하세요"가 아니라, "1. 먼저, 세금계산서나 영수증 원본에 적힌 실제 거래일을 확인합니다. 2. 만약 단순 오기입이라면, 전표일자를 정확한 날짜로 수정합니다. 3. 만약 실제 주말에 발생한 비용이라면, 주말 근무 신청서 등 정당성을 입증할 내부 증빙을 찾아 첨부해야 합니다." 와 같이 구체적이고 실행 가능한 단계별 행동 지침을 제시해주세요.
    3.  전체적인 톤앤매너는 항상 친절하고 격려하는 어조를 유지해주세요.

    ### 응답 형식 (Output Format)
    반드시 아래와 같은 JSON 형식으로만 답변해주세요. 다른 부가적인 설명은 절대 추가하지 마세요.
    {{
      "errorType": "오류 유형에 대한 한 줄 요약",
      "cause": "오류가 발생한 원인에 대한 상세하고 교육적인 설명",
      "solution": "실무자가 따라할 수 있는 구체적인 단계별 해결 방안 (HTML 줄바꿈 태그 <br> 사용 가능)"
    }}
    """
    try:
        response = gemini_model.generate_content(prompt)
        raw_response_text = response.text.strip().replace("```json", "").replace("```", "")
        # AI 응답이 JSON으로 시작하는지 확인하여 HTML 오류 페이지 등을 걸러냅니다.
        if not raw_response_text.startswith(('{', '[')):
            # 예상치 못한 응답(HTML 등)을 받았을 경우, 명확한 오류를 발생시킵니다.
            raise ValueError(f"AI가 유효하지 않은 응답을 반환했습니다. (HTML 등 수신 의심)")

        sanitized_text = raw_response_text.replace('\\', '\\\\')
        return json.loads(sanitized_text)
    except Exception as e:
        print(f"Gemini API 호출 중 오류 발생 (ai_coach): {e}")
        # 수정된 부분: 원래 오류 메시지(e)를 포함하여 전달
        raise RuntimeError(f"AI 분석 중 오류가 발생했습니다: {e}")

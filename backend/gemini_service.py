"""
gemini_service.py - Gemini API integration for free media content site detection
"""
import os
import json
import re
import google.generativeai as genai
from typing import Optional


def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


async def generate_keywords(topic: str) -> list[str]:
    """주제 기반으로 무료 미디어 공유 사이트 탐색용 키워드 생성"""
    model = get_gemini_client()

    prompt = f"""
당신은 웹 검색 전문가입니다. 다음 주제와 관련된 무료 미디어 콘텐츠가 공유되는 사이트를 찾기 위한 검색 키워드를 생성해주세요.

주제: {topic}

요구사항:
- 3개 이하의 단어로 이뤄진 키워드 1개 생성
- 무료 스트리밍, 토렌트, 파일공유, 업로더 사이트 관련 키워드 포함
- 한국어/영어 혼합 가능
- 최신 2024-2026년 트렌드 반영
- 드라마, 영화, 애니메이션, 음악 등 다양한 콘텐츠 유형 고려

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "keywords": ["키워드1", "키워드2", "키워드3", ...]
}}
"""

    response = model.generate_content(prompt)
    text = response.text.strip()
    # text='무료 만화'

    # JSON 파싱
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        data = json.loads(json_match.group())
        return data.get("keywords", [])

    # 폴백: 줄바꿈 파싱
    keywords = [line.strip().strip('"-,') for line in text.split('\n') if line.strip() and len(line.strip()) > 2]
    return keywords[:15]


async def analyze_text_for_leaks(url: str, title: str, text: str) -> dict:
    """텍스트에서 무료 미디어 공유 콘텐츠 분석"""
    if not text or len(text.strip()) < 50:
        return {
            "risk_level": "NONE",
            "risk_score": 0.0,
            "leak_types": [],
            "summary": "분석할 텍스트 없음"
        }

    model = get_gemini_client()

    truncated_text = text[:4000] if len(text) > 4000 else text

    prompt = f"""
당신은 웹 콘텐츠 분석 전문가입니다. 아래 웹페이지 텍스트를 분석하여 **불법 무료 공유 사이트**인지 판단해주세요.

URL: {url}
제목: {title}
텍스트:
{truncated_text}

분석 기준 (다음 중 하나라도 있으면 유출로 판단):
1. 영화/드라마/애니 **무료 스트리밍 직접 제공** (다운로드, 보기, 재생 이미지 버튼)
2. 토렌트, 파일공유 링크 제공
3. 가입 없이 바로 시청 가능
4. 최신 작품을 무료로 제공

**정식 플랫폼은 제외 (유출 아님):**
- 넷플릭스, 디즈니+, 웨이브, 티빙, 쿠팱플레이,왓챠 등 유료 플랫폼 공식사이트
- 유튜브 무료 공개 영상
- 영화사/제작사 공식 사이트

판단 기준:
- HIGH: 불법 무료 공유 명확 - 다운로드/스트리밍 직접 제공
- MEDIUM: 의심 - 광고 , 가입 유도,무료 사이트들 정리,추천,안내, trailer만
- LOW: 관련 콘텐츠 가볍게 언급
- NONE: 불법 무료 공유 없음 (정식 플랫폼이거나 일반 사이트)

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "risk_level": "HIGH|MEDIUM|LOW|NONE",
  "risk_score": 0.0~1.0,
  "leak_types": ["유출유형1", "유출유형2"],
  "summary": "분석 요약 (한국어, 2-3문장)"
}}
"""

    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()

        json_match = re.search(r'\{.*\}', text_resp, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "risk_level": data.get("risk_level", "NONE"),
                "risk_score": float(data.get("risk_score", 0.0)),
                "leak_types": data.get("leak_types", []),
                "summary": data.get("summary", "분석 완료")
            }
    except Exception as e:
        print(f"[Gemini 분석 오류] {url}: {e}")

    return {
        "risk_level": "NONE",
        "risk_score": 0.0,
        "leak_types": [],
        "summary": "분석 중 오류 발생"
    }


async def analyze_pages_batch(pages: list[dict]) -> dict:
    """여러 페이지를 하나로 합쳐서 한 번에 분석"""
    if not pages:
        return {
            "risk_level": "NONE",
            "risk_score": 0.0,
            "leak_types": [],
            "summary": "분석할 페이지 없음"
        }

    model = get_gemini_client()

    # 모든 페이지 텍스트 합치기
    combined_text = ""
    page_list = []
    
    for i, page in enumerate(pages):
        text = page.get("text", "")[:2000]  # 페이지당 2000자
        combined_text += f"\n\n--- 페이지 {i+1} ---\nURL: {page.get('url')}\n제목: {page.get('title')}\n내용: {text}"
        page_list.append({
            "url": page.get("url"),
            "title": page.get("title"),
            "keyword": page.get("keyword")
        })

    # 8000자 제한
    combined_text = combined_text[:8000]

    prompt = f"""
당신은 웹 콘텐츠 분석 전문가입니다. 아래 여러 웹페이지들을 분석하여 **불법 무료 공유 사이트**가 있는지 판단해주세요.

{combined_text}

분석 기준 (다음 중 하나라도 있으면 유출으로 판단):
1. 영화/드라마/애니 무료 스트리밍 직접 제공 (다운로드, 보기 버튼)
2. 토렌트, 파일공유 링크 제공
3. 가입 없이 바로 시청 가능
4. 최신 작품 무료 제공

**정식 플랫폼은 제외 (유출 아님):**
- 넷플릭스, 디즈니+, 웨이브, 티빙, 쿠팡플레이, 왓챠 등 유료 플랫폼 공식사이트
- 유튜브 무료 공개 영상
- 영화사/제작사 공식 사이트

판단 기준:
- HIGH: 불법 무료 공유 명확
- MEDIUM: 의심 - 광고 많음, 가입 유도
- LOW: 관련 콘텐츠轻微 언급
- NONE: 불법 무료 공유 없음

각 페이지별 결과를 아래 JSON 배열 형식으로 응답하세요:
[
  {{"url": "URL1", "title": "제목1", "risk_level": "HIGH|MEDIUM|LOW|NONE", "risk_score": 0.0~1.0, "leak_types": [], "summary": "요약"}},
  {{"url": "URL2", "title": "제목2", "risk_level": "NONE", ...}}
]
"""

    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()

        # JSON 배열 파싱
        json_match = re.search(r'\[.*\]', text_resp, re.DOTALL)
        if json_match:
            results = json.loads(json_match.group())
            return {
                "results": results,
                "total_pages": len(pages)
            }
    except Exception as e:
        print(f"[Gemini 배치 분석 오류]: {e}")

    return {
        "results": [],
        "total_pages": len(pages)
    }

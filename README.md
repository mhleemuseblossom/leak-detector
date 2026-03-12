# 🛡️ SENTINEL — 정보 유출 탐지 시스템

Gemini AI 기반 자동화 정보 유출 탐지 플랫폼

## 🗂️ 프로젝트 구조

```
leak-detector/
├── backend/
│   ├── main.py           # FastAPI 서버
│   ├── crawler.py        # Playwright + httpx 크롤러
│   ├── gemini_service.py # Gemini API
│   └── database.py       # SQLite DB
├── frontend/
│   └── index.html        # 웹 대시보드
├── data/                 # DB 자동 생성 경로
├── requirements.txt
└── start.sh
```

## 🚀 실행 방법

### 1단계 — API 키 설정

macOS / Linux:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

Windows PowerShell:
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

### 2단계 — 의존성 설치

```bash
pip install -r requirements.txt
```

### 3단계 — Playwright 브라우저 설치 (JS 렌더링용)

```bash
python -m playwright install chromium --with-deps
```

Playwright 설치 불가 환경에서는 httpx로 자동 fallback됩니다.

### 4단계 — 서버 실행

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

또는 루트에서:
```bash
chmod +x start.sh && ./start.sh
```

### 5단계 — 브라우저에서 접속

```
http://localhost:8000
```

## ⚙️ 설정 조정 (crawler.py)

```python
self.max_depth = 2              # 링크 확산 깊이
self.max_pages_per_keyword = 5  # 키워드당 최대 페이지
```

## ⚠️ 주의
자사 정보 유출 모니터링 / 보안 연구 목적으로만 사용하세요.

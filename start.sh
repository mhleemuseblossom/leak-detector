#!/bin/bash
# start.sh - SENTINEL 시작 스크립트

set -e

echo "╔══════════════════════════════════════════╗"
echo "║     SENTINEL - 정보 유출 탐지 시스템     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 환경변수 확인
if [ -z "$GEMINI_API_KEY" ]; then
  echo "❌ 오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다."
  echo ""
  echo "설정 방법:"
  echo "  export GEMINI_API_KEY='your-api-key-here'"
  echo ""
  exit 1
fi

echo "✅ GEMINI_API_KEY 확인됨"
echo ""

# Python 의존성 설치
echo "📦 의존성 설치 중..."
pip install -r requirements.txt --quiet --break-system-packages

# Playwright 설치 (chromium만)
echo "🎭 Playwright Chromium 설치 중..."
python -m playwright install chromium --with-deps 2>/dev/null || echo "⚠️ Playwright 설치 실패 (httpx fallback 사용)"

echo ""
echo "🚀 서버 시작..."
echo "📊 대시보드: http://localhost:8000"
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --loop asyncio --reload

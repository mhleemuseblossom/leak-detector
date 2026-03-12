"""
main.py - FastAPI 메인 서버
"""
import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 현재 파일 기준 절대 경로
BASE_DIR = Path(__file__).parent.parent  # leak-detector/
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

from database import (
    init_db, create_session, save_keywords, save_page,
    save_leak_result, finish_session, get_session_results, get_all_sessions
)
from gemini_service import generate_keywords, analyze_text_for_leaks, analyze_pages_batch
from crawler import LeakCrawler

app = FastAPI(title="Leak Detector API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 진행 상황 저장 (SSE용)
progress_queues: dict[str, asyncio.Queue] = {}
session_tasks: dict[str, bool] = {}  # session_id -> is_running


class ScanRequest(BaseModel):
    topic: str
    custom_keywords: Optional[list[str]] = None


@app.on_event("startup")
async def startup():
    DATA_DIR.mkdir(exist_ok=True)
    await init_db()
    print(f"✅ DB 초기화 완료")
    print(f"📁 프론트엔드 경로: {FRONTEND_DIR}")
    print(f"📊 대시보드: http://localhost:8000")


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": f"index.html 없음: {index}"}, status_code=404)
    return FileResponse(str(index))


# 정적 파일 서빙 (CSS, JS 등 필요 시)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/api/sessions")
async def get_sessions():
    sessions = await get_all_sessions()
    return {"sessions": sessions}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    results = await get_session_results(session_id)
    return results


@app.get("/api/check-key")
async def check_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    return {"has_key": bool(key), "key_preview": key[:8] + "..." if key else ""}


@app.post("/api/scan")
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())[:8]
    await create_session(session_id, req.topic)
    progress_queues[session_id] = asyncio.Queue()
    session_tasks[session_id] = True

    background_tasks.add_task(run_scan_pipeline, session_id, req.topic, req.custom_keywords)
    return {"session_id": session_id, "message": "스캔 시작됨"}


@app.get("/api/scan/{session_id}/stream")
async def stream_progress(session_id: str):
    """SSE 스트리밍 엔드포인트"""
    async def event_generator():
        queue = progress_queues.get(session_id)
        if not queue:
            # 세션이 없으면 기존 결과 반환
            yield f"data: {json.dumps({'type': 'error', 'message': '세션을 찾을 수 없습니다'})}\n\n"
            return

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=60)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def run_scan_pipeline(session_id: str, topic: str, custom_keywords: Optional[list[str]]):
    """전체 스캔 파이프라인"""
    queue = progress_queues.get(session_id)

    async def push(event_type: str, message: str, data: dict = None):
        if queue:
            payload = {"type": event_type, "message": message, "timestamp": datetime.now().isoformat()}
            if data:
                payload.update(data)
            await queue.put(payload)

    crawler = None
    try:
        # ── 1단계: 키워드 생성 ──
        await push("stage", "🤖 Gemini로 키워드 생성 중...", {"stage": 1})

        if custom_keywords and len(custom_keywords) > 0:
            keywords = custom_keywords
            await push("info", f"✅ 커스텀 키워드 {len(keywords)}개 사용")
        else:
            keywords = await generate_keywords(topic)
            await push("info", f"✅ 키워드 {len(keywords)}개 생성됨")

        await save_keywords(session_id, keywords)
        await push("keywords", "키워드 생성 완료", {"keywords": keywords})

        # ── 2단계: 크롤링 ──
        await push("stage", "🕷️ 웹 크롤링 시작...", {"stage": 2})

        crawler = LeakCrawler(session_id=session_id, on_progress=push)
        await crawler.start()

        all_pages = await crawler.crawl_keywords(keywords)
        await push("info", f"✅ 총 {len(all_pages)}개 페이지 수집 완료")

        # ── 3단계: DB 저장 ──
        await push("stage", "💾 데이터베이스 저장 중...", {"stage": 3})

        page_records = []
        for page in all_pages:
            page_id = await save_page(
                session_id=session_id,
                url=page["url"],
                keyword=page["keyword"],
                title=page["title"],
                text=page["text"],
                links=len(page.get("links", [])),
                depth=page.get("depth", 0)
            )
            page_records.append((page_id, page))
            await push("save", f"💾 저장됨: {page['title'][:40]}")

        # ── 4단계: Gemini 미디어 분석 (일괄) ──
        await push("stage", "🔬 Gemini 미디어 분석 중...", {"stage": 4})

        # 수집된 모든 페이지 텍스트 표시
        for page_id, page in page_records:
            text_preview = page.get("text", "") #[:300].replace("\n", " ")
            await push("page_content", f"📄 {page['title'][:40]} - {text_preview[:100]}...", {
                "url": page["url"],
                "title": page["title"],
                "text_preview": text_preview#[:500]
            })

        # 배치 분석 (1회 API 호출)
        await push("analyze", f"🔍 전체 {len(all_pages)}개 페이지 분석 중...")
        
        batch_result = await analyze_pages_batch(all_pages)
        
        media_count = 0
        
        for result in batch_result.get("results", []):
            if result.get("risk_level") != "NONE":
                # URL로 page_id 찾기
                result_url = result.get("url", "")
                found_page_id = None
                for pid, p in page_records:
                    if p.get("url") == result_url:
                        found_page_id = pid
                        break
                
                if found_page_id is None:
                    found_page_id = page_records[0][0] if page_records else 0
                    
                await save_leak_result(
                    session_id=session_id,
                    page_id=found_page_id,
                    url=result.get("url", ""),
                    risk_level=result.get("risk_level", "NONE"),
                    risk_score=float(result.get("risk_score", 0.0)),
                    leak_types=result.get("leak_types", []),
                    summary=result.get("summary", "")
                )
                media_count += 1
                await push("leak_found", f"⚠️ 유출 감지: {result['risk_level']} - {result['url'][:50]}", {
                    "leak": result
                })

        # ── 완료 ──
        await finish_session(session_id)
        final_results = await get_session_results(session_id)

        await push("done", f"✅ 스캔 완료! {len(all_pages)}개 페이지 분석, {media_count}개 유출 발견", {
            "summary": {
                "total_pages": len(all_pages),
                "total_leaks": media_count,
                "session_id": session_id
            },
            "results": final_results
        })

    except Exception as e:
        await push("error", f"❌ 오류 발생: {str(e)}")
        await finish_session(session_id)

    finally:
        if crawler:
            await crawler.stop()
        session_tasks.pop(session_id, None)


@app.delete("/api/scan/{session_id}/stop")
async def stop_scan(session_id: str):
    session_tasks[session_id] = False
    return {"message": "중지 요청됨"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

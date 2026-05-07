# -*- coding: utf-8 -*-
import asyncio
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/progress")
async def sse_progress(request: Request):
    from ..model_manager import _progress_mgr

    async def event_stream():
        start_time = time.time()
        while True:
            if time.time() - start_time > 600:
                break
            if await request.is_disconnected():
                break
            html = _progress_mgr.get_progress_html()
            if html:
                yield f"event: progress\ndata: {html}\n\n"
            if _progress_mgr._is_complete:
                yield "event: complete\ndata: done\n\n"
                await asyncio.sleep(1)
                _progress_mgr.reset()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/status")
async def sse_status(request: Request):
    from ..model_manager import _gen_tracker

    async def event_stream():
        start_time = time.time()
        while True:
            if time.time() - start_time > 600:
                break
            if await request.is_disconnected():
                break
            import sys
            _mm = sys.modules.get("integrated_app.model_manager")
            status_text = _gen_tracker.status_text()
            eng = (_mm.current_engine if _mm else None) or "none"
            mtype = (_mm.current_type if _mm else None) or "none"
            msize = (_mm.current_size if _mm else None) or "none"
            data = json.dumps({
                "status_text": status_text,
                "engine": eng,
                "model_type": mtype,
                "model_size": msize,
            }, ensure_ascii=False)
            yield f"event: status\ndata: {data}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/engine_switch")
async def sse_engine_switch(request: Request):
    async def event_stream():
        start_time = time.time()
        while True:
            if time.time() - start_time > 300:
                break
            if await request.is_disconnected():
                break
            switch_state = getattr(request.app.state, "engine_switch_state", None)
            if switch_state is None:
                data = json.dumps({
                    "active": False,
                    "step": "",
                    "status": "idle",
                    "engine": "",
                    "model_size": "VoxCPM2",
                }, ensure_ascii=False)
                yield f"event: engine_switch\ndata: {data}\n\n"
                await asyncio.sleep(2)
                continue
            step = switch_state.get("step", "")
            status = switch_state.get("status", "in_progress")
            error = switch_state.get("error", None)
            engine = switch_state.get("engine", "")
            model_size = switch_state.get("model_size", "VoxCPM2")
            data = json.dumps({
                "active": True,
                "step": step,
                "status": status,
                "error": error,
                "engine": engine,
                "model_size": model_size,
            }, ensure_ascii=False)
            yield f"event: engine_switch\ndata: {data}\n\n"
            if status in ("completed", "failed"):
                if hasattr(request.app.state, "engine_switch_state"):
                    del request.app.state.engine_switch_state
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/cancel")
async def sse_cancel(request: Request):
    """SSE endpoint to broadcast cancel confirmation events."""
    from ..model_manager import _progress_mgr

    async def event_stream():
        start_time = time.time()
        while True:
            if time.time() - start_time > 600:
                break
            if await request.is_disconnected():
                break
            if _progress_mgr.is_cancelled():
                data = json.dumps({
                    "status": "cancelled",
                    "message": "\u751f\u6210\u5df2\u53d6\u6d88",
                }, ensure_ascii=False)
                yield f"event: cancelled\ndata: {data}\n\n"
                await asyncio.sleep(1)
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/time_estimate")
async def sse_time_estimate(request: Request):
    """SSE endpoint that broadcasts estimated remaining generation time."""
    from ..model_manager import _time_estimator, _gen_tracker

    async def event_stream():
        start_time = time.time()
        gen_start_time = None
        last_depth = 0
        while True:
            if time.time() - start_time > 600:
                break
            if await request.is_disconnected():
                break

            current_depth = _gen_tracker.queue_depth
            if current_depth > 0:
                if last_depth == 0:
                    gen_start_time = time.time()
                remaining = _gen_tracker.estimate_wait()
                elapsed = time.time() - gen_start_time if gen_start_time else 0
                est_text = _format_time_estimate(remaining)
                data = json.dumps({
                    "status": "generating",
                    "elapsed": round(elapsed, 1),
                    "remaining": round(remaining, 1),
                    "total_est": round(remaining + elapsed, 1),
                    "text": est_text,
                }, ensure_ascii=False)
                yield f"event: time_estimate\ndata: {data}\n\n"
            else:
                if last_depth > 0 and gen_start_time:
                    actual = time.time() - gen_start_time
                    data = json.dumps({
                        "status": "complete",
                        "actual": round(actual, 1),
                        "text": "\u751f\u6210\u5b8c\u6210",
                    }, ensure_ascii=False)
                    yield f"event: time_estimate\ndata: {data}\n\n"
                    gen_start_time = None
                else:
                    data = json.dumps({"status": "idle", "text": _gen_tracker.status_text()}, ensure_ascii=False)
                    yield f"event: time_estimate\ndata: {data}\n\n"

            last_depth = current_depth
            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _format_time_estimate(seconds: float) -> str:
    """Format seconds into human-readable time estimate."""
    if seconds < 10:
        return "\u51e0\u79d2\u540e\u5b8c\u6210"
    elif seconds < 60:
        return f"\u7ea6 {int(seconds)} \u79d2"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"\u7ea6 {mins} \u5206 {secs} \u79d2"


@router.get("/streaming_generate")
async def sse_streaming_generate(request: Request):
    """SSE endpoint for streaming audio generation."""
    from ..model_manager import voxcpm_model, _progress_mgr
    
    async def event_stream():
        if voxcpm_model is None:
            yield "event: error\ndata: {\"error\": \"Model not loaded\"}\n\n"
            return
        
        start_time = time.time()
        while True:
            if time.time() - start_time > 600:
                break
            if await request.is_disconnected():
                break
            html = _progress_mgr.get_progress_html()
            if html:
                yield f"event: progress\ndata: {html}\n\n"
            if _progress_mgr._is_complete:
                yield "event: complete\ndata: done\n\n"
                await asyncio.sleep(1)
                _progress_mgr.reset()
                break
            await asyncio.sleep(0.5)
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

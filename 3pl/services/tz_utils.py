"""KST 타임존 유틸리티 — 3PL PackFlow.

모든 날짜/시간은 Asia/Seoul(KST) 기준.
서버 타임존과 무관하게 일관된 시간 처리.
"""
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst():
    """현재 KST 시각 (timezone-aware)."""
    return datetime.now(KST)


def today_kst():
    """오늘 날짜 문자열 (YYYY-MM-DD)."""
    return now_kst().strftime('%Y-%m-%d')


def days_ago_kst(days):
    """N일 전 날짜 문자열 (YYYY-MM-DD)."""
    return (now_kst() - timedelta(days=days)).strftime('%Y-%m-%d')


def to_kst(dt):
    """naive/UTC datetime → KST 변환."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # naive datetime은 UTC로 가정
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def format_kst(dt, fmt='%Y-%m-%d %H:%M'):
    """datetime을 KST 문자열로 포맷."""
    if dt is None:
        return ''
    if isinstance(dt, str):
        return dt  # 이미 문자열이면 그대로
    return to_kst(dt).strftime(fmt)

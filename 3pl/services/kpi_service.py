"""
kpi_service.py — 작업자/모드별 KPI 집계.

worker_activity_log + orders 기반 실시간 성과 지표.
"""
from datetime import datetime, timezone, timedelta


def get_worker_kpi(supabase, user_id, date_str=None, operator_id=None):
    """특정 작업자의 당일 KPI.

    Returns:
        dict: completed, uph, avg_time_sec, errors, active_hours
    """
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    day_start = f"{date_str}T00:00:00+00:00"
    day_end = f"{date_str}T23:59:59+00:00"

    q = supabase.table('worker_activity_log') \
        .select('*') \
        .eq('user_id', user_id) \
        .gte('created_at', day_start) \
        .lte('created_at', day_end)
    if operator_id:
        q = q.eq('operator_id', operator_id)
    result = q.execute()
    logs = result.data or []

    completed = len([l for l in logs if l.get('completed_at')])
    total_items = sum(l.get('item_count', 0) for l in logs)

    # 활성 시간 계산
    if logs:
        times = [l.get('completed_at') or l.get('created_at') for l in logs]
        starts = [l.get('started_at') or l.get('created_at') for l in logs]
        try:
            first = min(starts)
            last = max(times)
            first_dt = datetime.fromisoformat(first.replace('Z', '+00:00'))
            last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
            active_seconds = (last_dt - first_dt).total_seconds()
            active_hours = max(active_seconds / 3600, 0.01)
        except Exception:
            active_hours = 1.0
    else:
        active_hours = 0

    uph = round(completed / active_hours) if active_hours > 0 else 0

    # 평균 처리시간
    durations = []
    for l in logs:
        s = l.get('started_at')
        e = l.get('completed_at')
        if s and e:
            try:
                sd = datetime.fromisoformat(s.replace('Z', '+00:00'))
                ed = datetime.fromisoformat(e.replace('Z', '+00:00'))
                durations.append((ed - sd).total_seconds())
            except Exception:
                pass
    avg_time = round(sum(durations) / len(durations), 1) if durations else 0

    return {
        'user_id': user_id,
        'date': date_str,
        'completed': completed,
        'total_items': total_items,
        'uph': uph,
        'avg_time_sec': avg_time,
        'active_hours': round(active_hours, 2),
    }


def get_team_kpi(supabase, operator_id, date_str=None):
    """팀 전체 KPI (모드별 분리).

    Returns:
        dict: speed, precision, workers, totals
    """
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    day_start = f"{date_str}T00:00:00+00:00"
    day_end = f"{date_str}T23:59:59+00:00"

    result = supabase.table('worker_activity_log') \
        .select('*') \
        .eq('operator_id', operator_id) \
        .gte('created_at', day_start) \
        .lte('created_at', day_end) \
        .execute()
    logs = result.data or []

    speed_logs = [l for l in logs if l.get('fulfillment_mode') == 'speed']
    precision_logs = [l for l in logs if l.get('fulfillment_mode') != 'speed']

    # 작업자별 집계
    workers = {}
    for l in logs:
        uid = l.get('user_id')
        if uid not in workers:
            workers[uid] = {'speed': 0, 'precision': 0, 'total': 0, 'items': 0}
        mode = 'speed' if l.get('fulfillment_mode') == 'speed' else 'precision'
        workers[uid][mode] += 1
        workers[uid]['total'] += 1
        workers[uid]['items'] += l.get('item_count', 0)

    return {
        'date': date_str,
        'speed': {
            'completed': len(speed_logs),
            'items': sum(l.get('item_count', 0) for l in speed_logs),
        },
        'precision': {
            'completed': len(precision_logs),
            'items': sum(l.get('item_count', 0) for l in precision_logs),
        },
        'totals': {
            'completed': len(logs),
            'items': sum(l.get('item_count', 0) for l in logs),
            'workers': len(workers),
        },
        'workers': workers,
    }


def get_billing_queue_status(supabase, operator_id):
    """과금 큐 현황.

    Returns:
        dict: pending, processed, failed counts
    """
    counts = {}
    for status in ('pending', 'processed', 'failed'):
        try:
            result = supabase.table('billing_queue') \
                .select('id', count='exact') \
                .eq('operator_id', operator_id) \
                .eq('status', status) \
                .execute()
            counts[status] = result.count if hasattr(result, 'count') and result.count else len(result.data or [])
        except Exception:
            counts[status] = 0
    return counts

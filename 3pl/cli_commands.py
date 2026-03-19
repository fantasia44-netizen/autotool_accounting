"""Flask CLI 커맨드 — 스케줄 작업용.

사용법:
    flask storage-calc          # 이번 달 모든 고객사 보관비 계산
    flask storage-calc 2026-03  # 특정 월 보관비 계산
    flask storage-calc --force  # 기존 데이터 삭제 후 재계산
"""
import click
from flask.cli import with_appcontext


@click.command('storage-calc')
@click.argument('year_month', required=False)
@click.option('--force', is_flag=True, help='기존 보관비 삭제 후 재계산')
@with_appcontext
def storage_calc_command(year_month, force):
    """모든 활성 고객사의 월별 보관비 일괄 계산."""
    from datetime import datetime, timezone
    from db_utils import get_repo
    from services.client_billing_service import calculate_storage_fee

    if not year_month:
        year_month = datetime.now(timezone.utc).strftime('%Y-%m')

    client_repo = get_repo('client')
    billing_repo = get_repo('client_billing')
    rate_repo = get_repo('client_rate')
    inv_repo = get_repo('inventory')

    clients = client_repo.list_clients() or []
    click.echo(f'[보관비 계산] {year_month} — 대상 고객사 {len(clients)}개')

    success, skip, fail = 0, 0, 0
    for client in clients:
        cid = client['id']
        name = client.get('name', '')
        try:
            result = calculate_storage_fee(
                billing_repo, rate_repo, inv_repo, cid, year_month, force=force)
            status = result.get('status', 'error')
            if status == 'ok':
                click.echo(f'  ✓ {name}: {result.get("temp_qty", {})} × {result.get("days")}일')
                success += 1
            elif status == 'already_calculated':
                click.echo(f'  - {name}: 이미 계산됨 ({result.get("count")}건)')
                skip += 1
            elif status == 'no_rates':
                click.echo(f'  - {name}: 보관비 요금표 없음')
                skip += 1
            else:
                click.echo(f'  ✗ {name}: {result.get("error", "오류")}')
                fail += 1
        except Exception as e:
            click.echo(f'  ✗ {name}: {e}')
            fail += 1

    click.echo(f'\n[완료] 성공: {success}, 스킵: {skip}, 실패: {fail}')


@click.command('process-billing-queue')
@click.option('--limit', default=500, help='한 번에 처리할 최대 건수')
@with_appcontext
def process_billing_queue_command(limit):
    """billing_queue의 pending 이벤트를 배치 처리."""
    from db_utils import get_repo
    from services.client_billing_service import record_outbound_fee
    from flask import g

    repo = get_repo('client')
    supabase = repo.supabase

    # pending 이벤트 조회
    result = supabase.table('billing_queue') \
        .select('*') \
        .eq('status', 'pending') \
        .order('created_at') \
        .limit(limit) \
        .execute()

    events = result.data if result.data else []
    click.echo(f'[과금큐] pending {len(events)}건 처리 시작')

    success, fail = 0, 0
    for event in events:
        eid = event['id']
        try:
            event_data = event.get('event_data', {})
            client_id = event.get('client_id')
            event_type = event.get('event_type', '')

            if event_type == 'outbound':
                order_id = event_data.get('order_id')
                item_count = event_data.get('item_count', 1)
                total_qty = event_data.get('total_qty', 1)

                billing_repo = get_repo('client_billing')
                rate_repo = get_repo('client_rate')
                try:
                    record_outbound_fee(
                        billing_repo, rate_repo, client_id,
                        order_id=order_id,
                        item_count=item_count,
                        total_weight_g=0,
                    )
                except Exception as e:
                    click.echo(f'  과금 기록 실패 (fallback): {e}')

            # 처리 완료 마킹
            supabase.table('billing_queue').update({
                'status': 'processed',
                'processed_at': 'now()',
            }).eq('id', eid).execute()
            success += 1

        except Exception as e:
            # 실패 마킹
            try:
                supabase.table('billing_queue').update({
                    'status': 'failed',
                }).eq('id', eid).execute()
            except Exception:
                pass
            click.echo(f'  ✗ id={eid}: {e}')
            fail += 1

    click.echo(f'[완료] 성공: {success}, 실패: {fail}')


def register_commands(app):
    """Flask 앱에 CLI 커맨드 등록."""
    app.cli.add_command(storage_calc_command)
    app.cli.add_command(process_billing_queue_command)

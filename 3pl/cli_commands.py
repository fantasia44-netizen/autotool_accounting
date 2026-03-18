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


def register_commands(app):
    """Flask 앱에 CLI 커맨드 등록."""
    app.cli.add_command(storage_calc_command)

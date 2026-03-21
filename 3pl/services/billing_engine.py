"""
billing_engine.py — PackFlow 과금 엔진 v2.0
조건별 공식 기반 과금 + 템플릿 시스템 + Speed/Precision 분리.

GPT 리뷰: "누구나 쓰는 시스템"으로 설계
Gemini 리뷰: 단가 이력, 체적중량, 일할 보관비, 에러 방어 반영
"""
import re
import math
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ═══ 안전한 수식 파서 ═══

# 허용 함수
_SAFE_FUNCS = {
    'ceil': math.ceil,
    'floor': math.floor,
    'min': min,
    'max': max,
    'abs': abs,
    'round': round,
}

# 허용 변수 패턴
_VAR_PATTERN = re.compile(r'\{(\w+)\}')


def _safe_eval(expr_str):
    """eval 대신 안전한 수식 평가. 허용: 숫자, 사칙연산, 괄호, 안전함수."""
    # 위험한 패턴 차단
    dangerous = ['import', '__', 'exec', 'eval', 'open', 'os.', 'sys.',
                 'lambda', 'class', 'def ', 'global', 'nonlocal']
    expr_lower = expr_str.lower()
    for d in dangerous:
        if d in expr_lower:
            raise ValueError(f'허용되지 않는 표현: {d}')

    # 허용 문자만 통과: 숫자, 연산자, 괄호, 공백, 점, 콤마, 함수명
    cleaned = re.sub(r'[a-zA-Z_]\w*', lambda m: m.group() if m.group() in _SAFE_FUNCS else f'__ERR_{m.group()}__', expr_str)
    if '__ERR_' in cleaned:
        bad = re.findall(r'__ERR_(\w+)__', cleaned)
        raise ValueError(f'허용되지 않는 식별자: {bad}')

    try:
        return float(eval(expr_str, {"__builtins__": {}}, _SAFE_FUNCS))
    except Exception as e:
        raise ValueError(f'수식 평가 오류: {expr_str} → {e}')


def evaluate_formula(formula_str, context_vars, min_amount=0):
    """공식 문자열을 평가하여 금액 반환.

    Args:
        formula_str: 공식 (예: "{base_amount} + ({item_count} - 1) * 100")
                     None이면 base_amount × qty 기본 계산.
        context_vars: 변수 딕셔너리 {qty, item_count, weight_kg, ...}
        min_amount: 최소 보장 금액 (음수 방지)

    Returns:
        float: 계산된 금액 (min_amount 이상)
    """
    if not formula_str:
        base = float(context_vars.get('base_amount', 0))
        qty = float(context_vars.get('qty', 1))
        return max(base * qty, min_amount)

    # 변수 치환
    expr = formula_str
    for var_name in _VAR_PATTERN.findall(formula_str):
        val = context_vars.get(var_name)
        if val is None:
            logger.warning('과금 변수 누락: %s (formula=%s)', var_name, formula_str)
            val = 0
        expr = expr.replace(f'{{{var_name}}}', str(float(val)))

    try:
        result = _safe_eval(expr)
        return max(result, min_amount)
    except Exception as e:
        logger.error('과금 공식 평가 실패: formula=%s, expr=%s, error=%s',
                     formula_str, expr, e)
        # fallback: base_amount × qty
        base = float(context_vars.get('base_amount', 0))
        qty = float(context_vars.get('qty', 1))
        return max(base * qty, min_amount)


# ═══ 조건 매칭 ═══

def match_conditions(conditions, context):
    """요금 조건(JSONB)과 과금 컨텍스트를 비교.

    Args:
        conditions: dict (client_rates.conditions)
        context: dict (주문/입고 정보)

    Returns:
        bool: 모든 조건 충족 시 True
    """
    if not conditions:
        return True

    for key, expected in conditions.items():
        if expected is None or expected == '':
            continue

        actual = context.get(key)

        # pack_type 매칭
        if key == 'pack_type':
            if actual != expected:
                return False

        # 중량 범위
        elif key == 'weight_min_g':
            weight_g = float(context.get('weight_g', context.get('chargeable_weight_kg', 0) * 1000))
            if weight_g < float(expected):
                return False
        elif key == 'weight_max_g':
            weight_g = float(context.get('weight_g', context.get('chargeable_weight_kg', 0) * 1000))
            if weight_g > float(expected):
                return False

        # 품목수 범위
        elif key == 'item_count_min':
            if int(context.get('item_count', 1)) < int(expected):
                return False
        elif key == 'item_count_max':
            if int(context.get('item_count', 1)) > int(expected):
                return False

        # 보관온도
        elif key == 'storage_temp':
            if actual != expected:
                return False

        # 배송지역
        elif key == 'delivery_region':
            region = context.get('delivery_region', '')
            if expected not in region:
                return False

        # SKU 카테고리
        elif key == 'sku_category':
            if actual != expected:
                return False

        # 시간대
        elif key == 'time_slot':
            if actual != expected:
                return False

        # 이벤트 타입 (반품 등)
        elif key == 'event_type':
            if actual != expected:
                return False

        # 재포장 필요 여부
        elif key == 'cs_requires_repacking':
            if bool(context.get('cs_requires_repacking')) != bool(expected):
                return False

        # override 금액 (특정 SKU 무료 등)
        elif key == 'override_amount':
            pass  # calculate_fee에서 처리

    return True


# ═══ Sanity Check ═══

def sanity_check(context):
    """과금 전 입력값 이상 탐지."""
    warnings = []
    weight = context.get('chargeable_weight_kg', context.get('weight_kg', 0))
    if weight and float(weight) > 100:
        warnings.append(f'비정상 중량: {weight}kg')
    item_count = context.get('item_count', 0)
    if item_count and int(item_count) > 50:
        warnings.append(f'비정상 품목수: {item_count}')
    qty = context.get('qty', 0)
    if qty is not None and float(qty) <= 0:
        warnings.append(f'수량이 0 이하: {qty}')
    if warnings:
        logger.warning('과금 sanity check 경고: %s', warnings)
    return warnings


# ═══ 통합 과금 계산 ═══

def calculate_fees(rates, context, mode='precision'):
    """고객사 요금표와 과금 컨텍스트로 전체 과금 항목 계산.

    Args:
        rates: list of dict (client_rates 목록)
        context: dict (주문/입고/보관 정보)
        mode: 'speed' = 단순 고정가만, 'precision' = 조건별 공식

    Returns:
        list of dict: [{fee_name, category, quantity, unit_price, total_amount,
                        formula_detail, conditions_matched}, ...]
    """
    sanity_check(context)
    today = date.today()
    results = []
    applied_categories = {}  # 스태킹 제어용

    # 우선순위 정렬 (낮은 숫자 = 높은 우선순위)
    sorted_rates = sorted(rates, key=lambda r: r.get('priority', 100))

    for rate in sorted_rates:
        if not rate.get('is_active', True):
            continue

        # 유효기간 체크
        valid_from = rate.get('valid_from')
        valid_to = rate.get('valid_to')
        if valid_from:
            vf = valid_from if isinstance(valid_from, date) else datetime.strptime(str(valid_from)[:10], '%Y-%m-%d').date()
            if today < vf:
                continue
        if valid_to:
            vt = valid_to if isinstance(valid_to, date) else datetime.strptime(str(valid_to)[:10], '%Y-%m-%d').date()
            if today > vt:
                continue

        category = rate.get('category', 'custom')
        conditions = rate.get('conditions') or {}
        formula = rate.get('formula')
        is_stackable = rate.get('is_stackable', True)

        # 스태킹 제어: 같은 카테고리에서 non-stackable이 이미 적용됐으면 스킵
        if category in applied_categories and not applied_categories[category]:
            continue

        # Speed 모드: formula 없는 단순 항목만 처리
        if mode == 'speed' and formula and '{' in formula:
            continue

        # applies_to 체크
        applies_to = rate.get('applies_to', 'all')
        if applies_to != 'all':
            pack_type = context.get('pack_type', 'single')
            if applies_to != pack_type:
                continue

        # 조건 매칭
        if not match_conditions(conditions, context):
            continue

        # override 금액 체크
        if conditions.get('override_amount') is not None:
            override = float(conditions['override_amount'])
            results.append({
                'rate_id': rate.get('id'),
                'fee_name': rate.get('fee_name', ''),
                'category': category,
                'quantity': 1,
                'unit_price': override,
                'total_amount': override,
                'formula_detail': f'override: {override}',
                'conditions_matched': conditions,
            })
            if not is_stackable:
                applied_categories[category] = False
            continue

        # 변수 세팅
        vars_ctx = dict(context)
        vars_ctx['base_amount'] = float(rate.get('amount', 0))
        if 'qty' not in vars_ctx:
            vars_ctx['qty'] = 1

        # 공식 계산
        min_amount = float(rate.get('min_amount', 0))
        total = evaluate_formula(formula, vars_ctx, min_amount)

        if total <= 0:
            continue

        # 수량/단가 분리 (정산서 표시용)
        qty_for_log = float(vars_ctx.get('qty', 1))
        unit_price = total / qty_for_log if qty_for_log > 0 else total

        # 공식 상세 (감사추적)
        formula_detail = ''
        if formula:
            formula_detail = f'{formula} → {total:,.0f}원'
            for vk in ['base_amount', 'qty', 'item_count', 'weight_kg',
                        'chargeable_weight_kg', 'pallet_count', 'days']:
                if vk in vars_ctx:
                    formula_detail += f' [{vk}={vars_ctx[vk]}]'

        results.append({
            'rate_id': rate.get('id'),
            'fee_name': rate.get('fee_name', ''),
            'category': category,
            'quantity': qty_for_log,
            'unit_price': unit_price,
            'total_amount': total,
            'formula_detail': formula_detail,
            'conditions_matched': conditions if conditions else None,
        })

        if not is_stackable:
            applied_categories[category] = False
        else:
            applied_categories[category] = True

    return results


# ═══ 이벤트 기반 과금 헬퍼 ═══

def create_billing_event(billing_repo, client_id, event_type, fees,
                          order_id=None, year_month=None, memo='',
                          dedupe_prefix='', operator_id=None):
    """과금 결과를 billing_logs에 기록.

    Args:
        billing_repo: ClientBillingRepository
        client_id: 고객사 ID
        event_type: 'inbound'/'outbound'/'storage'/'return'/'vas'/'material'
        fees: calculate_fees() 결과 리스트
        order_id: 주문 ID (nullable)
        year_month: 과금 월 (YYYY-MM), None이면 현재월
        memo: 메모
        dedupe_prefix: 중복방지 키 접두사
        operator_id: 운영사 ID

    Returns:
        dict: {logged: N, skipped: N, total_amount: float}
    """
    if not year_month:
        year_month = datetime.now().strftime('%Y-%m')

    logged = 0
    skipped = 0
    total = 0

    for fee in fees:
        dedupe_key = None
        if dedupe_prefix:
            dedupe_key = f"{dedupe_prefix}:{fee['fee_name']}:{fee.get('rate_id', '')}"

        data = {
            'operator_id': operator_id,
            'client_id': client_id,
            'rate_id': fee.get('rate_id'),
            'order_id': order_id,
            'year_month': year_month,
            'fee_name': fee['fee_name'],
            'category': fee['category'],
            'quantity': fee['quantity'],
            'unit_price': fee['unit_price'],
            'total_amount': fee['total_amount'],
            'event_type': event_type,
            'event_status': 'confirmed',
            'formula_detail': fee.get('formula_detail', ''),
            'conditions_matched': fee.get('conditions_matched'),
            'memo': memo,
            'dedupe_key': dedupe_key,
        }

        # 중복 체크
        if dedupe_key:
            try:
                existing = billing_repo.find_by_dedupe_key(client_id, dedupe_key)
                if existing:
                    skipped += 1
                    continue
            except Exception:
                pass

        try:
            billing_repo.log_fee(data)
            logged += 1
            total += fee['total_amount']
        except Exception as e:
            logger.error('과금 기록 실패: client=%s, fee=%s, error=%s',
                         client_id, fee['fee_name'], e)
            skipped += 1

    return {'logged': logged, 'skipped': skipped, 'total_amount': total}


def cancel_billing_event(billing_repo, client_id, dedupe_prefix):
    """이벤트 취소 시 해당 과금 역분개 — Append-only 음수 정정 트랜잭션.

    동일 dedupe_prefix를 가진 기존 과금 로그를 찾아서,
    각각에 대해 음수(-) 금액의 정정(reversal) 레코드를 Insert.
    원본 레코드는 절대 삭제/수정하지 않음 (회계 원칙).

    Returns:
        dict: {'reversed': int, 'skipped': int, 'total_reversed': float}
    """
    logger.info('과금 역분개 시작: client=%s, prefix=%s', client_id, dedupe_prefix)

    # 1) dedupe_prefix로 시작하는 기존 과금 로그 조회
    all_fees = billing_repo.list_fees(client_id, limit=2000)
    target_fees = [
        f for f in all_fees
        if f.get('dedupe_key', '').startswith(dedupe_prefix)
        and not f.get('is_reversal')
    ]

    if not target_fees:
        logger.info('역분개 대상 없음: client=%s, prefix=%s', client_id, dedupe_prefix)
        return {'reversed': 0, 'skipped': 0, 'total_reversed': 0}

    reversed_count = 0
    skipped = 0
    total_reversed = 0.0

    for fee in target_fees:
        reversal_dedupe = f"REV:{fee.get('dedupe_key', '')}"

        # 이미 역분개된 건인지 확인 (멱등성)
        existing = billing_repo.find_by_dedupe_key(client_id, reversal_dedupe)
        if existing:
            skipped += 1
            continue

        original_amount = float(fee.get('total_amount', 0))
        reversal_data = {
            'client_id': client_id,
            'fee_name': f"[역분개] {fee.get('fee_name', '')}",
            'category': fee.get('category', 'custom'),
            'fee_type': 'reversal',
            'unit_price': -float(fee.get('unit_price', 0)),
            'quantity': fee.get('quantity', 1),
            'total_amount': -original_amount,
            'dedupe_key': reversal_dedupe,
            'is_reversal': True,
            'original_fee_id': fee.get('id'),
            'year_month': fee.get('year_month'),
            'description': f"원본 과금 ID {fee.get('id')} 역분개",
        }

        try:
            billing_repo.log_fee(reversal_data)
            reversed_count += 1
            total_reversed += original_amount
        except Exception as e:
            logger.error('역분개 기록 실패: fee_id=%s, error=%s', fee.get('id'), e)
            skipped += 1

    logger.info('과금 역분개 완료: client=%s, reversed=%d, skipped=%d, total=%.0f',
                client_id, reversed_count, skipped, total_reversed)
    return {
        'reversed': reversed_count,
        'skipped': skipped,
        'total_reversed': total_reversed,
    }

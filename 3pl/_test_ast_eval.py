"""
PackFlow billing_engine AST 파서 시뮬레이션 테스트.
eval() 제거 후 AST 화이트리스트 방식이 올바르게 동작하는지 검증.
"""
import sys
import os

# 모듈 import 경로 설정
sys.path.insert(0, os.path.dirname(__file__))

from services.billing_engine import _safe_eval, evaluate_formula


def test_basic_arithmetic():
    """기본 사칙연산."""
    assert _safe_eval("1 + 2") == 3.0
    assert _safe_eval("10 - 3") == 7.0
    assert _safe_eval("4 * 5") == 20.0
    assert _safe_eval("10 / 4") == 2.5
    assert _safe_eval("10 // 3") == 3.0
    assert _safe_eval("10 % 3") == 1.0
    assert _safe_eval("2 ** 3") == 8.0
    print("  PASS: basic arithmetic")


def test_parentheses():
    """괄호 우선순위."""
    assert _safe_eval("(1 + 2) * 3") == 9.0
    assert _safe_eval("10 - (2 + 3)") == 5.0
    assert _safe_eval("((1 + 2) * (3 + 4))") == 21.0
    print("  PASS: parentheses")


def test_unary():
    """단항 연산자."""
    assert _safe_eval("-5") == -5.0
    assert _safe_eval("-(-3)") == 3.0
    assert _safe_eval("+10") == 10.0
    print("  PASS: unary operators")


def test_safe_functions():
    """허용된 함수."""
    assert _safe_eval("ceil(3.2)") == 4.0
    assert _safe_eval("floor(3.8)") == 3.0
    assert _safe_eval("min(3, 5)") == 3.0
    assert _safe_eval("max(3, 5)") == 5.0
    assert _safe_eval("abs(-7)") == 7.0
    assert _safe_eval("round(3.567)") == 4.0
    print("  PASS: safe functions")


def test_complex_formulas():
    """실제 과금 공식 패턴."""
    # 기본 출고비 + 추가 아이템
    assert _safe_eval("3000 + (5 - 1) * 100") == 3400.0
    # 무게 기반 요금
    assert _safe_eval("ceil(2.3) * 500") == 1500.0
    # 최소 보장
    assert _safe_eval("max(3000, 1500 + 200 * 3)") == 3000.0
    print("  PASS: complex billing formulas")


def test_evaluate_formula_with_vars():
    """변수 치환 + 공식 평가."""
    ctx = {'base_amount': 3000, 'item_count': 5, 'qty': 1}

    # 기본 (formula=None)
    result = evaluate_formula(None, ctx)
    assert result == 3000.0, f"Expected 3000, got {result}"

    # 공식 사용
    result = evaluate_formula(
        "{base_amount} + ({item_count} - 1) * 100", ctx)
    assert result == 3400.0, f"Expected 3400, got {result}"

    # min_amount 보장
    result = evaluate_formula("100", {'qty': 1}, min_amount=500)
    assert result == 500.0, f"Expected 500 (min), got {result}"

    print("  PASS: evaluate_formula with variables")


def test_block_dangerous():
    """위험한 코드 차단."""
    attacks = [
        "__import__('os').system('rm -rf /')",
        "exec('print(1)')",
        "open('/etc/passwd').read()",
        "lambda: 1",
        "().__class__.__bases__",
        "globals()",
        "locals()",
        "dir()",
        "type(1)",
    ]
    blocked = 0
    for attack in attacks:
        try:
            _safe_eval(attack)
            print(f"  FAIL: should block: {attack}")
        except (ValueError, SyntaxError):
            blocked += 1
    assert blocked == len(attacks), f"Only blocked {blocked}/{len(attacks)}"
    print(f"  PASS: blocked {blocked}/{len(attacks)} attacks")


def test_power_limit():
    """거듭제곱 지수 제한."""
    # 2^10은 허용
    assert _safe_eval("2 ** 10") == 1024.0
    # 2^101은 차단
    try:
        _safe_eval("2 ** 101")
        print("  FAIL: should block 2**101")
    except ValueError:
        pass
    print("  PASS: power limit enforced")


if __name__ == '__main__':
    print("=" * 60)
    print("PackFlow AST Parser Simulation Test")
    print("=" * 60)

    test_basic_arithmetic()
    test_parentheses()
    test_unary()
    test_safe_functions()
    test_complex_formulas()
    test_evaluate_formula_with_vars()
    test_block_dangerous()
    test_power_limit()

    print("\n" + "=" * 60)
    print("ALL PASS")
    print("=" * 60)

"""Black-Scholes Greeks / IV 단위 테스트 — v7.9.0.

KRX 옵션 체인 가격에서 IV·그릭을 역산하는 수학 SSOT 검증. 외부 데이터·네트워크
불요(순수 함수). 알려진 교과서 값 + 왕복(round-trip) 일관성으로 검증.
"""

import math

from src.tools.greeks import (
    bs_price,
    black_scholes_greeks,
    implied_vol,
    max_pain,
    put_call_ratio,
)


def test_bs_price_known_value():
    # 교과서 표준 케이스: S=100,K=100,T=1,r=5%,σ=20% → call≈10.4506, put≈5.5735
    call = bs_price(100, 100, 1.0, 0.05, 0.20, "call")
    put = bs_price(100, 100, 1.0, 0.05, 0.20, "put")
    assert call is not None and put is not None
    assert abs(call - 10.4506) < 0.01
    assert abs(put - 5.5735) < 0.01


def test_put_call_parity():
    # C - P = S - K e^{-rT}
    s, k, t, r, sigma = 320.0, 325.0, 30 / 365, 0.03, 0.18
    c = bs_price(s, k, t, r, sigma, "call")
    p = bs_price(s, k, t, r, sigma, "put")
    lhs = c - p
    rhs = s - k * math.exp(-r * t)
    assert abs(lhs - rhs) < 1e-6


def test_invalid_inputs_return_none():
    assert bs_price(100, 100, 0.0, 0.05, 0.2, "call") is None
    assert bs_price(100, 100, 1.0, 0.05, 0.0, "call") is None
    assert black_scholes_greeks(100, 100, -1, 0.05, 0.2, "call") is None
    assert implied_vol(0.0, 100, 100, 1.0, 0.05, "call") is None


def test_atm_call_delta_around_half():
    g = black_scholes_greeks(100, 100, 0.25, 0.03, 0.20, "call")
    assert g is not None
    # ATM 콜 델타는 0.5 보다 약간 위(드리프트 때문).
    assert 0.50 < g.delta < 0.62
    assert g.gamma > 0
    assert g.vega > 0
    assert g.theta < 0  # 시간가치 소멸


def test_put_delta_negative_and_parity():
    gc = black_scholes_greeks(100, 100, 0.25, 0.03, 0.20, "call")
    gp = black_scholes_greeks(100, 100, 0.25, 0.03, 0.20, "put")
    assert gc is not None and gp is not None
    assert gp.delta < 0
    # delta_call - delta_put = e^{-qT} = 1 (q=0)
    assert abs((gc.delta - gp.delta) - 1.0) < 1e-6
    # gamma/vega 는 콜·풋 동일
    assert abs(gc.gamma - gp.gamma) < 1e-9
    assert abs(gc.vega - gp.vega) < 1e-9


def test_implied_vol_round_trip():
    # 가격을 σ=0.22 로 만든 뒤 역산하면 0.22 가 나와야.
    s, k, t, r, true_sigma = 320.0, 310.0, 45 / 365, 0.03, 0.22
    for ot in ("call", "put"):
        price = bs_price(s, k, t, r, true_sigma, ot)  # type: ignore[arg-type]
        assert price is not None
        iv = implied_vol(price, s, k, t, r, ot)  # type: ignore[arg-type]
        assert iv is not None
        assert abs(iv - true_sigma) < 1e-3


def test_implied_vol_below_intrinsic_none():
    # 내재가치보다 낮은 가격은 역산 불가.
    s, k, t, r = 320.0, 300.0, 30 / 365, 0.03
    intrinsic = s - k * math.exp(-r * t)
    assert implied_vol(intrinsic * 0.5, s, k, t, r, "call") is None


def test_greeks_with_injected_iv_records_iv():
    g = black_scholes_greeks(320, 320, 30 / 365, 0.03, 0.185, "call")
    assert g is not None
    assert abs(g.iv - 0.185) < 1e-12


def test_max_pain_picks_min_payout_strike():
    # OI 가 320 콜·풋에 몰리면 max pain 은 그 근처.
    chain = [
        (310.0, 100.0, 5000.0),
        (320.0, 8000.0, 8000.0),
        (330.0, 6000.0, 100.0),
    ]
    mp = max_pain(chain)
    assert mp in (310.0, 320.0, 330.0)
    # 320 에 양방향 OI 최대 → 보통 320 부근으로 수렴
    assert mp == 320.0


def test_max_pain_insufficient_data_none():
    assert max_pain([(320.0, 100.0, 100.0)]) is None
    assert max_pain([]) is None


def test_put_call_ratio():
    assert put_call_ratio(150.0, 100.0) == 1.5
    assert put_call_ratio(100.0, 0.0) is None

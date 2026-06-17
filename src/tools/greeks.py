"""Black-Scholes option pricing + Greeks + implied volatility — v7.9.0.

KOSPI200 옵션 체인(KRX MDCSTAT12501)의 *가격* 만으로 내재변동성(IV)과 그릭
(델타/감마/세타/베가/로)을 결정적으로 계산한다. KRX 가 IV·그릭을 공표하지 않아도
프리미엄(종가)에서 역산할 수 있게 해, 장마감 브리핑의 파생 데스크 섹션이 실제 수치를
다룰 수 있게 하는 수학 SSOT.

설계:
- 외부 의존성 0 — ``math`` 만 사용(scipy 미설치 환경 대응, norm CDF/PDF 직접 구현).
- 유럽형 가정(KOSPI200 옵션은 유럽형이라 정확). 배당수익률 q 지원(지수 옵션 q≈0).
- IV 역산은 Newton-Raphson(vega) → 실패 시 bisection 폴백. 비정상 입력은 None.
- 모든 함수는 순수 함수(부수효과 없음) — 단위 테스트 용이.

단위 규약:
- ``sigma`` / ``r`` / ``q`` 는 *소수* (연 20% = 0.20).
- ``t`` 는 *연 단위* 잔존만기 (예: 30일 → 30/365).
- vega 는 변동성 1%p(0.01) 당, theta 는 *하루* 당, rho 는 금리 1%p 당으로 환산해 반환
  (데스크 관용 표기). raw(연/1.0 단위)는 내부 계산용.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

OptionType = Literal["call", "put"]

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    """표준정규 누적분포 N(x). math.erf 기반 (scipy 불요)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """표준정규 확률밀도 n(x)."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(s: float, k: float, t: float, r: float, sigma: float, q: float) -> tuple[float, float]:
    vol_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def bs_price(
    s: float, k: float, t: float, r: float, sigma: float,
    option_type: OptionType, q: float = 0.0,
) -> float | None:
    """Black-Scholes 이론가. 입력이 비정상(만기/변동성 ≤ 0 등)이면 None."""
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0:
        return None
    d1, d2 = _d1_d2(s, k, t, r, sigma, q)
    disc_r = math.exp(-r * t)
    disc_q = math.exp(-q * t)
    if option_type == "call":
        return s * disc_q * _norm_cdf(d1) - k * disc_r * _norm_cdf(d2)
    return k * disc_r * _norm_cdf(-d2) - s * disc_q * _norm_cdf(-d1)


@dataclass(frozen=True)
class Greeks:
    """옵션 1계약의 민감도 지표. 데스크 관용 단위로 환산된 값.

    - delta: 기초자산 1.0 변화당 옵션값 변화 (콜 0~1, 풋 -1~0)
    - gamma: 기초자산 1.0 변화당 delta 변화
    - vega: 변동성 1%p(0.01) 상승당 옵션값 변화
    - theta: 하루 경과당 옵션값 변화(보통 음수 — 시간가치 소멸)
    - rho: 금리 1%p 상승당 옵션값 변화
    - iv: 계산에 쓰인 내재변동성(소수). 외부 주입 IV 면 그대로, 역산이면 역산값.
    """

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    iv: float


def black_scholes_greeks(
    s: float, k: float, t: float, r: float, sigma: float,
    option_type: OptionType, q: float = 0.0,
) -> Greeks | None:
    """주어진 변동성 sigma 로 그릭 계산. 비정상 입력이면 None.

    vega/theta/rho 는 데스크 관용 단위(1%p / 1일 / 1%p)로 환산해 반환.
    """
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0:
        return None
    d1, d2 = _d1_d2(s, k, t, r, sigma, q)
    disc_r = math.exp(-r * t)
    disc_q = math.exp(-q * t)
    pdf_d1 = _norm_pdf(d1)
    sqrt_t = math.sqrt(t)

    gamma = (disc_q * pdf_d1) / (s * sigma * sqrt_t)
    vega_raw = s * disc_q * pdf_d1 * sqrt_t  # per 1.0 vol
    # theta (연 단위). 공통항 + 금리·배당 항.
    common = -(s * disc_q * pdf_d1 * sigma) / (2.0 * sqrt_t)
    if option_type == "call":
        delta = disc_q * _norm_cdf(d1)
        theta_year = (
            common
            - r * k * disc_r * _norm_cdf(d2)
            + q * s * disc_q * _norm_cdf(d1)
        )
        rho_raw = k * t * disc_r * _norm_cdf(d2)
    else:
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta_year = (
            common
            + r * k * disc_r * _norm_cdf(-d2)
            - q * s * disc_q * _norm_cdf(-d1)
        )
        rho_raw = -k * t * disc_r * _norm_cdf(-d2)

    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=vega_raw / 100.0,       # per 1%p
        theta=theta_year / 365.0,    # per day
        rho=rho_raw / 100.0,         # per 1%p
        iv=sigma,
    )


def implied_vol(
    price: float, s: float, k: float, t: float, r: float,
    option_type: OptionType, q: float = 0.0,
) -> float | None:
    """옵션 시장가(프리미엄)에서 내재변동성 역산.

    Newton-Raphson(vega) 우선, 발산·범위이탈 시 bisection 폴백. 역산 불가
    (가격이 내재가치 미만 / 만기 0 / 무수렴)면 None.
    """
    if price is None or price <= 0 or s <= 0 or k <= 0 or t <= 0:
        return None
    # 차익거래 하한(내재가치) 미만이면 역산 불가.
    disc_r = math.exp(-r * t)
    disc_q = math.exp(-q * t)
    if option_type == "call":
        intrinsic = max(0.0, s * disc_q - k * disc_r)
    else:
        intrinsic = max(0.0, k * disc_r - s * disc_q)
    if price < intrinsic - 1e-6:
        return None

    # Newton-Raphson.
    sigma = 0.30  # 합리적 시작점(연 30%)
    for _ in range(60):
        model = bs_price(s, k, t, r, sigma, option_type, q)
        if model is None:
            break
        d1, _ = _d1_d2(s, k, t, r, sigma, q)
        vega_raw = s * disc_q * _norm_pdf(d1) * math.sqrt(t)
        diff = model - price
        if abs(diff) < 1e-6:
            if 1e-4 < sigma < 5.0:
                return sigma
            break
        if vega_raw < 1e-8:
            break  # vega 소실 → Newton 불안정, bisection 으로
        sigma -= diff / vega_raw
        if sigma <= 1e-4 or sigma > 5.0:
            break

    # Bisection 폴백 (0.1%~500%).
    lo, hi = 1e-4, 5.0
    plo = bs_price(s, k, t, r, lo, option_type, q)
    phi = bs_price(s, k, t, r, hi, option_type, q)
    if plo is None or phi is None:
        return None
    if (plo - price) * (phi - price) > 0:
        return None  # 구간 내 해 없음
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        pmid = bs_price(s, k, t, r, mid, option_type, q)
        if pmid is None:
            return None
        if abs(pmid - price) < 1e-6:
            return mid
        if (plo - price) * (pmid - price) < 0:
            hi = mid
            phi = pmid
        else:
            lo = mid
            plo = pmid
    return 0.5 * (lo + hi)


def max_pain(
    strikes_oi: list[tuple[float, float, float]],
) -> float | None:
    """행사가별 (strike, call_oi, put_oi) 로 최대고통(max pain) 행사가 추정.

    만기에 옵션 매수자 총 손실(=매도자 총 이익)이 최대가 되는 행사가. 만기 부근
    지수를 끌어당기는 '자석' 레벨로 해석. 데이터 없으면 None.
    """
    valid = [(k, c, p) for (k, c, p) in strikes_oi if k and (c or p)]
    if len(valid) < 2:
        return None
    strikes = sorted({k for (k, _, _) in valid})
    best_strike = None
    best_pain = None
    for settle in strikes:
        pain = 0.0
        for (k, c, p) in valid:
            if settle > k:
                pain += (settle - k) * c   # ITM 콜 매수자 이익 = 매도자 손실
            elif settle < k:
                pain += (k - settle) * p   # ITM 풋
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = settle
    return best_strike


def put_call_ratio(total_put: float, total_call: float) -> float | None:
    """풋/콜 비율. 분모 0 이면 None."""
    if not total_call or total_call <= 0:
        return None
    return total_put / total_call

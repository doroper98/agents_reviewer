"""KOSPI200 파생 snapshot 조립 단위 테스트 — v7.9.0.

네트워크 없이 build_snapshot(순수 함수)를 KRX MDCSTAT12501 형태의 합성 rows 로 검증.
옵션 프리미엄을 알려진 IV 로 만들어 IV 역산·그릭·PCR·max pain·key_figures 를 확인.
"""

from datetime import date

from src.tools.greeks import bs_price
from src.tools.derivatives_fetcher import (
    build_snapshot,
    parse_futures,
    parse_option_rows,
    _f,
    _expiry_T,
    _second_thursday,
)


def _fut_rows():
    return [
        {  # 최근월물 (거래량 큼)
            "ISU_NM": "코스피200 F 202607", "TDD_CLSPRC": "352.10",
            "CMPPREVDD_PRC": "-1.40", "ACC_TRDVOL": "120,000",
            "ACC_OPNINT_QTY": "330,000", "SPOT_PRC": "351.20",
        },
        {  # 원월물 (거래량 적음)
            "ISU_NM": "코스피200 F 202609", "TDD_CLSPRC": "353.00",
            "CMPPREVDD_PRC": "-1.20", "ACC_TRDVOL": "300",
            "ACC_OPNINT_QTY": "12,000", "SPOT_PRC": "351.20",
        },
        {  # 스프레드 — 제외돼야
            "ISU_NM": "코스피200 SP 2607-2609", "TDD_CLSPRC": "0.90",
            "CMPPREVDD_PRC": "0.10", "ACC_TRDVOL": "5,000",
            "ACC_OPNINT_QTY": "-", "SPOT_PRC": "351.20",
        },
    ]


def _opt_rows(anchor: date):
    """행사가 345~357.5, 만기 202607, IV 0.18 로 프리미엄 생성."""
    exp = _second_thursday(2026, 7)
    t = (exp - anchor).days / 365.0
    s = 351.20
    r = 0.03
    iv = 0.18
    rows = []
    for strike in [345.0, 347.5, 350.0, 352.5, 355.0, 357.5]:
        for cp, ot in (("C", "call"), ("P", "put")):
            prem = bs_price(s, strike, t, r, iv, ot)  # type: ignore[arg-type]
            rows.append({
                "ISU_NM": f"코스피200 {cp} 202607 {strike}",
                "TDD_CLSPRC": f"{prem:.2f}",
                "ACC_TRDVOL": "5000" if strike == 352.5 else "1500",
                "ACC_OPNINT_QTY": "20000" if strike in (350.0, 355.0) else "8000",
                "SPOT_PRC": f"{s}",
            })
    return rows


def test_float_parser():
    assert _f("1,234.5") == 1234.5
    assert _f("-") is None
    assert _f("") is None
    assert _f("-1.40") == -1.40
    assert _f(None) is None


def test_parse_futures_picks_near_month():
    fq = parse_futures(_fut_rows())
    assert fq is not None
    assert "202607" in fq.name
    assert fq.close == 352.10
    assert fq.oi == 330000
    assert fq.basis is not None and abs(fq.basis - (352.10 - 351.20)) < 1e-6
    assert fq.pct is not None  # change% 계산됨


def test_parse_option_rows():
    anchor = date(2026, 6, 17)
    parsed = parse_option_rows(_opt_rows(anchor))
    assert len(parsed) == 12
    assert all(o["expiry"] == "202607" for o in parsed)
    assert {o["option_type"] for o in parsed} == {"call", "put"}


def test_expiry_T_past_returns_none():
    anchor = date(2026, 8, 1)
    assert _expiry_T("202607", anchor) is None  # 이미 지난 만기
    assert _expiry_T("202609", anchor) is not None


def test_build_snapshot_iv_greeks_roundtrip():
    anchor = date(2026, 6, 17)
    snap = build_snapshot(
        as_of=anchor.isoformat(), anchor=anchor,
        futures_rows=_fut_rows(), option_rows=_opt_rows(anchor),
        vkospi=18.5, risk_free=0.03,
    )
    assert snap.has_data
    assert snap.futures is not None
    assert snap.front_expiry == "202607"
    # IV 역산이 0.18 근처
    ivs = [o.greeks.iv for o in snap.options if o.greeks is not None]
    assert ivs and all(abs(iv - 0.18) < 0.02 for iv in ivs)
    # ATM IV 도 0.18 근처
    assert snap.atm_iv is not None and abs(snap.atm_iv - 0.18) < 0.02
    # PCR 계산됨
    assert snap.pcr_volume is not None
    assert snap.pcr_oi is not None
    # max pain 은 OI 몰린 행사가 근처(350 또는 355)
    assert snap.max_pain in (350.0, 352.5, 355.0)
    # 관심 콜·풋 (OI 상위) 존재 + 그릭 있음
    assert snap.notable_calls and snap.notable_puts
    assert all(o.greeks is not None for o in snap.notable_calls)
    # 콜 델타 양수, 풋 델타 음수
    assert all(o.greeks.delta > 0 for o in snap.notable_calls)
    assert all(o.greeks.delta < 0 for o in snap.notable_puts)


def test_build_snapshot_key_figures_shape():
    anchor = date(2026, 6, 17)
    snap = build_snapshot(
        as_of=anchor.isoformat(), anchor=anchor,
        futures_rows=_fut_rows(), option_rows=_opt_rows(anchor),
        vkospi=18.5,
    )
    kfs = snap.key_figures
    assert kfs and all({"label", "value", "context"} <= set(kf) for kf in kfs)
    labels = " ".join(kf["label"] for kf in kfs)
    assert "선물" in labels
    assert "VKOSPI" in labels
    assert "풋/콜" in labels
    assert "관심" in labels  # 관심 콜/풋 행사가
    # 그릭이 context 에 노출
    joined = " ".join(kf["context"] for kf in kfs)
    assert "델타" in joined and "감마" in joined and "베가" in joined


def test_option_underlying_fallback_to_futures_spot():
    # 옵션 행에 SPOT_PRC 가 없을 때(KRX 실데이터 회귀) 선물 현물가로 폴백해 그릭 산출.
    anchor = date(2026, 6, 17)
    opt_rows = _opt_rows(anchor)
    for r in opt_rows:
        r.pop("SPOT_PRC", None)        # 옵션 행에서 현물가 제거 (VM 실측 상황 재현)
    snap = build_snapshot(
        as_of=anchor.isoformat(), anchor=anchor,
        futures_rows=_fut_rows(), option_rows=opt_rows,  # 선물엔 SPOT_PRC 존재
    )
    # 폴백 덕분에 IV/그릭이 계산됨
    assert snap.atm_iv is not None
    assert snap.notable_calls and all(o.greeks is not None for o in snap.notable_calls)
    assert any("델타" in kf["context"] for kf in snap.key_figures)


def test_build_snapshot_empty_graceful():
    anchor = date(2026, 6, 17)
    snap = build_snapshot(
        as_of=anchor.isoformat(), anchor=anchor,
        futures_rows=[], option_rows=[],
    )
    assert not snap.has_data
    assert snap.key_figures == []
    assert snap.notable_calls == []

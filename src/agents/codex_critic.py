"""V6 Phase V6-1 — Codex 외부 critic CLI 통합 (Tier 0 spike).

REFACTOR_V6_PLAN.md §3 Phase V6-1. 전 V6 루프가 의존하는 *외부 경로* 를 먼저
증명한다. codex CLI (ChatGPT 구독) 를 headless 로 호출해 ComposedReport +
ContextAnalysis 를 사실 검수하고 FactVerdict(JSON) 를 받는다.

설계 원칙 (REFACTOR_V6_PLAN.md §1):
  - 본문은 Claude(Opus) 고정 — codex 는 *검수·지시* 만, 본문 텍스트를 직접 쓰지
    않는다 (AP-V6-1/11). 이 모듈은 verdict(지시서) 만 생산한다.
  - graceful degrade — codex 부재/인증실패/한도/timeout/파싱실패 →
    ``FactVerdict.skip(...)`` → 호출측이 루프를 스킵 → v5.8.8 단일패스 발행
    (AP-V6-12). 어떤 외부 실패도 보고서 발행을 막지 않는다.
  - flag ``V6_CODEX_CRITIC`` default OFF. OFF 면 ``critique()`` 가 즉시 skip
    verdict 를 반환한다 (호출측 byte-equal). Phase 1 단계에선 orchestrator 가
    본 모듈을 *호출하지 않으므로* 호출 경로 자체가 불변 (T-0).
  - 루프 제어는 0 LLM — 본 모듈은 verdict 만 emit 하고, "재작성할까" 판정은
    호출측이 ``FactVerdict.violation_count`` 로 결정 (AP-V6-5, Phase 3).

이 spike 의 목적은 codex 의 *실제 호출 형태* 를 VM 에서 확정하는 것이므로 bin /
subcommand / extra args / model / timeout 을 전부 config 로 override 할 수 있게
열어둔다 (Config.codex_* 필드).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from src.config import Config
from src.models import (
    ComposedReport,
    ContextAnalysis,
    CritiqueClaim,
    FactVerdict,
)

logger = logging.getLogger(__name__)


# codex 에게 주는 검수 지침. JSON 예시의 ``{}`` 와 .format() 충돌을 피하려고
# placeholder 치환은 .replace() 로만 한다 (CLAUDE.md Execution Rule #7).
_CRITIC_INSTRUCTIONS = """You are an external fact critic for a Korean-language analysis report.
The report body was written by Claude (Opus). Your ONLY job is to verify factual
claims against the supplied evidence and flag conflicts. You do NOT rewrite the
body — you only return structured critique that a separate writer (Opus) will act on.

검수 대상 (error_class):
  unsourced_number      출처에 없는 특정 수치를 단정 (confabulation)
  scope_misattribution  진짜 수치를 잘못된 단위/범위에 귀속
  novelty_conflation    출처 작성일(과거)을 "오늘 발표"로 합성
  timepoint_overclaim   시계열/시장 수치에 시점 라벨 없이 과근접 단정
  list_truncation       부분 목록을 전체인 것처럼 단정
  market_data_mismatch  시장 가격이 evidence 의 종가와 불일치/소스 혼합
  stale_sourcing        오래된 뉴스를 현재로 (상대 시점 그대로 베낌)
  event_conflation      별개 행사/사건을 하나로 혼동
  attribution_as_fact   한쪽 주장을 객관 사실로 단정
  causal_overreach      인과 중간단계 생략 + 강도 과장
  metric_label_ambiguity 지표 라벨 모호
  coherence_break       문장 간 논리·맥락 단절. 비유/프레임을 세운 뒤 그 틀과 어긋나는
                        요소를 끼워넣음(예: '세 채널'이라 해놓고 갑자기 '유가 채널'),
                        또는 뜬금없는 개념 도약으로 해석이 어려움
  undefined_reference   서두 정의 없이 'A/B', '전자/후자', 약어를 사용해 독자가 무엇을
                        가리키는지 알 수 없음
  recency_violation     보고서가 발행일(publication_date) 기준 *실시간* 이 아님 — 오래된
                        데이터·뉴스를 현재처럼 제시, '오늘/현재/최근/방금' 이 발행일과
                        불일치, 발행일 이후로 갱신됐어야 할 수치를 옛날 값으로 둠 (최우선)
  duplicate_heading     섹션 제목 또는 핵심 문구가 보고서 내 *여러 곳에서 반복* (동일/유사
                        제목이 다른 섹션에 나란히)

규칙:
  - ★ 실시간성(최우선·엄격): 이 보고서는 publication_date 에 *지금* 발행된다. 모든 시점·
    수치·'오늘/현재/최근' 표현이 publication_date 기준으로 신선한지 *엄격히* 검수하라.
    발행일과 데이터·사건 시점이 어긋나거나, 발행일 이후 갱신됐어야 할 값을 옛날 것으로
    두면 recency_violation(high). 의심되면 웹으로 최신값을 확인하라.
  - ★ 반복 제목/문구(엄격): 같은(또는 거의 같은) 섹션 제목이 여러 섹션에 나오거나 핵심
    문구가 반복되면 duplicate_heading(high). fix_instruction 에 "각 섹션을 내용에 맞는
    *서로 다른* 제목으로 바꿔라(같은 제목 금지)" 처럼 *강한* 교정 지시를 준다.
  - 시장 수치(지수·환율·주가·등락률) 검수 (market_data_mismatch, 최우선):
    · time_series 와 대조하되 *그것만 믿지 말 것* — 헤드라인·요약·표의 지수/환율 종가는
      **웹으로 그 날짜 실제 종가를 직접 확인**하라. 해외 피드(한국 지수 ^KS11 등)는 지연·
      오류로 time_series 자체가 틀릴 수 있어 "일치"만으론 부족. 실제와 다르면 high.
    · 숫자는 prose 에만 있지 않다. 표 카드(fact_grid)·차트 데이터·key_figure 등 *구조화
      필드* 도 검수. 같은 지표가 본문과 표/차트에서 다른 값/다른 날짜면(본문 코스피 7,516
      vs 표 8,864) intra-report 모순 → high.
    · 날짜는 *연도까지* 확인 — 다른 해 같은 월·일(2025-06-18↔2026-06-18)을 올해로 표기 → high.
    · 같은 거래일 한국 지표(코스피·코스닥·삼성·하이닉스·환율) 기준일 불일치(코스피만 직전일)
      → high. 지수 등락 방향과 수급(외국인/개인/기관 순매수·도) 방향 모순도 → high.
  - 사실뿐 아니라 *문장 간 맥락·정합성* 도 본다. 비유·프레임이 무너지거나(coherence_break),
    정의 없이 A/B·약어를 쓰면(undefined_reference) 어디가 어떻게 끊기는지 evidence_conflict
    에 적고, fix_instruction 에 *어떻게 이으면 되는지* 구체 지시를 준다. 본문은 직접 쓰지 말 것.
  - 모든 지적은 어느 evidence/URL 또는 *본문의 어느 부분* 과 충돌하는지 evidence_conflict 에 반드시 명시.
    근거를 못 대는 지적은 아예 내지 말 것 (false-positive 가 멀쩡한 본문을 망친다).
  - evidence 에 부합하면 위반이 아니다. 의심만으로 flag 하지 말 것.
  - fix_instruction 은 Opus 가 수행할 *지시* 만. 본문 문장을 대신 쓰지 말 것.

출력: 아래 JSON 객체 *하나만* 출력. 코드펜스/설명/주석 금지.
{
  "verdict_status": "clean" | "violations",
  "claims": [
    {
      "location": "섹션 heading 또는 'headline'/'deck'/차트 title",
      "error_class": "위 enum 중 하나",
      "quote": "문제가 된 본문/차트 인용구",
      "evidence_conflict": "어느 근거와 어떻게 충돌하는지",
      "source_urls": ["근거 URL(있으면)"],
      "fix_instruction": "Opus 가 수행할 보완 지시",
      "severity": "high" | "medium" | "low"
    }
  ],
  "cited_urls": ["검수에 사용한 전체 URL"]
}
위반이 없으면 {"verdict_status":"clean","claims":[]} 를 출력.
"""

_PROMPT_TEMPLATE = (
    _CRITIC_INSTRUCTIONS
    + "\n\n=== 발행일 (publication_date) ===\n__PUB_DATE__\n"
    + "\n=== 결정적 사전필터가 이미 표시한 의심 (참고, Phase 2) ===\n__PRE_FLAGS__\n"
    + "\n=== 수집된 근거 (ContextAnalysis evidence) ===\n__EVIDENCE_JSON__\n"
    + "\n=== 검수 대상 보고서 (ComposedReport) ===\n__REPORT_JSON__\n"
)


# Phase V6-4 — 차트 미학 검수 (비전). 첨부된 차트 PNG 이미지를 보고 미학·데이터
# 정합을 검수한다. 출력은 동일한 FactVerdict JSON (claims[].location=차트 title).
_VISUAL_INSTRUCTIONS = """You are an external visual desk critic for charts in a Korean analysis report.
첨부된 이미지는 보고서의 *차트 렌더 결과* 다. 각 차트를 보고 미학·데이터 정합 문제를 찾는다.
본문 문체는 보지 않는다. 차트만 본다.

검수 항목 (error_class):
  chart_readability     라벨 겹침/잘림, 글자 너무 작음, 범례 누락으로 판독 불가
  chart_truncation      막대/축/라벨이 카드 밖으로 잘림
  chart_pattern_conflict 패턴·해칭이 충돌해 카테고리 구분 불가
  chart_axis_missing    축/단위/기준선 없음, 0 baseline 누락으로 왜곡
  chart_data_mismatch   차트 숫자가 본문/근거 데이터와 불일치 (data digest 와 대조)
  chart_empty           데이터 0 또는 의미 없는 빈 프레임

규칙:
  - 각 지적은 어느 차트(title)·무엇이 문제인지 명시. 근거 없는 트집 금지.
  - fix_instruction 은 데이터/타입/축 조정 *지시* 만. 직접 그리지 말 것.
  - 미학이 멀쩡하면 위반 아님. 의심만으로 flag 하지 말 것.

출력: 시스템이 지정한 FactVerdict JSON *하나만*. claims[].location = 차트 title.
위반 없으면 {"verdict_status":"clean","claims":[]}.
"""

_VISUAL_PROMPT_TEMPLATE = (
    _VISUAL_INSTRUCTIONS
    + "\n=== 차트 데이터 digest (숫자 대조용) ===\n__CHART_JSON__\n"
    + "\n첨부 이미지가 위 차트들의 렌더 결과다. 이미지를 보고 검수하라.\n"
)


class CodexCritic:
    """codex CLI 를 headless 로 호출하는 외부 fact critic.

    BaseAgent(Claude CLI 전용) 를 상속하지 않는다 — codex 는 다른 CLI(ChatGPT
    구독)이고 verdict 만 생산하기 때문. 호출 형태는 Config.codex_* 로 override.
    """

    def __init__(self, config: Config, *, persona: str | None = None) -> None:
        self.config = config
        # codex 배너에서 실측한 모델명 (바이라인 버전 표기용, Phase V6-7). 하드코딩 금지.
        self._last_codex_model = ""
        # 검수자 페르소나 (도메인 인식 팩트체크 데스크). 빈 문자열이면 기본 지침만
        # = byte-equal. 작성 페르소나가 아님 — codex 는 본문을 안 쓴다 (AP-V6-11).
        self.critic_persona = (
            persona if persona is not None else self._load_persona_from_config()
        )

    def _load_persona_from_config(self) -> str:
        path = (self.config.codex_critic_persona_path or "").strip()
        if not path:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("[codex_critic] persona load fail (%s): %s", path, exc)
            return ""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def critique(
        self,
        report: ComposedReport,
        context: ContextAnalysis,
        *,
        publication_date: str = "",
        pre_flags: list[str] | None = None,
        report_format: str = "",
    ) -> FactVerdict:
        """보고서를 codex 로 사실 검수해 FactVerdict 반환.

        flag OFF / codex 부재 / 외부 실패 시 항상 ``skip`` verdict — 호출측은 이를
        받아 루프를 스킵하고 단일패스로 발행한다 (AP-V6-12).

        v8.2.0 — ``report_format == "reportage"`` 면 프롬프트에 모드 마커를 주입해
        codex 가 르포 전용 표현 등급 검수(사실/추론/가설 라벨 정합)로 전환한다.
        기본값 ``""`` 또는 ``"standard"`` 면 미주입 → 기존 프롬프트 byte-equal.
        """
        if not self.config.enable_codex_critic:
            return FactVerdict.skip("flag_off")

        bin_path = self._resolve_bin()
        if bin_path is None:
            verdict = FactVerdict.skip("codex_not_found")
            self._record_call(verdict, prompt_chars=0)
            logger.warning(
                "[codex_critic] codex CLI not found on PATH (bin=%r) — skipping critic",
                self.config.codex_bin,
            )
            return verdict

        webverify = self.config.enable_codex_webverify
        prompt = self._build_prompt(
            report, context, publication_date=publication_date, pre_flags=pre_flags,
            webverify=webverify, report_format=report_format,
        )

        start = time.time()
        try:
            stdout, stderr, returncode, elapsed_ms = await self._call_codex_cli(
                bin_path, prompt, webverify=webverify,
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() - start) * 1000)
            verdict = FactVerdict.skip("timeout", latency_ms=elapsed_ms)
            self._record_call(verdict, prompt_chars=len(prompt))
            logger.warning(
                "[codex_critic] codex timeout after %ds", self.config.codex_timeout_s,
            )
            return verdict
        except Exception as exc:  # noqa: BLE001 — 외부 의존은 절대 발행을 막지 않음
            elapsed_ms = int((time.time() - start) * 1000)
            verdict = FactVerdict.skip("codex_error", latency_ms=elapsed_ms)
            self._record_call(verdict, prompt_chars=len(prompt))
            logger.warning("[codex_critic] codex invocation failed: %s", exc)
            return verdict

        if returncode != 0:
            reason = self._classify_failure(returncode, stderr)
            verdict = FactVerdict.skip(reason, latency_ms=elapsed_ms)
            self._record_call(verdict, prompt_chars=len(prompt))
            logger.warning(
                "[codex_critic] codex exit=%d (%s): %s",
                returncode, reason, (stderr or "")[:300],
            )
            return verdict

        verdict = self._parse_verdict(stdout, latency_ms=elapsed_ms)
        # 바이라인 버전 표기 (Phase V6-7) — 배너 실측 모델 반영, 없으면 일반 라벨.
        if self._last_codex_model:
            verdict.model_label = f"OpenAI Codex ({self._last_codex_model})"
        self._record_call(verdict, prompt_chars=len(prompt))
        logger.info(
            "[codex_critic] verdict=%s violations=%d (%dms%s)",
            verdict.verdict_status,
            verdict.violation_count,
            verdict.latency_ms,
            ", repaired" if verdict.truncation_repaired else "",
        )
        return verdict

    # ------------------------------------------------------------------
    # Phase V6-4 — 차트 미학 검수 (비전)
    # ------------------------------------------------------------------

    async def critique_visual(
        self, report: ComposedReport, image_paths: list[str],
    ) -> FactVerdict:
        """차트 PNG 이미지를 codex 비전에 넣어 미학·데이터 정합 검수.

        flag OFF / 이미지 없음 / codex 부재 / 실패 시 skip verdict (graceful, log-only).
        결과는 호출측이 *측정* 으로 적립 — 현재 차트 자동수정 안 함 (V5 가드와 병행).
        """
        if not self.config.enable_codex_visual:
            return FactVerdict.skip("flag_off")
        if not image_paths:
            return FactVerdict.skip("no_images")
        bin_path = self._resolve_bin()
        if bin_path is None:
            return FactVerdict.skip("codex_not_found")

        chart_digest = [
            {
                "section": sec.heading,
                "charts": [
                    {"type": c.get("type"), "title": c.get("title"), "data": c.get("data")}
                    for c in sec.charts if isinstance(c, dict)
                ],
            }
            for sec in report.sections if sec.charts
        ]
        prompt = _VISUAL_PROMPT_TEMPLATE.replace(
            "__CHART_JSON__",
            json.dumps(chart_digest, ensure_ascii=False, separators=(",", ":")),
        )
        if self.critic_persona:
            prompt = (
                "=== 검수 관점 (페르소나) ===\n" + self.critic_persona + "\n\n" + prompt
            )

        start = time.time()
        try:
            stdout, stderr, returncode, elapsed_ms = await self._call_codex_cli(
                bin_path, prompt, image_paths=image_paths,
            )
        except asyncio.TimeoutError:
            return FactVerdict.skip("timeout", latency_ms=int((time.time() - start) * 1000))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[codex_critic] visual invocation failed: %s", exc)
            return FactVerdict.skip("codex_error", latency_ms=int((time.time() - start) * 1000))
        if returncode != 0:
            return FactVerdict.skip(
                self._classify_failure(returncode, stderr), latency_ms=elapsed_ms,
            )
        verdict = self._parse_verdict(stdout, latency_ms=elapsed_ms)
        verdict.model_label = "OpenAI Codex (vision)"  # 미학 verdict 명시 (파서 기본 라벨 덮음)
        logger.info(
            "[codex_critic] visual verdict=%s findings=%d (%dms, %d imgs)",
            verdict.verdict_status, verdict.violation_count, verdict.latency_ms,
            len(image_paths),
        )
        return verdict

    async def critique_report_visuals(
        self, report: ComposedReport, html_path: str,
    ) -> FactVerdict:
        """렌더된 HTML 에서 차트 PNG 를 캡처해 미학 검수 (capture → critique_visual).

        Playwright 미설치/캡처 실패 시 graceful skip (AP-V6-12).
        """
        if not self.config.enable_codex_visual:
            return FactVerdict.skip("flag_off")
        try:
            from src.visual.capture import capture_proofs
        except Exception as exc:  # noqa: BLE001
            logger.warning("[codex_critic] capture import failed: %s", exc)
            return FactVerdict.skip("no_capture")
        try:
            captures = capture_proofs(html_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[codex_critic] capture failed: %s", exc)
            return FactVerdict.skip("no_capture")
        charts = [c for c in captures if getattr(c, "role", "") == "chart_closeup"]
        if not charts:
            return FactVerdict.skip("no_images")
        tmpdir = tempfile.mkdtemp(prefix="codex_charts_")
        paths: list[str] = []
        try:
            for i, cap in enumerate(charts):
                p = os.path.join(tmpdir, f"chart_{i:02d}.png")
                with open(p, "wb") as f:
                    f.write(base64.b64decode(cap.image_b64))
                paths.append(p)
            return await self.critique_visual(report, paths)
        finally:
            for p in paths:
                with contextlib.suppress(OSError):
                    os.unlink(p)
            with contextlib.suppress(OSError):
                os.rmdir(tmpdir)

    # ------------------------------------------------------------------
    # CLI 호출
    # ------------------------------------------------------------------

    def _resolve_bin(self) -> str | None:
        return shutil.which(self.config.codex_bin)

    def _build_cmd(
        self, bin_path: str, image_paths: list[str] | None = None,
        webverify: bool = False,
    ) -> list[str]:
        cmd = [bin_path, *self.config.codex_cmd_args]
        if webverify and self.config.codex_websearch_args.strip():
            cmd.extend(self.config.codex_websearch_args.split())  # 웹검색 활성 (Phase V6-5)
        if self.config.codex_model:
            cmd.extend(["-m", self.config.codex_model])
        for img in image_paths or []:
            cmd.extend(["-i", img])  # codex exec --image (Phase V6-4 비전)
        return cmd

    async def _call_codex_cli(
        self, bin_path: str, prompt: str, image_paths: list[str] | None = None,
        webverify: bool = False,
    ) -> tuple[str, str, int, int]:
        """codex 를 subprocess 로 호출. 프롬프트는 stdin 으로 전달.

        Returns ``(stdout, stderr, returncode, elapsed_ms)`` 에서 ``stdout`` 은
        codex 의 *최종 메시지만* (배너/프롬프트 echo/`tokens used` 푸터 없이) —
        ``-o <FILE>`` 로 깨끗이 받는다 (codex-cli 0.136.0 VM spike 에서 stdout 이
        배너+echo+푸터로 오염됨을 확인). 파일이 비면 raw stdout 폴백. timeout 시
        ``asyncio.TimeoutError`` 를 raise (호출측이 skip verdict 로 degrade).
        """
        cmd = self._build_cmd(bin_path, image_paths, webverify)
        fd, msg_path = tempfile.mkstemp(prefix="codex_verdict_", suffix=".txt")
        os.close(fd)
        cmd = [*cmd, "-o", msg_path]
        logger.info(
            "[codex_critic] invoking codex (cmd=%s, prompt=%d chars, timeout=%ds)",
            " ".join(cmd), len(prompt), self.config.codex_timeout_s,
        )
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=self.config.codex_timeout_s,
                )
            except asyncio.TimeoutError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                raise
            elapsed_ms = int((time.time() - start) * 1000)
            # 최종 메시지는 -o 파일에서 (깨끗). 비면 raw stdout 으로 폴백.
            raw_stdout = stdout_b.decode("utf-8", "replace")
            # codex 배너의 "model: gpt-5.5" 실측 (바이라인 버전, Phase V6-7).
            m = re.search(r"(?mi)^\s*model:\s*(\S+)", raw_stdout)
            if m:
                self._last_codex_model = m.group(1).strip()
            message = self._read_text(msg_path)
            stdout = message or raw_stdout.strip()
            stderr = stderr_b.decode("utf-8", "replace").strip()
            return stdout, stderr, proc.returncode or 0, elapsed_ms
        finally:
            with contextlib.suppress(OSError):
                os.unlink(msg_path)

    @staticmethod
    def _read_text(path: str) -> str:
        """파일을 utf-8 로 읽어 strip. 실패/부재 시 빈 문자열 (폴백 트리거)."""
        try:
            with open(path, "rb") as f:
                return f.read().decode("utf-8", "replace").strip()
        except OSError:
            return ""

    @staticmethod
    def _classify_failure(returncode: int, stderr: str) -> str:
        """non-zero exit 의 stderr 로 degrade 사유를 추정 (graceful degrade 분기)."""
        s = (stderr or "").lower()
        if any(k in s for k in ("rate limit", "429", "quota", "too many requests", "usage limit")):
            return "rate_limited"
        if any(
            k in s
            for k in ("unauthorized", "401", "403", "forbidden", "not logged in", "login", "auth")
        ):
            return "auth_failed"
        return "codex_error"

    # ------------------------------------------------------------------
    # 프롬프트 빌드
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        report: ComposedReport,
        context: ContextAnalysis,
        *,
        publication_date: str,
        pre_flags: list[str] | None,
        webverify: bool = False,
        report_format: str = "",
    ) -> str:
        report_json = json.dumps(
            self._report_digest(report), ensure_ascii=False, separators=(",", ":"),
        )
        evidence_json = json.dumps(
            self._evidence_digest(context), ensure_ascii=False, separators=(",", ":"),
        )
        flags_txt = "\n".join(f"- {f}" for f in (pre_flags or [])) or "(없음)"
        prompt = (
            _PROMPT_TEMPLATE
            .replace("__PUB_DATE__", publication_date or context.date or "(미상)")
            .replace("__PRE_FLAGS__", flags_txt)
            .replace("__EVIDENCE_JSON__", evidence_json)
            .replace("__REPORT_JSON__", report_json)
        )
        # V7 Track C — 기준시점 계약 (REFACTOR_V7_PLAN.md §3.4). flag OFF 면 미주입
        # = 기존 프롬프트 byte-equal. "사실로서 정확하지만 보고서 기준 시점과 다른
        # 날짜의 값" 을 wrong_timeframe 으로 분류 — 기존 recency/stale 류(출처 신선도)
        # 와 구분되는 V7 신설 class (사용자 게이트 승인 2026-06-11).
        if getattr(self.config, "enable_ref_frame", False):
            from src.factcheck.reference_frame import build_reference_frame
            frame_json = json.dumps(
                build_reference_frame(context), ensure_ascii=False, separators=(",", ":"),
            )
            prompt += (
                "\n\n=== 기준시점 계약 (V7 reference_frame) ===\n"
                f"{frame_json}\n"
                "추가 error_class: wrong_timeframe — *사실로서는 정확하지만* 이 보고서의 기준\n"
                "시점과 다른 날짜·기간의 값을 현재 값처럼 제시 (예: 발행일 6/5 브리핑에 6/4\n"
                "종가가 가용한데 6/1 종가를 무표기로 인용). 검수 0순위로 본다:\n"
                "- 본문의 각 시장 수치가 위 instruments 의 last_available_date 와 같은 *시점*\n"
                "  의 값인지 확인하라. 숫자가 그 옛 날짜 기준으로 '정확' 해도 면책되지 않는다.\n"
                "- 더 옛 날짜의 값을 쓰려면 본문에 절대 날짜와 그 시점을 쓰는 사유가 명시돼\n"
                "  있어야 한다. 없으면 wrong_timeframe(high).\n"
                "- fix_instruction 엔 last_available_date 의 값으로 교체 + 날짜 명기 지시를 준다.\n"
            )
        # Phase V6-5 — 웹 verify. 근거에 없는 사실은 웹으로 ≤N 대조 + URL 인용 강제 (bound).
        if webverify:
            prompt += (
                f"\n\n=== 웹 verify (V6, bounded ≤{self.config.codex_websearch_cap}회) ===\n"
                "수집된 근거(evidence)에 *없는* 특정 사실(제품명·날짜·수치·인용)은 웹검색으로\n"
                f"최대 {self.config.codex_websearch_cap}회까지 ground truth 와 대조하라.\n"
                "- 웹으로 확인한 지적은 사용한 URL 을 해당 claim 의 source_urls 와 전체 cited_urls 에 명시.\n"
                "- URL 을 댈 수 없으면 그 지적은 내지 마라(근거 없는 지적 금지, AP-V6-8).\n"
                "- 웹으로도 확인 불가면 '허위' 가 아니라 evidence_conflict 에 '근거 부족(웹 미확인)' 으로.\n"
                f"- 검색은 {self.config.codex_websearch_cap}회를 넘기지 마라.\n"
            )
        # v8.2.0 — 르포 모드 마커. 페르소나의 "포맷 적응" 섹션이 표현 등급 검수로
        # 전환하도록 활성화 신호를 준다. report_format != "reportage" 면 미주입 →
        # 기존 프롬프트 byte-equal (AP-V6-3 상속). speculation_as_fact / unsupported_
        # inference 는 페르소나가 정의하는 르포 전용 error_class.
        if report_format == "reportage":
            prompt += (
                "\n\n=== 보고서 포맷 마커 (V8) ===\n"
                "report_format: reportage\n"
                "이 보고서는 르포(탐사보도)다. 페르소나 §\"포맷 적응 — 르포 인지\" 의\n"
                "표현 등급(사실 단정형 / 추론 헤지형 / 가설 명시 라벨) 정합 검수로 전환하라.\n"
                "- 명시 헤지·가설 라벨 안의 추측은 *통과* (false-positive 회피).\n"
                "- 라벨 없는 단정 추측·짜임의 재료 부재·입력 사실 충돌·시점/수치를 추론\n"
                "  톤으로 흐림은 여전히 high. 신규 error_class: speculation_as_fact /\n"
                "  unsupported_inference (둘 다 페르소나 §\"포맷 적응\" 정의).\n"
                "- fix_instruction 은 본문 재작성이 아니라 *표기 교정* (헤지·라벨·짜임\n"
                "  재료 추가·단정 부사 제거) 으로 준다 (AP-V6-11 그대로).\n"
            )
        # 검수자 페르소나가 있으면 *맨 앞* 에 주입 (검수 관점만 — 본문 작성 금지).
        if self.critic_persona:
            prompt = (
                "=== 검수 관점 (페르소나 — 검증 기준이지 작성 지침 아님) ===\n"
                f"{self.critic_persona}\n"
                "위 관점은 *무엇을 사실로 의심할지* 판단에만 쓴다. 문체 평가·본문 작성 금지.\n\n"
                + prompt
            )
        return prompt

    @staticmethod
    def _report_digest(report: ComposedReport) -> dict:
        """검수에 필요한 본문/차트만 추린 사본 (토큰 절약 + 사진/테마 등 무관 필드 제외)."""
        return {
            "headline": report.headline,
            "deck": report.deck,
            "sections": [
                {
                    "heading": s.heading,
                    "prose": s.prose,
                    "charts": [
                        {"type": c.get("type"), "title": c.get("title"), "data": c.get("data")}
                        for c in s.charts
                        if isinstance(c, dict)
                    ],
                    "fact_grid": s.fact_grid,
                }
                for s in report.sections
            ],
            "contradictions": report.contradictions,
            "closing": report.closing,
        }

    @staticmethod
    def _evidence_digest(context: ContextAnalysis) -> dict:
        """ContextAnalysis 에서 사실 검수의 ground truth 가 되는 필드만 추림."""
        return {
            "event_name": context.event_name,
            "date": context.date,
            "summary": context.summary,
            "background": context.background,
            "timeline": context.timeline,
            "key_figures": context.key_figures,
            "sources": context.sources,
            "time_series": context.time_series,
            "provenance": getattr(context, "provenance", []),  # Phase V6-8 — 출처일·단위·URL
        }

    # ------------------------------------------------------------------
    # verdict 파싱 + 절단 복구
    # ------------------------------------------------------------------

    def _parse_verdict(self, raw: str, *, latency_ms: int) -> FactVerdict:
        block = self._extract_json_block(raw)
        repaired = False
        data: dict | None = None
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            fixed = self._repair_truncated_json(block)
            if fixed:
                try:
                    data = json.loads(fixed)
                    repaired = True
                except (json.JSONDecodeError, ValueError):
                    data = None
        if not isinstance(data, dict):
            logger.warning("[codex_critic] verdict JSON parse failed (len=%d)", len(raw))
            return FactVerdict.skip("parse_failed", latency_ms=latency_ms)

        verdict = self._coerce_verdict(data)
        if verdict is None:
            return FactVerdict.skip("parse_failed", latency_ms=latency_ms)
        verdict.latency_ms = latency_ms
        verdict.truncation_repaired = repaired
        if not verdict.model_label:
            verdict.model_label = "OpenAI Codex"
        return verdict

    @staticmethod
    def _coerce_verdict(data: dict) -> FactVerdict | None:
        """dict → FactVerdict. 근거 없는/필드 누락 claim 은 *드롭* (AP-V6-8) 하고
        나머지로 verdict 를 조립. 전체 verdict 가 깨지면 None."""
        raw_claims = data.get("claims") or []
        good: list[CritiqueClaim] = []
        for rc in raw_claims:
            try:
                good.append(CritiqueClaim.model_validate(rc))
            except ValidationError as exc:
                logger.warning(
                    "[codex_critic] dropping ungrounded/invalid claim: %s",
                    str(exc).splitlines()[0] if str(exc) else exc,
                )
        payload = dict(data)
        payload["claims"] = good
        # status 는 _coherent_status validator 가 claims 기준 정규화하므로 제거.
        payload.pop("verdict_status", None)
        # Phase V6-5 — cited_urls 가 비면 claim 의 source_urls 를 집계 (웹verify 추적).
        if not payload.get("cited_urls"):
            seen: list[str] = []
            for c in good:
                for u in c.source_urls:
                    if u and u not in seen:
                        seen.append(u)
            if seen:
                payload["cited_urls"] = seen
        try:
            return FactVerdict.model_validate(payload)
        except ValidationError as exc:
            logger.warning("[codex_critic] verdict assembly failed: %s", exc)
            return None

    @staticmethod
    def _extract_json_block(raw: str) -> str:
        """codex stdout 에서 JSON 블록 추출 — 코드펜스/머리말 잔재 제거.

        BaseAgent._parse_json_response 와 동일 규칙 + 첫 ``{`` 폴백.
        """
        if not raw:
            return ""
        if "```json" in raw:
            return raw.split("```json", 1)[1].split("```", 1)[0].strip()
        if "```" in raw:
            return raw.split("```", 1)[1].split("```", 1)[0].strip()
        start = raw.find("{")
        return raw[start:].strip() if start >= 0 else raw.strip()

    @staticmethod
    def _repair_truncated_json(s: str) -> str | None:
        """절단된 JSON 을 마지막 *완결 경계* 까지 자르고 열린 괄호를 닫는다.

        NarrativeComposer._repair_truncated_json 의 대응물 (REFACTOR_V6_PLAN.md
        §3 Phase V6-1). 쉼표 직전(완결 값 뒤)·``}``/``]`` 직후만 안전 경계로 인정.
        문자열 내부의 괄호·쉼표는 무시 (in_str 추적). 첫 ``{`` 부터 시작.
        """
        if not s:
            return None
        start = s.find("{")
        if start < 0:
            return None
        s = s[start:].rstrip()
        in_str = False
        esc = False
        last_safe: int | None = None
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "}]":
                last_safe = i + 1
            elif ch == ",":
                last_safe = i
        if last_safe is None:
            return None
        head = s[:last_safe]
        stack: list[str] = []
        in_str = False
        esc = False
        for ch in head:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack:
                    stack.pop()
        head = head.rstrip().rstrip(",").rstrip()
        return head + "".join(reversed(stack))

    # ------------------------------------------------------------------
    # 텔레메트리 (T-C3 측정 hook) — usage_log 패턴
    # ------------------------------------------------------------------

    def _record_call(self, verdict: FactVerdict, *, prompt_chars: int) -> None:
        """codex 호출 1건을 JSONL 로 적립 (호출수·latency·degrade 사유).

        파일 IO 실패는 warning 만 — 검수 결과를 막지 않는다 (usage_log 패턴).
        """
        raw = os.environ.get("V6_CODEX_LOG_PATH")
        path = Path(raw) if raw else Path("logs") / "codex_calls.jsonl"
        record = {
            "ts": int(time.time()),
            "verdict_status": verdict.verdict_status,
            "skipped": verdict.skipped,
            "skip_reason": verdict.skip_reason,
            "violations": verdict.violation_count,
            "latency_ms": verdict.latency_ms,
            "truncation_repaired": verdict.truncation_repaired,
            "prompt_chars": prompt_chars,
            "model": self.config.codex_model or "(default)",
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("[codex_critic] telemetry append fail: %s", exc)

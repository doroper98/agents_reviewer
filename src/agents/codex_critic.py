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
import contextlib
import json
import logging
import os
import shutil
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

규칙:
  - 모든 지적은 어느 evidence/URL 과 충돌하는지 evidence_conflict 에 반드시 명시.
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


class CodexCritic:
    """codex CLI 를 headless 로 호출하는 외부 fact critic.

    BaseAgent(Claude CLI 전용) 를 상속하지 않는다 — codex 는 다른 CLI(ChatGPT
    구독)이고 verdict 만 생산하기 때문. 호출 형태는 Config.codex_* 로 override.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

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
    ) -> FactVerdict:
        """보고서를 codex 로 사실 검수해 FactVerdict 반환.

        flag OFF / codex 부재 / 외부 실패 시 항상 ``skip`` verdict — 호출측은 이를
        받아 루프를 스킵하고 단일패스로 발행한다 (AP-V6-12).
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

        prompt = self._build_prompt(
            report, context, publication_date=publication_date, pre_flags=pre_flags,
        )

        start = time.time()
        try:
            stdout, stderr, returncode, elapsed_ms = await self._call_codex_cli(
                bin_path, prompt,
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
    # CLI 호출
    # ------------------------------------------------------------------

    def _resolve_bin(self) -> str | None:
        return shutil.which(self.config.codex_bin)

    def _build_cmd(self, bin_path: str) -> list[str]:
        cmd = [bin_path, *self.config.codex_cmd_args]
        if self.config.codex_model:
            cmd.extend(["-m", self.config.codex_model])
        return cmd

    async def _call_codex_cli(
        self, bin_path: str, prompt: str,
    ) -> tuple[str, str, int, int]:
        """codex 를 subprocess 로 호출. 프롬프트는 stdin 으로 전달.

        Returns ``(stdout, stderr, returncode, elapsed_ms)``. timeout 시
        ``asyncio.TimeoutError`` 를 raise (호출측이 skip verdict 로 degrade).
        """
        cmd = self._build_cmd(bin_path)
        logger.info(
            "[codex_critic] invoking codex (cmd=%s, prompt=%d chars, timeout=%ds)",
            " ".join(cmd), len(prompt), self.config.codex_timeout_s,
        )
        start = time.time()
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
        stdout = stdout_b.decode("utf-8", "replace").strip()
        stderr = stderr_b.decode("utf-8", "replace").strip()
        return stdout, stderr, proc.returncode or 0, elapsed_ms

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
    ) -> str:
        report_json = json.dumps(
            self._report_digest(report), ensure_ascii=False, separators=(",", ":"),
        )
        evidence_json = json.dumps(
            self._evidence_digest(context), ensure_ascii=False, separators=(",", ":"),
        )
        flags_txt = "\n".join(f"- {f}" for f in (pre_flags or [])) or "(없음)"
        return (
            _PROMPT_TEMPLATE
            .replace("__PUB_DATE__", publication_date or context.date or "(미상)")
            .replace("__PRE_FLAGS__", flags_txt)
            .replace("__EVIDENCE_JSON__", evidence_json)
            .replace("__REPORT_JSON__", report_json)
        )

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

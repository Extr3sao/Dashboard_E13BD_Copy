"""
dba_query_explainer.py
======================
Motor DBA que genera explicacions automàtiques de consultes SQL/PL/SQL
associades als checks de l'auditoria Post-CRQ, usant OpenRouter amb
fallback ordenat de 20 models gratuïts.

Fase del pla: §6 Redisseny Skill DBA + §7 Prompt Mestre + §8 Integració OpenRouter

Codificació: UTF-8  (garantia lingüística català)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import textwrap
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

import requests

from src.core.config_loader import ConfigLoader
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now, utc_now_iso

logger = logging.getLogger(__name__)

# ─── Constants de qualitat ───────────────────────────────────────────────────
MIN_RESUM_CHARS = 50
MIN_EXPLICACIO_CHARS = 100
MIN_CONFIANCA = 0.0   # s'accepta qualsevol, però es registra

# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class DBAExplainRequest:
    check_id: str            # 'CHECK_01'
    titol: str               # 'TAULES RECENTS SENSE PRIMARY KEY'
    severitat: str           # 'ALT'
    sql_nou: str             # SQL o PL/SQL complet de la nova versió
    versio_nova: int         # número de versió
    parametres: List[str] = field(default_factory=list)  # ['days_back']
    sql_anterior: Optional[str] = None   # None si és la primera versió
    context_check: str = ""  # descripció breu de la finalitat del check
    tipus: str = "SQL"       # SQL o PLSQL


@dataclass
class DBAExplainResponse:
    check_id: str
    model_utilitzat: str
    resum_executiu: str
    explicacio_funcional: str
    explicacio_tecnica: str
    impacte: str
    riscos: str
    canvis_respecte_anterior: Optional[str]
    recomanacio_revisio: str
    nivell_confianca: float
    advertiments: Optional[str]
    # Blocs llestos per inserir als fitxers derivats
    bloc_auditoria_md: str        # Capçalera del bloc a auditoria_post_crq.md
    linia_consultes_txt: str      # Línia única per a consultes_post_crq.txt
    explicacio_check_text: str    # Explicació completa per al check
    latencia_ms: int = 0
    tokens_entrada: int = 0
    tokens_sortida: int = 0
    explicacio_preview_text: str = ""


# ─── DBAQueryExplainer ───────────────────────────────────────────────────────

class DBAQueryExplainer:
    """
    Agent DBA encarregat de:
    1. Construir un prompt d'alta qualitat per a OpenRouter
    2. Invocar els models gratuïts per ordre de prioritat (fallback automàtic)
    3. Validar la resposta i registrar mètriques
    4. Preparar el contingut llest per a la sincronització de fitxers
    """

    SYSTEM_PROMPT = (
        "Ets un expert DBA Oracle sènior i tècnic de qualitat de codi. "
        "La teva tasca és analitzar una consulta SQL o PL/SQL d'un sistema "
        "d'auditoria de bases de dades Oracle i generar una explicació altament "
        "precisa, estructurada i reutilitzable per a reports tècnics. "
        "La teva resposta HA DE ser un JSON vàlid amb exactament els camps que "
        "s'indiquen. No generis text fora del JSON. Respon sempre en CATALÀ."
    )

    def __init__(self, db_path: Optional[str] = None, config: Optional[ConfigLoader] = None):
        self.db_path = db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
        self.config = config or ConfigLoader()
        self._api_key = (self.config.get_env_var("OPENROUTER_API_KEY", "") or "").strip()
        self._base_url = (
            self.config.get_env_var("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") or
            "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self._timeout = int(self.config.get_env_var("OPENROUTER_TIMEOUT_MS", "60000") or 60000) / 1000

    # ─── API pública ──────────────────────────────────────────────────────────

    def explain(self, req: DBAExplainRequest) -> DBAExplainResponse:
        """
        Genera una explicació completa per a una consulta SQL/PL/SQL.
        Fa fallback automàtic pels 20 models gratuïts prioritzats.
        """
        diff_summary = self._compute_diff(req.sql_anterior, req.sql_nou)
        prompt = self._build_prompt(req, diff_summary)
        models = self._get_active_models()

        last_error: Optional[str] = None
        for model_row in models:
            ordre, model_id = model_row[0], model_row[1]
            t0 = time.time()
            try:
                raw = self._call_openrouter(model_id, prompt)
                latencia_ms = int((time.time() - t0) * 1000)
                parsed = json.loads(raw)

                if not self._validate_response(parsed):
                    self._log_attempt(req.check_id, None, model_id, ordre,
                                      "QUALITAT_INSUFICIENT", latencia_ms=latencia_ms)
                    self._increment_fallback(model_id)
                    continue

                tokens_in = parsed.get("_tokens_entrada", 0)
                tokens_out = parsed.get("_tokens_sortida", 0)
                self._log_attempt(req.check_id, None, model_id, ordre,
                                  "OK", latencia_ms=latencia_ms,
                                  tokens_in=tokens_in, tokens_out=tokens_out)
                self._reset_fallback(model_id)

                response = self._build_response(req, parsed, model_id, latencia_ms,
                                                tokens_in, tokens_out)
                return response

            except (requests.Timeout, requests.ConnectionError) as exc:
                latencia_ms = int((time.time() - t0) * 1000)
                last_error = str(exc)
                self._log_attempt(req.check_id, None, model_id, ordre,
                                  "ERROR", error_codi="TIMEOUT", latencia_ms=latencia_ms)
                self._increment_fallback(model_id)

            except requests.HTTPError as exc:
                latencia_ms = int((time.time() - t0) * 1000)
                error_info = self._parse_openrouter_error(exc.response)
                status_code = str(error_info["status_code"])
                last_error = str(error_info["summary"])
                if self._is_global_free_quota_exhausted(error_info):
                    self._log_attempt(
                        req.check_id,
                        None,
                        model_id,
                        ordre,
                        "ERROR",
                        error_codi="FREE_QUOTA_EXHAUSTED",
                        latencia_ms=latencia_ms,
                    )
                    raise RuntimeError(
                        "Quota diària de models gratuïts d'OpenRouter esgotada. "
                        "Cal esperar al reset diari o afegir saldo al compte."
                    ) from exc
                if exc.response and exc.response.status_code == 429:
                    self._exclude_temporarily(model_id, minutes=5)
                self._log_attempt(req.check_id, None, model_id, ordre,
                                  "ERROR", error_codi=f"HTTP_{status_code}", latencia_ms=latencia_ms)

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                latencia_ms = int((time.time() - t0) * 1000)
                last_error = f"ParseError: {exc}"
                self._log_attempt(req.check_id, None, model_id, ordre,
                                  "ERROR", error_codi="PARSE_ERROR", latencia_ms=latencia_ms)
                self._increment_fallback(model_id)

        raise RuntimeError(
            f"[DBAExplainer] Cap dels {len(models)} models actius ha pogut generar "
            f"una resposta vàlida per a {req.check_id}. Darrer error: {last_error}"
        )

    @staticmethod
    def _parse_openrouter_error(response: Optional[requests.Response]) -> Dict[str, object]:
        status_code = response.status_code if response is not None else "??"
        message = f"HTTP {status_code}"
        body: Dict[str, object] = {}
        if response is not None:
            try:
                body = response.json() or {}
            except ValueError:
                body = {}
            error_payload = body.get("error") if isinstance(body, dict) else None
            if isinstance(error_payload, dict):
                message = str(error_payload.get("message") or message)
        return {
            "status_code": status_code,
            "message": message,
            "body": body,
            "summary": f"HTTP {status_code}: {message}",
        }

    @staticmethod
    def _is_global_free_quota_exhausted(error_info: Dict[str, object]) -> bool:
        if str(error_info.get("status_code")) != "429":
            return False
        body = error_info.get("body")
        if not isinstance(body, dict):
            return False
        error_payload = body.get("error")
        if not isinstance(error_payload, dict):
            return False
        message = str(error_payload.get("message") or "")
        metadata = error_payload.get("metadata") or {}
        headers = metadata.get("headers") if isinstance(metadata, dict) else {}
        remaining = headers.get("X-RateLimit-Remaining") if isinstance(headers, dict) else None
        return "free-models-per-day" in message and str(remaining) == "0"

    # ─── Construcció del prompt ───────────────────────────────────────────────

    def _build_prompt(self, req: DBAExplainRequest, diff_summary: Optional[str]) -> str:
        params_str = ", ".join(req.parametres) if req.parametres else "cap"
        bloc_diff = ""
        if req.sql_anterior and diff_summary:
            bloc_diff = (
                f"\n---\n"
                f"**CONSULTA ANTERIOR (versió {req.versio_nova - 1}):**\n"
                f"```sql\n{req.sql_anterior}\n```\n\n"
                f"**Canvis detectats automàticament:**\n{diff_summary}\n"
            )

        return f"""Analitza la consulta següent que pertany al {req.check_id}: {req.titol}

**Severitat:** {req.severitat}
**Tipus de consulta:** {req.tipus}
**Paràmetres d'entrada:** {params_str}
**Context del check:** {req.context_check or 'Auditoria de qualitat Post-CRQ sobre objectes Oracle modificats recentment.'}

---
**CONSULTA (versió {req.versio_nova}):**
```sql
{req.sql_nou}
```
{bloc_diff}
---

## Objectiu de redacció

Has de generar una explicació de qualitat tècnica pensada per a revisió real de desenvolupament, QA i validació de lots. No facis una fitxa telegràfica ni definicions mínimes. El text ha de ser interpretatiu, prudent i útil per ajudar a decidir si cal intervenir abans del desplegament.

Quan omplis els camps `que_detecta`, `per_que_es_important`, `impacte_sobre_lot`, `com_revisar`, `com_corregir` i `validacio_posterior`, redacta com si després s'haguessin de mostrar exactament amb aquests apartats:
- Què detecta
- Per què és important
- Impacte sobre el lot
- Com revisar
- Com corregir
- Validació posterior

## Instruccions de qualitat i estil

- Respon sempre en català.
- Mantén un to d'informe intern de qualitat tècnica, no comercial.
- No repeteixis literalment el patró amb altres paraules; interpreta què pot indicar dins d'un objecte PL/SQL o SQL real.
- Connecta el patró amb riscos de mantenibilitat, estabilitat, operativa, rendiment, seguretat i diagnosi d'incidències.
- Si el senyal és heurístic o indirecte, fes servir formulacions prudents com `pot indicar`, `acostuma a estar associat a`, `és un senyal de`.
- No inventis exemples concrets de taules, paquets, procediments o dades que no es desprenguin de la consulta o del context.
- A `com_revisar`, explica l'ordre de revisió i què s'ha de prioritzar. No diguis només que cal mirar el codi.
- A `com_corregir`, proposa accions prudents, realistes i orientades a causa arrel. Evita refactoritzacions agressives si no són necessàries.
- A `validacio_posterior`, inclou la reexecució del control i també comprovacions funcionals o tècniques coherents amb el risc detectat.
- `limitacions_o_falsos_positius` ha d'explicar quan el senyal pot no ser concloent o pot requerir revisió contextual.
- `columnes_taula_recomanades` ha de contenir només columnes coherents amb el tipus de check.

## Nivell d'aprofundiment esperat

- `que_detecta`: explica el patró i la fragilitat tècnica o funcional que suggereix.
- `per_que_es_important`: explica per què és rellevant més enllà d'una norma de codi.
- `impacte_sobre_lot`: aterra el risc al context de desplegament, validació i suport posterior.
- `com_revisar`: orienta una revisió manual amb criteri tècnic.
- `com_corregir`: prioritza accions prudents i verificables.
- `validacio_posterior`: combina reexecució del check i verificació posterior.

Genera la teva anàlisi completa i retorna **únicament** el JSON següent sense cap text addicional:

```json
{{
  "resum_executiu": "Màxim 3 frases, orientades a responsable no tècnic.",
  "explicacio_funcional": "Síntesi funcional del control, suficient per entendre què busca i on s'aplica.",
  "explicacio_tecnica": "Anàlisi tècnica de la consulta: catàleg, filtres, joins, funcions, patrons i limitacions observables.",
  "impacte": "Impacte en rendiment, seguretat, estabilitat o qualitat si el check detecta incidències.",
  "riscos": "Riscos si les incidències detectades no es resolen.",
  "canvis_respecte_anterior": "Descripció dels canvis entre la versió anterior i l'actual, o null si és nova.",
  "recomanacio_revisio": "Recomanació concreta per al revisor o DBA.",
  "nivell_confianca": 0.0,
  "advertiments": "Ambigüitats, dubtes tècnics o límits d'interpretació, o null.",
  "que_detecta": "Text desenvolupat i interpretatiu.",
  "per_que_es_important": "Text desenvolupat i interpretatiu.",
  "impacte_sobre_lot": "Text desenvolupat i interpretatiu.",
  "com_revisar": "Text desenvolupat, amb punts només si realment ajuden.",
  "com_corregir": "Text desenvolupat, amb punts només si realment ajuden.",
  "limitacions_o_falsos_positius": "Context on el senyal pot no ser concloent.",
  "columnes_taula_recomanades": ["Lot", "Esquema", "Objecte"],
  "validacio_posterior": "Text desenvolupat i orientat a verificació real.",
  "seccio_auditoria_md": "Comentari de capçalera adaptat al format de auditoria_post_crq.md (sense el SQL).",
  "linia_consultes_txt": "Línia single-line per a consultes_post_crq.txt."
}}
```

**Criteris de qualitat obligatoris:**
- `resum_executiu`: entre 50 i 300 caràcters
- `explicacio_tecnica`: entre 150 i 800 caràcters
- `que_detecta`, `per_que_es_important`, `impacte_sobre_lot`, `com_revisar`, `com_corregir` i `validacio_posterior`: prou desenvolupats per ser útils en una revisió real, no telegràfics
- `nivell_confianca`: valor entre 0.0 i 1.0 (on 1.0 = consulta completament clara)
- Si el SQL és complex o ambigu, posa `nivell_confianca` < 0.7 i explica els dubtes a `advertiments`
- La `linia_consultes_txt` ha de seguir exactament el format: `CHECK_NN | TÍTOL EN MAJÚSCULES | severitat base: VALOR | paràmetres: param1`
- La `seccio_auditoria_md` ha de seguir exactament el format:
  `-- CHECK NN: TÍTOL\n-- Severitat: VALOR\n-- Criteri:\n--   [explicació fins a 3 línies]`

## Requisit de compatibilitat amb fitxers i format

La teva resposta ha d'estar pensada per ser integrada en:
- `auditoria_post_crq.md` (bloc SQL amb capçalera de comentari)
- `consultes_post_crq.txt` (índex de checks)
- explicació del check al report

Per tant:
- usa el to formal i tècnic habitual de la documentació d'auditoria Oracle
- redacta de manera reutilitzable i transformable
- evita formats arbitràriament nous
- indica clarament quin text és resum, quin és detall tècnic i quin és advertiment
"""

    # ????????? Crida a OpenRouter ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????? ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????? ───────────────────────────────────────────────────

    def _call_openrouter(self, model_id: str, user_prompt: str) -> str:
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY no configurat.")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Antigravity",
            "X-Title": "Oracle Audit Dashboard - DBA Explainer",
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    # ─── Validació de la resposta IA ──────────────────────────────────────────

    def _validate_response(self, parsed: dict) -> bool:
        required = [
            "resum_executiu", "explicacio_funcional", "explicacio_tecnica",
            "impacte", "riscos", "recomanacio_revisio", "nivell_confianca",
            "linia_consultes_txt", "seccio_auditoria_md",
        ]
        for key in required:
            if key not in parsed:
                logger.warning("[DBAExplainer] Clau absent en la resposta IA: %s", key)
                return False
        if len(str(parsed.get("resum_executiu", ""))) < MIN_RESUM_CHARS:
            logger.warning("[DBAExplainer] resum_executiu massa curt.")
            return False
        if len(str(parsed.get("explicacio_tecnica", ""))) < MIN_EXPLICACIO_CHARS:
            logger.warning("[DBAExplainer] explicacio_tecnica massa curta.")
            return False
        return True

    # ─── Construcció de la resposta estructurada ──────────────────────────────

    def _build_response(
        self, req: DBAExplainRequest, parsed: dict,
        model_id: str, latencia_ms: int,
        tokens_in: int, tokens_out: int
    ) -> DBAExplainResponse:
        nn = req.check_id.replace("CHECK_", "").lstrip("0") or "0"
        nn_padded = req.check_id.replace("CHECK_", "").zfill(2)
        sql_body = self._strip_existing_check_header(req.sql_nou)

        # Bloc complet per a auditoria_post_crq.md (capçalera + SQL)
        criteri_raw = parsed.get("seccio_auditoria_md") or parsed.get("explicacio_funcional", "")
        criteri_lines = self._format_criteri_lines(criteri_raw)
        separador = "-- " + "=" * 77
        bloc_md = (
            f"```sql\n"
            f"{separador}\n"
            f"-- CHECK {nn_padded}: {req.titol}\n"
            f"-- Severitat: {req.severitat}\n"
            f"-- Criteri:\n"
            f"{criteri_lines}"
            f"{separador}\n"
            f"{sql_body}\n"
            f"```"
        )

        # Línia per a consultes_post_crq.txt
        params_str = ", ".join(req.parametres) if req.parametres else "days_back"
        linia_txt = (
            parsed.get("linia_consultes_txt") or
            f"CHECK_{nn_padded} | {req.titol} | severitat base: {req.severitat} | paràmetres: {params_str}"
        )

        # Explicació completa del check
        explicacio_check = self._build_explanation_catalog_section(req, parsed)

        return DBAExplainResponse(
            check_id=req.check_id,
            model_utilitzat=model_id,
            resum_executiu=str(parsed.get("resum_executiu", "")),
            explicacio_funcional=str(parsed.get("explicacio_funcional", "")),
            explicacio_tecnica=str(parsed.get("explicacio_tecnica", "")),
            impacte=str(parsed.get("impacte", "")),
            riscos=str(parsed.get("riscos", "")),
            canvis_respecte_anterior=parsed.get("canvis_respecte_anterior"),
            recomanacio_revisio=str(parsed.get("recomanacio_revisio", "")),
            nivell_confianca=float(parsed.get("nivell_confianca", 0.0)),
            advertiments=parsed.get("advertiments"),
            bloc_auditoria_md=bloc_md,
            linia_consultes_txt=linia_txt,
            explicacio_check_text=explicacio_check,
            explicacio_preview_text=self._build_preview_explanation_text(req, parsed),
            latencia_ms=latencia_ms,
            tokens_entrada=tokens_in,
            tokens_sortida=tokens_out,
        )

    @staticmethod
    def _strip_existing_check_header(sql_text: str) -> str:
        text = (sql_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```sql\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        header_pattern = re.compile(
            r"^\s*-- =+\s*\n"
            r"-- CHECK[ _]\d+:.*\n"
            r"(?:--.*\n)*?"
            r"-- =+\s*\n?",
            re.IGNORECASE,
        )
        stripped = header_pattern.sub("", text, count=1).strip()
        return stripped or text

    # ─── Diff entre versions ──────────────────────────────────────────────────

    def _compute_diff(self, sql_anterior: Optional[str], sql_nou: str) -> Optional[str]:
        if not sql_anterior:
            return None
        linies_ant = set(sql_anterior.strip().splitlines())
        linies_nou = set(sql_nou.strip().splitlines())
        afegides = linies_nou - linies_ant
        eliminades = linies_ant - linies_nou
        parts = []
        if eliminades:
            parts.append(f"Línies eliminades ({len(eliminades)}): "
                         + "; ".join(list(eliminades)[:3]))
        if afegides:
            parts.append(f"Línies afegides ({len(afegides)}): "
                         + "; ".join(list(afegides)[:3]))
        return ". ".join(parts) if parts else "Canvis menors sense diferències de línies."

    # ─── Helpers de format ────────────────────────────────────────────────────

    @staticmethod
    def _format_criteri_lines(text: str) -> str:
        """Formata fins a 3 línies de comentari SQL de 75 caràcters màxim."""
        # Neteja marques de comentari o capçaleres completes retornades pel model.
        clean = re.sub(r"\*+", "", text or "")
        clean = re.sub(r"^\s*--\s?", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"^\s*CHECK[ _]\d+\s*:.*$", "", clean, flags=re.IGNORECASE | re.MULTILINE)
        clean = re.sub(r"^\s*SEVERITAT\s*:.*$", "", clean, flags=re.IGNORECASE | re.MULTILINE)
        clean = re.sub(r"^\s*CRITERI\s*:?", "", clean, flags=re.IGNORECASE | re.MULTILINE)
        clean = clean.strip()
        lines = textwrap.wrap(clean, width=75)[:3]
        return "\n".join(f"--   {l}" for l in lines) + "\n"

    @staticmethod
    def _normalize_text_block(value: object, fallback: str = "No informat.") -> str:
        text = str(value or "").strip()
        return text or fallback

    @staticmethod
    def _normalize_columns(value: object) -> List[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or ["Lot", "Esquema", "Objecte", "Severitat", "Acció recomanada"]
        text = str(value or "").strip()
        if not text:
            return ["Lot", "Esquema", "Objecte", "Severitat", "Acció recomanada"]
        return [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]

    def _build_explanation_catalog_section(self, req: DBAExplainRequest, parsed: dict) -> str:
        que_detecta = self._normalize_text_block(
            parsed.get("que_detecta"),
            fallback=str(parsed.get("explicacio_funcional") or req.context_check or "No informat."),
        )
        per_que_es_important = self._normalize_text_block(
            parsed.get("per_que_es_important"),
            fallback=str(parsed.get("resum_executiu") or parsed.get("impacte") or "No informat."),
        )
        impacte_sobre_lot = self._normalize_text_block(
            parsed.get("impacte_sobre_lot"),
            fallback=str(parsed.get("impacte") or parsed.get("riscos") or "No informat."),
        )
        com_revisar = self._normalize_text_block(
            parsed.get("com_revisar"),
            fallback=str(parsed.get("recomanacio_revisio") or "No informat."),
        )
        com_corregir = self._normalize_text_block(
            parsed.get("com_corregir"),
            fallback=str(parsed.get("recomanacio_revisio") or "No informat."),
        )
        limitacions = self._normalize_text_block(
            parsed.get("limitacions_o_falsos_positius") or parsed.get("limitacions"),
            fallback=str(parsed.get("advertiments") or "No informat."),
        )
        validacio_posterior = self._normalize_text_block(
            parsed.get("validacio_posterior"),
            fallback="Reexecutar el check i validar que la incidència ha desaparegut sense regressions funcionals.",
        )
        columnes = self._normalize_columns(parsed.get("columnes_taula_recomanades"))
        title = req.titol[:1] + req.titol[1:].lower() if req.titol.isupper() else req.titol

        lines = [
            f"## {req.check_id} — {title}",
            "### Què detecta",
            que_detecta,
            "### Per què és important",
            per_que_es_important,
            "### Impacte sobre el lot",
            impacte_sobre_lot,
            "### Com s'ha de revisar",
            com_revisar,
            "### Com es pot corregir",
            com_corregir,
            "### Limitacions o falsos positius",
            limitacions,
            "### Dades que s'han de mostrar a la taula",
            *[f"- {column}" for column in columnes],
            "### Validació posterior",
            validacio_posterior,
        ]
        return "\n".join(lines).strip()

    # ─── Gestió de models actius ──────────────────────────────────────────────
    def _build_preview_explanation_text(self, req: DBAExplainRequest, parsed: dict) -> str:
        que_detecta = self._normalize_text_block(
            parsed.get("que_detecta"),
            fallback=str(parsed.get("explicacio_funcional") or req.context_check or "No informat."),
        )
        per_que_es_important = self._normalize_text_block(
            parsed.get("per_que_es_important"),
            fallback=str(parsed.get("resum_executiu") or parsed.get("impacte") or "No informat."),
        )
        impacte_sobre_lot = self._normalize_text_block(
            parsed.get("impacte_sobre_lot"),
            fallback=str(parsed.get("impacte") or parsed.get("riscos") or "No informat."),
        )
        com_revisar = self._normalize_text_block(
            parsed.get("com_revisar"),
            fallback=str(parsed.get("recomanacio_revisio") or "No informat."),
        )
        com_corregir = self._normalize_text_block(
            parsed.get("com_corregir"),
            fallback=str(parsed.get("recomanacio_revisio") or "No informat."),
        )
        validacio_posterior = self._normalize_text_block(
            parsed.get("validacio_posterior"),
            fallback="Reexecutar el check i validar que la incidència ha desaparegut sense regressions funcionals.",
        )

        lines = [
            f"{req.check_id} — {req.titol}",
            "",
            f"Què detecta: {que_detecta}",
            "",
            f"Per què és important: {per_que_es_important}",
            "",
            f"Impacte sobre el lot: {impacte_sobre_lot}",
            "",
            "Com revisar:",
            com_revisar,
            "",
            "Com corregir:",
            com_corregir,
            "",
            f"Validació posterior: {validacio_posterior}",
        ]
        return "\n".join(lines).strip()


    def _get_active_models(self) -> List[tuple]:
        """Retorna els models actius i no exclosos temporalment, per ordre de prioritat."""
        ara = utc_now_iso()
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT ordre, model_id FROM model_config
                    WHERE actiu = 1
                      AND (excloses_fins IS NULL OR excloses_fins < ?)
                    ORDER BY ordre ASC
                    """,
                    (ara,),
                ).fetchall()
            return rows
        except sqlite3.OperationalError:
            # Fallback si les taules no estan migrades encara
            return [(1, "meta-llama/llama-3.3-70b-instruct:free")]

    def _increment_fallback(self, model_id: str) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE model_config SET fallbacks_consecutius = fallbacks_consecutius + 1 WHERE model_id = ?",
                    (model_id,),
                )
                row = conn.execute(
                    "SELECT fallbacks_consecutius FROM model_config WHERE model_id = ?",
                    (model_id,),
                ).fetchone()
                if row and row[0] >= 3:
                    exclou = utc_now_iso(utc_now() + timedelta(minutes=30))
                    conn.execute(
                        "UPDATE model_config SET excloses_fins = ? WHERE model_id = ?",
                        (exclou, model_id),
                    )
                conn.commit()
        except sqlite3.OperationalError:
            pass

    def _reset_fallback(self, model_id: str) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE model_config SET fallbacks_consecutius = 0, excloses_fins = NULL WHERE model_id = ?",
                    (model_id,),
                )
                conn.commit()
        except sqlite3.OperationalError:
            pass

    def _exclude_temporarily(self, model_id: str, minutes: int = 5) -> None:
        exclou = utc_now_iso(utc_now() + timedelta(minutes=minutes))
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE model_config SET excloses_fins = ? WHERE model_id = ?",
                    (exclou, model_id),
                )
                conn.commit()
        except sqlite3.OperationalError:
            pass

    def _log_attempt(
        self, check_id: str, version_id: Optional[int],
        model_id: str, ordre: int, resultat: str,
        latencia_ms: int = 0, tokens_in: int = 0,
        tokens_out: int = 0, error_codi: Optional[str] = None,
    ) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO regeneracio_log
                    (check_id, consulta_version_id, model_intentat, model_ordre,
                     resultat, tokens_entrada, tokens_sortida, latencia_ms, error_codi)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (check_id, version_id, model_id, ordre, resultat,
                     tokens_in, tokens_out, latencia_ms, error_codi),
                )
                conn.commit()
        except sqlite3.OperationalError:
            pass

import datetime as dt
import io
import unittest
import zipfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from pypdf import PdfReader

from src.api.automation_analytics_pdf import _generated_at_text
from src.api.main import app
from src.api.report_builder import (
    _generate_ai_text,
    _report_now_text,
    build_post_crq_markdown,
    build_standard_markdown,
)
from src.api.post_crq_audit import _build_post_crq_markdown_from_report_model_final_v7
from src.api.post_crq_experimental_pdf import _deadline_text, _humanize_duration_ms


def _build_multi_lot_experimental_payload():
    return {
        "profile": "E13DB",
        "data": {
            "audit_type": "post_crq",
            "context": {
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "time_filter": {"mode": "preset", "preset": "weekly", "days_back": 7},
                "source_file": "auditoria_post_crq.md",
            },
            "report_model": {
                "execution_parameters": {
                    "profile": "E13DB",
                    "generated_at": "2026-03-08 20:05",
                    "time_window": {"start_at": "2026-03-01T20:05", "end_at": "2026-03-08T20:05"},
                    "time_filter_label": "weekly",
                    "language": "Català",
                    "encoding": "UTF-8",
                    "source_file": "auditoria_post_crq.md",
                    "enabled_checks": [
                        {"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"},
                        {"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"},
                    ],
                    "schemas": ["APP_USER", "APP_AUX"],
                },
                "enabled_checks": [
                    {"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"},
                    {"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"},
                ],
                "lot_summary": [
                    {
                        "lot": "LOT_APP",
                        "critical": 1,
                        "medium": 0,
                        "low": 0,
                        "checks": ["CHECK_03"],
                        "schemas": ["APP_USER"],
                        "affected_objects": 1,
                        "first_action": "Definir CACHE adequat.",
                        "dominant_impact": "Risc de rendiment.",
                        "priority": "Crític",
                    },
                    {
                        "lot": "LOT_AUX",
                        "critical": 0,
                        "medium": 1,
                        "low": 0,
                        "checks": ["CHECK_01"],
                        "schemas": ["APP_AUX"],
                        "affected_objects": 1,
                        "first_action": "Definir PRIMARY KEY.",
                        "dominant_impact": "Risc d'integritat.",
                        "priority": "Mitjà",
                    },
                ],
                "lot_incident_groups": [
                    {
                        "lot": "LOT_APP",
                        "check": "CHECK_03",
                        "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                        "description": "S'ha detectat una seqüència sense cache.",
                        "severity": "Crític",
                        "termini_dies": 0,
                        "impacte": "Pot degradar insercions concurrents.",
                        "accio_recomanada": "Definir CACHE adequat.",
                        "validacio_posterior": "Executar prova d'inserció posterior.",
                        "schemas": [{"nom": "APP_USER", "object_count": 1, "objectes": [{"OBJECTE": "SEQ_ALPHA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE_ACTUAL=0"}]}],
                    },
                    {
                        "lot": "LOT_AUX",
                        "check": "CHECK_01",
                        "title": "TAULES RECENTS SENSE PRIMARY KEY",
                        "description": "S'ha detectat una taula sense PK.",
                        "severity": "Mitjà",
                        "termini_dies": 15,
                        "impacte": "Pot complicar la integritat.",
                        "accio_recomanada": "Definir la PRIMARY KEY.",
                        "validacio_posterior": "Reexecutar el check.",
                        "schemas": [{"nom": "APP_AUX", "object_count": 1, "objectes": [{"OBJECTE": "TMP_BETA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense PK"}]}],
                    },
                ],
                "detail_sections": [
                    {
                        "check_id": "CHECK_03",
                        "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                        "criticality": "Crític",
                        "duration_ms": 1200,
                        "finding_count": 1,
                        "overview": "Detecta seqüències sense cache o amb cache massa baixa.",
                        "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                        "rows": [{"Lot": "LOT_APP", "OBJECTE": "SEQ_ALPHA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE_ACTUAL=0"}],
                    },
                    {
                        "check_id": "CHECK_01",
                        "title": "TAULES RECENTS SENSE PRIMARY KEY",
                        "criticality": "Mitjà",
                        "duration_ms": 900,
                        "finding_count": 1,
                        "overview": "Detecta taules recents sense PK.",
                        "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                        "rows": [{"Lot": "LOT_AUX", "OBJECTE": "TMP_BETA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense PK"}],
                    },
                ],
                "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Aplicar correccions."]},
            },
            "report_options": {"include_annex": True},
        },
    }


def _build_all_checks_post_crq_pdf_payload():
    payload = {
        "profile": "E13DB",
        "format": "pdf",
        "data": {
            "audit_type": "post_crq",
            "context": {
                "profile": "E13DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "time_filter": {
                    "mode": "preset",
                    "preset": "weekly",
                    "days_back": 7,
                    "start_date": "2026-03-09",
                    "end_date": "2026-03-16",
                    "resolved_on": "2026-03-16",
                },
                "source_file": "auditoria_post_crq.md",
                "source_path": "C:/repo/Auditoria_post_crq.md",
            },
            "summary": {
                "selected_checks": 12,
                "executed_checks": 12,
                "checks_with_findings": 12,
                "total_findings": 24,
                "checks_with_errors": 0,
                "findings_by_criticality": {"Crític": 8, "Mitjà": 8, "Baix": 8},
                "latest_change_at": "2026-03-16 10:00",
                "detected_time_range": {"start_at": "2026-03-09 00:00", "end_at": "2026-03-16 10:00"},
            },
            "executed_checks": [],
            "results_by_check": [],
            "report_model": {
                "execution_parameters": {
                    "profile": "E13DB",
                    "generated_at": "2026-03-16 10:05",
                    "time_window": {"start_at": "2026-03-09T00:00", "end_at": "2026-03-16T10:00"},
                    "time_filter_label": "weekly",
                    "language": "Català",
                    "encoding": "UTF-8",
                    "source_file": "auditoria_post_crq.md",
                    "enabled_checks": [],
                    "schemas": ["APP_USER", "APP_AUX"],
                },
                "enabled_checks": [],
                "lot_summary": [
                    {
                        "lot": "LOT_APP",
                        "critical": 4,
                        "medium": 2,
                        "low": 0,
                        "checks": [f"CHECK_{i:02d}" for i in range(1, 7)],
                        "schemas": ["APP_USER"],
                        "affected_objects": 12,
                        "first_action": "Revisar seqüències, índex i taules crítiques.",
                        "dominant_impact": "Impacte combinat sobre rendiment, integritat i estabilitat.",
                        "priority": "Crític",
                    },
                    {
                        "lot": "LOT_AUX",
                        "critical": 0,
                        "medium": 2,
                        "low": 4,
                        "checks": [f"CHECK_{i:02d}" for i in range(7, 13)],
                        "schemas": ["APP_AUX"],
                        "affected_objects": 12,
                        "first_action": "Revisar qualitat estructural i problemes de compilació.",
                        "dominant_impact": "Risc de mantenibilitat i incidències posteriors de suport.",
                        "priority": "Mitjà",
                    },
                ],
                "lot_incident_groups": [],
                "detail_sections": [],
                "final_observations": {
                    "blocking_errors": [],
                    "warnings": ["No s'ha detectat cap bloqueig, però hi ha acumulació de males pràctiques <tag>."],
                    "next_steps": ["Aplicar correccions, validar integritat & reexecutar tots els checks."],
                },
            },
            "report_options": {"include_annex": True},
            "errors": [],
        },
    }

    for index in range(1, 13):
        check_id = f"CHECK_{index:02d}"
        severity = "Crític" if index <= 4 else ("Mitjà" if index <= 8 else "Baix")
        lot = "LOT_APP" if index <= 6 else "LOT_AUX"
        schema = "APP_USER" if index <= 6 else "APP_AUX"
        object_type = "TABLE" if index % 2 else "VIEW"
        title = f"{check_id} — Seqüències, índexs i execució amb accents català/español"
        long_text = (
            f"Descripció extensa del {check_id} amb <LOOP>, <tag>, & i text llarg per validar el saneado. "
            "Inclou seqüències, índex, execució, validació, correcció, integritat i mantenibilitat en català."
        )

        payload["data"]["executed_checks"].append(
            {
                "check_id": check_id,
                "title": title,
                "severitat": severity,
                "criticitat": severity,
                "criticitat_key": severity.upper(),
                "status": "ok",
                "row_count": 2,
                "duration_ms": 900 + index,
            }
        )
        payload["data"]["results_by_check"].append(
            {
                "check_id": check_id,
                "title": title,
                "severitat": severity,
                "criticitat": severity,
                "criticitat_key": severity.upper(),
                "criteri": f"Criteri {check_id} amb </para> i ús real de l'índex.",
                "status": "ok",
                "row_count": 2,
                "duration_ms": 900 + index,
                "columns": ["Lot", "ESQUEMA", "OBJECTE", "DADA"],
                "rows": [
                    {"Lot": lot, "ESQUEMA": schema, "OBJECTE": f"OBJ_{index}_A", "DADA": "Valor <A> & seqüència"},
                    {"Lot": lot, "ESQUEMA": schema, "OBJECTE": f"OBJ_{index}_B", "DADA": "Valor <B> & índex"},
                ],
            }
        )
        payload["data"]["report_model"]["enabled_checks"].append(
            {"check_id": check_id, "title": title, "criticality": severity}
        )
        payload["data"]["report_model"]["execution_parameters"]["enabled_checks"].append(
            {"check_id": check_id, "title": title, "criticality": severity}
        )
        payload["data"]["report_model"]["lot_incident_groups"].append(
            {
                "lot": lot,
                "check": check_id,
                "title": title,
                "description": long_text,
                "severity": severity,
                "termini_dies": 0 if severity == "Crític" else 15,
                "impacte": f"Impacte {check_id} sobre rendiment, integritat & estabilitat amb <if> markup accidental.",
                "accio_recomanada": f"Acció {check_id}: corregir definició, revisar dependències i evitar </para> al text.",
                "validacio_posterior": f"Validació {check_id}: reexecutar, recompilar i revisar logs & mètriques.",
                "schemas": [
                    {
                        "nom": schema,
                        "object_count": 2,
                        "objectes": [
                            {"OBJECTE": f"OBJ_{index}_A", "TIPUS": object_type, "DADA TÈCNICA": "Dada tècnica <1> & prova"},
                            {"OBJECTE": f"OBJ_{index}_B", "TIPUS": object_type, "DADA TÈCNICA": "Dada tècnica <2> & prova"},
                        ],
                    }
                ],
            }
        )
        payload["data"]["report_model"]["detail_sections"].append(
            {
                "check_id": check_id,
                "title": title,
                "criticality": severity,
                "duration_ms": 900 + index,
                "finding_count": 2,
                "overview": f"Overview del {check_id} amb seqüències, índex i execució; inclou <tag> i accents.",
                "why_it_matters": f"El {check_id} pot afectar rendiment, integritat i mantenibilitat & operació.",
                "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                "rows": [
                    {"Lot": lot, "OBJECTE": f"OBJ_{index}_A", "TIPUS": object_type, "DADA TÈCNICA": "Dada tècnica <1> & prova"},
                    {"Lot": lot, "OBJECTE": f"OBJ_{index}_B", "TIPUS": object_type, "DADA TÈCNICA": "Dada tècnica <2> & prova"},
                ],
            }
        )

    return payload


class TestReportGeneration(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generate_markdown_report(self):
        payload = {
            "profile": "E13DB",
            "format": "markdown",
            "data": [
                {
                    "username": "ADSL",
                    "obsolescence_score": 72,
                    "audit_result": "PRECAUCIO",
                    "summary": {
                        "SIZE_GB": 0.01,
                        "INBOUND_REFERENCES": 2,
                        "ACTIVE_JOBS": 0,
                        "APEX_APPLICATIONS": 0,
                        "ENABLED_TRIGGERS": 1,
                    },
                    "score_breakdown": [
                        {"factor": "Activitat", "desc": "Moviments DML detectats"},
                        {"factor": "Aïllament", "desc": "Dependències entrants"},
                    ],
                    "executed_queries": [
                        {"query": "Q01_SUMMARY_360", "status": "ok", "rows": 1},
                        {"query": "Q08_DEPS_INCOMING", "status": "ok", "rows": 2},
                    ],
                }
            ],
        }

        res = self.client.post("/api/report/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/markdown", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_detallat_E13DB", res.headers.get("content-disposition", ""))
        text = res.content.decode("utf-8")
        self.assertIn("Context de l'Auditoria", text)
        self.assertIn("E13DB", text)

    def test_generate_pdf_report(self):
        payload = {
            "profile": "E13DB",
            "format": "pdf",
            "data": [
                {
                    "USERNAME": "ADSL",
                    "SIZE_GB": 0.01,
                    "risc": "PRECAUCIO",
                    "motiu": "Dependències entrants detectades",
                }
            ],
        }

        res = self.client.post("/api/report/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_E13DB", res.headers.get("content-disposition", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_generate_post_crq_markdown_report(self):
        payload = {
            "profile": "E13DB",
            "format": "markdown",
            "data": {
                "audit_type": "post_crq",
                "context": {
                    "profile": "E13DB",
                    "schemas": ["APP_USER"],
                    "time_filter": {
                        "mode": "preset",
                        "preset": "weekly",
                        "days_back": 7,
                        "start_date": "2026-03-02",
                        "end_date": "2026-03-08",
                        "resolved_on": "2026-03-08",
                    },
                    "source_file": "auditoria_post_crq.md",
                    "source_path": "C:/repo/Auditoria_post_crq.md",
                },
                "summary": {
                    "selected_checks": 2,
                    "executed_checks": 2,
                    "checks_with_findings": 2,
                    "total_findings": 3,
                    "checks_with_errors": 0,
                    "findings_by_criticality": {"Crític": 1, "Mitjà": 2, "Baix": 0},
                    "latest_change_at": "2026-03-08 20:04",
                    "detected_time_range": {"start_at": "2026-03-08 19:00", "end_at": "2026-03-08 20:04"},
                },
                "executed_checks": [
                    {
                        "check_id": "CHECK_03",
                        "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                        "severitat": "Crític",
                        "criticitat": "Crític",
                        "criticitat_key": "CRITIC",
                        "status": "ok",
                        "row_count": 1,
                        "duration_ms": 1200,
                    },
                    {
                        "check_id": "CHECK_01",
                        "title": "TAULES RECENTS SENSE PRIMARY KEY",
                        "severitat": "Mitjà",
                        "criticitat": "Mitjà",
                        "criticitat_key": "MITJA",
                        "status": "ok",
                        "row_count": 2,
                        "duration_ms": 900,
                    },
                ],
                "results_by_check": [
                    {
                        "check_id": "CHECK_03",
                        "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                        "severitat": "Crític",
                        "criticitat": "Crític",
                        "criticitat_key": "CRITIC",
                        "criteri": "Seqüències recents sense cache",
                        "status": "ok",
                        "row_count": 1,
                        "duration_ms": 1200,
                        "columns": ["Lot", "ESQUEMA", "SEQUENCIA", "CACHE_ACTUAL", "ESTAT", "ACCIO_RECOMANADA"],
                        "rows": [
                            {"Lot": "LOT_APP", "ESQUEMA": "APP_USER", "SEQUENCIA": "SEQ_ALPHA", "CACHE_ACTUAL": 0, "ESTAT": "NOCACHE", "ACCIO_RECOMANADA": "Definir CACHE adequat"},
                        ],
                    },
                    {
                        "check_id": "CHECK_01",
                        "title": "TAULES RECENTS SENSE PRIMARY KEY",
                        "severitat": "Mitjà",
                        "criticitat": "Mitjà",
                        "criticitat_key": "MITJA",
                        "criteri": "Només taules modificades recentment",
                        "status": "ok",
                        "row_count": 2,
                        "duration_ms": 900,
                        "columns": ["Lot", "ESQUEMA", "TAULA"],
                        "rows": [
                            {"Lot": "LOT_APP", "ESQUEMA": "APP_USER", "TAULA": "TMP_ALPHA"},
                            {"Lot": "LOT_APP", "ESQUEMA": "APP_USER", "TAULA": "TMP_BETA"},
                        ],
                    },
                ],
                "report_model": {
                    "execution_parameters": {
                        "profile": "E13DB",
                        "generated_at": "2026-03-08 20:05",
                        "time_window": {"start_at": "2026-03-01T20:05", "end_at": "2026-03-08T20:05"},
                        "language": "Català",
                        "encoding": "UTF-8",
                        "source_file": "auditoria_post_crq.md",
                        "enabled_checks": [
                            {"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"},
                            {"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"},
                        ],
                        "schemas": ["APP_USER"],
                    },
                    "enabled_checks": [
                        {"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"},
                        {"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"},
                    ],
                    "lot_summary": [
                        {
                            "lot": "LOT_APP",
                            "critical": 1,
                            "medium": 2,
                            "low": 0,
                            "checks": ["CHECK_03", "CHECK_01"],
                            "check_descriptions": [
                                {"check_id": "CHECK_03", "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT"},
                                {"check_id": "CHECK_01", "title": "TAULES RECENTS SENSE PRIMARY KEY"},
                            ],
                            "first_action": "Definir CACHE adequat a les seqüències prioritàries.",
                            "dominant_impact": "Risc de rendiment en insercions concurrents.",
                            "priority": "Crític",
                        }
                    ],
                    "lot_incident_groups": [
                        {
                            "lot": "LOT_APP",
                            "check": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "severity": "Crític",
                            "termini_dies": 0,
                            "impacte": "Pot degradar insercions batch i processos concurrents.",
                            "accio_recomanada": "Definir un valor de CACHE adequat segons l'ús real.",
                            "validacio_posterior": "Executar proves d'inserció i validar el temps de resposta.",
                            "schemas": [
                                {
                                    "nom": "APP_USER",
                                    "object_count": 1,
                                    "objectes": [
                                        {
                                            "nom": "SEQ_ALPHA",
                                            "tipus": "SEQUENCE",
                                            "dada_tecnica": "CACHE_ACTUAL=0",
                                            "accio_recomanada": "Definir CACHE adequat",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "critical_checks_grouped": [
                        {
                            "check_id": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "summary_text": "S'han detectat seqüències amb cache inexistent o insuficient.",
                            "impact_text": "Pot degradar insercions batch i processos concurrents.",
                            "urgency_label": "URGENT",
                            "recommended_action": "Definir un valor de CACHE adequat segons l'ús real.",
                            "review_steps": "Comprovar el valor actual de CACHE i el patró d'ús.",
                            "post_validation": "Executar proves d'inserció i validar el temps de resposta.",
                            "lot_rows": [
                                {
                                    "lot": "LOT_APP",
                                    "esquema": "APP_USER",
                                    "objecte": "SEQ_ALPHA",
                                    "severitat": "Crític",
                                    "dada_tecnica": "CACHE_ACTUAL=0",
                                    "accio_recomanada": "Definir CACHE adequat",
                                }
                            ],
                        }
                    ],
                    "detail_sections": [
                        {
                            "check_id": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "status": "ok",
                            "criticality": "Crític",
                            "overview": "Detecta seqüències sense cache o amb cache massa baixa.",
                            "why_it_matters": "Pot penalitzar processos d'inserció concurrents.",
                            "finding_count": 1,
                            "columns": ["Lot", "ESQUEMA", "SEQUENCIA", "CACHE_ACTUAL", "ESTAT", "ACCIO_RECOMANADA"],
                            "rows": [
                                {"Lot": "LOT_APP", "ESQUEMA": "APP_USER", "SEQUENCIA": "SEQ_ALPHA", "CACHE_ACTUAL": 0, "ESTAT": "NOCACHE", "ACCIO_RECOMANADA": "Definir CACHE adequat"},
                            ],
                        }
                    ],
                    "final_observations": {
                        "blocking_errors": [],
                        "warnings": ["Cap placeholder de responsable visible."],
                        "next_steps": ["Aplicar la correcció al lot prioritari i reexecutar el check."],
                    },
                    "quality_gate": {"status": "ok", "issues": []},
                },
                "report_options": {"include_annex": True},
                "errors": [],
            },
        }

        res = self.client.post("/api/report/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/markdown", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_post_crq_E13DB", res.headers.get("content-disposition", ""))
        text = res.content.decode("utf-8")
        self.assertIn("## 1. Índex", text)
        self.assertIn("## 2. Context de l'auditoria", text)
        self.assertIn("## 3. Resum executiu post-CRQ", text)
        self.assertIn("## 4. Incidències prioritzades per criticitat i lot", text)
        self.assertIn("## 5. Resultat detallat per check", text)
        self.assertIn("## 6. Observacions finals", text)
        self.assertIn("Checks inclosos en l'informe", text)
        self.assertIn("LOT_APP", text)
        self.assertIn("SEQ_ALPHA", text)
        self.assertIn("Annex A — anàlisi funcional de cada check", text)
        self.assertNotIn("Responsable No informat", text)

    def test_generate_post_crq_pdf_report(self):
        payload = {
            "profile": "E13DB",
            "format": "pdf",
            "data": {
                "audit_type": "post_crq",
                "context": {
                    "profile": "E13DB",
                    "schemas": ["APP_USER"],
                    "time_filter": {
                        "mode": "preset",
                        "preset": "weekly",
                        "days_back": 7,
                        "resolved_at": "2026-03-08T20:05:00",
                    },
                    "source_file": "auditoria_post_crq.md",
                    "source_path": "C:/repo/Auditoria_post_crq.md",
                },
                "summary": {
                    "selected_checks": 1,
                    "executed_checks": 1,
                    "checks_with_findings": 1,
                    "total_findings": 1,
                    "checks_with_errors": 0,
                },
                "executed_checks": [
                    {
                        "check_id": "CHECK_03",
                        "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                        "severitat": "Crític",
                        "criticitat": "Crític",
                        "criticitat_key": "CRITIC",
                        "status": "ok",
                        "row_count": 1,
                        "duration_ms": 1200,
                    }
                ],
                "report_model": {
                    "execution_parameters": {
                        "profile": "E13DB",
                        "generated_at": "2026-03-08 20:05",
                        "time_window": {"start_at": "2026-03-01T20:05", "end_at": "2026-03-08T20:05"},
                        "language": "Català",
                        "encoding": "UTF-8",
                        "source_file": "auditoria_post_crq.md",
                        "enabled_checks": [{"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"}],
                        "schemas": ["APP_USER"],
                    },
                    "enabled_checks": [{"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"}],
                    "lot_summary": [
                        {
                            "lot": "LOT_APP",
                            "critical": 1,
                            "medium": 0,
                            "low": 0,
                            "checks": ["CHECK_03"],
                            "check_descriptions": [{"check_id": "CHECK_03", "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT"}],
                            "first_action": "Definir CACHE adequat a la seqüència.",
                            "dominant_impact": "Risc de rendiment en insercions concurrents.",
                            "priority": "Crític",
                        }
                    ],
                    "lot_incident_groups": [
                        {
                            "lot": "LOT_APP",
                            "check": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "severity": "Crític",
                            "termini_dies": 0,
                            "impacte": "Pot degradar insercions concurrents.",
                            "accio_recomanada": "Definir CACHE adequat i revisar el bloc <LOOP> afectat.",
                            "validacio_posterior": "Executar prova d'inserció posterior.",
                            "schemas": [
                                {
                                    "nom": "APP_USER",
                                    "object_count": 1,
                                    "objectes": [
                                        {
                                            "nom": "SEQ_ALPHA",
                                            "tipus": "SEQUENCE",
                                            "dada_tecnica": "CACHE_ACTUAL=0",
                                            "accio_recomanada": "Definir CACHE adequat",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "critical_checks_grouped": [
                        {
                            "check_id": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "summary_text": "S'ha detectat una seqüència sense cache.",
                            "impact_text": "Pot degradar insercions concurrents.",
                            "urgency_label": "URGENT",
                            "recommended_action": "Definir CACHE adequat.",
                            "review_steps": "Comprovar el valor actual de CACHE.",
                            "post_validation": "Executar prova d'inserció posterior.",
                            "lot_rows": [
                                {"lot": "LOT_APP", "esquema": "APP_USER", "objecte": "SEQ_ALPHA", "severitat": "Crític", "dada_tecnica": "CACHE_ACTUAL=0", "accio_recomanada": "Definir CACHE adequat"}
                            ],
                        }
                    ],
                    "detail_sections": [
                        {
                            "check_id": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "status": "ok",
                            "criticality": "Crític",
                            "overview": "Detecta seqüències sense cache o amb cache massa baixa.",
                            "why_it_matters": "Pot penalitzar processos d'inserció concurrents.",
                            "finding_count": 1,
                            "columns": ["Lot", "ESQUEMA", "SEQUENCIA", "CACHE_ACTUAL", "ESTAT", "ACCIO_RECOMANADA"],
                            "rows": [
                                {"Lot": "LOT_APP", "ESQUEMA": "APP_USER", "SEQUENCIA": "SEQ_ALPHA", "CACHE_ACTUAL": 0, "ESTAT": "NOCACHE", "ACCIO_RECOMANADA": "Definir CACHE adequat"}
                            ],
                        }
                    ],
                    "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Aplicar correcció i reexecutar el check."]},
                    "quality_gate": {"status": "ok", "issues": []},
                },
                "errors": [],
            },
        }

        res = self.client.post("/api/report/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_post_crq_E13DB", res.headers.get("content-disposition", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_generate_post_crq_pdf_report_with_all_checks_enabled(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))

        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Context de l'auditoria", extracted)
        self.assertIn("Resultat detallat per check", extracted)
        self.assertIn("CHECK_01", extracted)
        self.assertIn("CHECK_12", extracted)

    def test_generate_post_crq_pdf_report_contains_cover_content(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        reader = PdfReader(io.BytesIO(res.content))
        cover_text = reader.pages[0].extract_text() or ""
        self.assertIn("AUDITORIA ORACLE · VALIDACIÓ POST-CRQ", cover_text)
        self.assertIn("Informe d'auditoria post-CRQ", cover_text)
        self.assertIn("Perfil", cover_text)
        self.assertIn("Finestra auditada", cover_text)
        self.assertIn("Període aplicat", cover_text)
        self.assertIn("Data de generació", cover_text)
        self.assertIn("Resum global", cover_text)
        self.assertIn("Departament d'Educació i Formació Professional · Informe generat automàticament", cover_text)
        self.assertNotIn("VALIDACIÃ", cover_text)
        self.assertNotIn("Â·", cover_text)

    def test_generate_post_crq_pdf_report_contains_toc_entries(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        reader = PdfReader(io.BytesIO(res.content))
        toc_text = "\n".join((page.extract_text() or "") for page in reader.pages[1:4])
        self.assertIn("Índex", toc_text)
        self.assertIn("1. Context de l'auditoria", toc_text)
        self.assertIn("2. Resum executiu post-CRQ", toc_text)
        self.assertIn("4. Resultat detallat per check", toc_text)

    def test_generate_post_crq_pdf_report_toc_has_internal_links(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        reader = PdfReader(io.BytesIO(res.content))
        toc_page = reader.pages[1]
        annots = toc_page.get("/Annots") or []
        self.assertGreaterEqual(len(annots), 5)
        destinations = []
        for annot_ref in annots:
            annot = annot_ref.get_object()
            self.assertEqual(annot.get("/Subtype"), "/Link")
            destinations.append(annot.get("/Dest"))
        self.assertTrue(any(destinations))

    def test_generate_post_crq_pdf_report_does_not_show_markdown_syntax(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:8])
        self.assertNotIn("| OBJECTE |", extracted)
        self.assertNotIn("**Què detecta:**", extracted)
        self.assertNotIn("](#context)", extracted)

    def test_generate_post_crq_pdf_report_renders_react_style_object_table(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:10])
        lowered = extracted.lower()
        self.assertIn("objecte", lowered)
        self.assertIn("tipus", lowered)
        self.assertIn("dada tècnica", lowered)

    def test_generate_post_crq_pdf_report_sanitizes_report_model_before_render(self):
        payload = _build_all_checks_post_crq_pdf_payload()
        payload["data"]["report_model"]["lot_summary"][0]["first_action"] = "Acció amb <LOOP>, <if>, </para> i &"
        payload["data"]["report_model"]["detail_sections"][0]["overview"] = "Overview amb <LOOP>, <if>, </para> i &"
        payload["data"]["report_model"]["lot_incident_groups"][0]["description"] = "Descripció amb <LOOP>, <if>, </para> i &"

        res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_generate_post_crq_pdf_report_falls_back_when_renderer_raises_paraparser(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        with self.assertLogs("src.api.post_crq_audit", level="WARNING") as captured:
            with patch(
                "src.api.post_crq_audit._build_post_crq_pdf_from_report_model_final_v7",
                side_effect=Exception("paraparser: syntax error: parse ended with 1 unclosed tags para"),
            ):
                res = self.client.post("/api/report/generate", json=payload)

        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))
        self.assertTrue(any("Falling back to safe post CRQ PDF builder" in message for message in captured.output))

        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:8])
        self.assertNotIn("| OBJECTE |", extracted)
        self.assertNotIn("**Què detecta:**", extracted)
        self.assertNotIn("](#context)", extracted)
        self.assertIn("objecte", extracted.lower())

    def test_post_crq_markdown_index_uses_internal_links_for_fallback(self):
        payload = _build_all_checks_post_crq_pdf_payload()

        markdown = _build_post_crq_markdown_from_report_model_final_v7(payload["profile"], payload["data"])

        self.assertIn("- [1. Context de l'auditoria](#context)", markdown)
        self.assertIn("- [4. Resultat detallat per check](#detall)", markdown)

    def test_generate_post_crq_experimental_pdf_report(self):
        payload = {
            "profile": "E13DB",
            "data": {
                "audit_type": "post_crq",
                "context": {
                    "profile": "E13DB",
                    "schemas": ["APP_USER"],
                    "time_filter": {
                        "mode": "preset",
                        "preset": "weekly",
                        "days_back": 7,
                        "resolved_at": "2026-03-08T20:05:00",
                    },
                    "source_file": "auditoria_post_crq.md",
                    "source_path": "C:/repo/Auditoria_post_crq.md",
                },
                "report_model": {
                    "execution_parameters": {
                        "profile": "E13DB",
                        "generated_at": "2026-03-08 20:05",
                        "time_window": {"start_at": "2026-03-01T20:05", "end_at": "2026-03-08T20:05"},
                        "time_filter_label": "weekly",
                        "language": "Català",
                        "encoding": "UTF-8",
                        "source_file": "auditoria_post_crq.md",
                        "enabled_checks": [{"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"}],
                        "schemas": ["APP_USER"],
                    },
                    "enabled_checks": [{"check_id": "CHECK_03", "title": "SEQÜÈNCIES...", "criticality": "Crític"}],
                    "lot_summary": [
                        {
                            "lot": "LOT_APP",
                            "critical": 1,
                            "medium": 0,
                            "low": 0,
                            "checks": ["CHECK_03"],
                            "schemas": ["APP_USER"],
                            "affected_objects": 1,
                            "first_action": "Definir CACHE adequat a la seqüència.",
                            "dominant_impact": "Risc de rendiment en insercions concurrents.",
                            "priority": "Crític",
                        }
                    ],
                    "lot_incident_groups": [
                        {
                            "lot": "LOT_APP",
                            "check": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "description": "S'ha detectat una seqüència sense cache.",
                            "severity": "Crític",
                            "termini_dies": 0,
                            "impacte": "Pot degradar insercions concurrents.",
                            "accio_recomanada": "Definir CACHE adequat.",
                            "validacio_posterior": "Executar prova d'inserció posterior.",
                            "schemas": [
                                {
                                    "nom": "APP_USER",
                                    "object_count": 1,
                                    "objectes": [
                                        {
                                            "OBJECTE": "SEQ_ALPHA",
                                            "TIPUS": "SEQUENCE",
                                            "DADA TÈCNICA": "CACHE_ACTUAL=0",
                                            "OBSERVACIÓ": "Definir CACHE adequat",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "detail_sections": [
                        {
                            "check_id": "CHECK_03",
                            "title": "SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT",
                            "criticality": "Crític",
                            "duration_ms": 1200,
                            "finding_count": 1,
                            "overview": "Detecta seqüències sense cache o amb cache massa baixa.",
                            "columns": ["OBJECTE", "TIPUS", "DADA TÈCNICA"],
                            "rows": [{"OBJECTE": "SEQ_ALPHA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE_ACTUAL=0"}],
                        }
                    ],
                    "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Aplicar correcció i reexecutar el check."]},
                },
                "report_options": {"include_annex": True},
            },
        }

        res = self.client.post("/api/report/generate-experimental", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_post_crq_experimental_E13DB", res.headers.get("content-disposition", ""))
        self.assertTrue(res.content.startswith(b"%PDF"))
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("2. Resum executiu post-CRQ", extracted)
        self.assertIn("3. Incidències prioritzades per criticitat i lot", extracted)
        self.assertIn("4. Resultat detallat per check", extracted)
        self.assertIn("5. Observacions finals", extracted)
        self.assertIn("Annex V2 - Resum executiu experimental", extracted)
        self.assertIn("Semàfor executiu", extracted)
        self.assertIn("Validacions de coherència", extracted)
        self.assertNotIn("Mapa de lots detectats", extracted)

    def test_generate_post_crq_experimental_pdf_report_handles_large_detail_tables(self):
        long_text = "Detall molt extens amb fragments repetits per forçar l'ajust de la fila. " * 80
        rows = []
        for index in range(56):
            rows.append(
                {
                    "Lot": "LOT_APP",
                    "OBJECTE": f"OBJ_{index:02d}",
                    "TIPUS": "TABLE",
                    "DADA TÈCNICA": long_text if index == 0 else f"Detall breu {index}",
                }
            )

        payload = {
            "profile": "E13DB",
            "data": {
                "audit_type": "post_crq",
                "context": {
                    "profile": "E13DB",
                    "schemas": ["APP_USER"],
                    "time_filter": {
                        "mode": "range",
                        "range_start_at": "2026-04-07T17:30",
                        "range_end_at": "2026-04-08T17:30",
                    },
                    "source_file": "auditoria_post_crq.md",
                    "source_path": "C:/repo/Auditoria_post_crq.md",
                },
                "report_model": {
                    "execution_parameters": {
                        "profile": "E13DB",
                        "generated_at": "2026-04-08 17:35",
                        "time_window": {"start_at": "2026-04-07T17:30", "end_at": "2026-04-08T17:30"},
                        "time_filter_label": "range",
                        "language": "Català",
                        "encoding": "UTF-8",
                        "source_file": "auditoria_post_crq.md",
                        "enabled_checks": [{"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"}],
                        "schemas": ["APP_USER"],
                    },
                    "enabled_checks": [{"check_id": "CHECK_01", "title": "TAULES...", "criticality": "Mitjà"}],
                    "lot_summary": [
                        {
                            "lot": "LOT_APP",
                            "critical": 0,
                            "medium": 1,
                            "low": 0,
                            "checks": ["CHECK_01"],
                            "schemas": ["APP_USER"],
                            "affected_objects": 56,
                            "first_action": "Revisar objectes afectats.",
                            "dominant_impact": "Impacte sobre integritat.",
                            "priority": "Mitjà",
                        }
                    ],
                    "lot_incident_groups": [
                        {
                            "lot": "LOT_APP",
                            "check": "CHECK_01",
                            "title": "TAULES RECENTS SENSE PRIMARY KEY",
                            "description": "Es detecten taules sense PK.",
                            "severity": "Mitjà",
                            "termini_dies": 15,
                            "impacte": "Pot afectar la integritat.",
                            "accio_recomanada": "Definir PRIMARY KEY.",
                            "validacio_posterior": "Revalidar el lot afectat.",
                            "schemas": [
                                {
                                    "nom": "APP_USER",
                                    "object_count": 56,
                                    "objectes": [
                                        {
                                            "OBJECTE": f"OBJ_{index:02d}",
                                            "TIPUS": "TABLE",
                                            "DADA TÈCNICA": "BREU",
                                        }
                                        for index in range(56)
                                    ],
                                }
                            ],
                        }
                    ],
                    "detail_sections": [
                        {
                            "check_id": "CHECK_01",
                            "title": "TAULES RECENTS SENSE PRIMARY KEY",
                            "criticality": "Mitjà",
                            "duration_ms": 950,
                            "finding_count": 56,
                            "overview": "Detall tècnic amb múltiples files i una cel·la molt llarga.",
                            "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                            "rows": rows,
                        }
                    ],
                    "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Revisar i continuar."]},
                },
                "report_options": {"include_annex": True},
            },
        }

        res = self.client.post("/api/report/generate-experimental", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("OBJ_00", extracted)
        self.assertIn("OBJ_55", extracted)

    def test_experimental_pdf_numeric_helpers_tolerate_invalid_values(self):
        self.assertEqual(_humanize_duration_ms("not-a-number"), "-")
        self.assertIn("termini establert", _deadline_text("invalid", "Mitjà"))

    def test_generate_post_crq_experimental_pdf_report_for_lot(self):
        payload = _build_multi_lot_experimental_payload()

        res = self.client.post(
            "/api/report/generate-experimental",
            json={**payload, "variant": "lot", "lot_code": "LOT_APP"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=report_auditoria_post_crq_experimental_E13DB_LOT_APP", res.headers.get("content-disposition", ""))
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("LOT LOT_APP", extracted)
        self.assertNotIn("LOT LOT_AUX", extracted)
        self.assertIn("CHECK_03", extracted)
        self.assertNotIn("TMP_BETA", extracted)

    def test_generate_post_crq_experimental_pdf_report_for_unknown_lot_returns_400(self):
        payload = _build_multi_lot_experimental_payload()

        res = self.client.post(
            "/api/report/generate-experimental",
            json={**payload, "variant": "lot", "lot_code": "LOT_UNKNOWN"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("LOT_UNKNOWN", res.json().get("detail", ""))

    @patch("src.api.main.run_post_crq_audit", side_effect=lambda **kwargs: _build_multi_lot_experimental_payload()["data"])
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.config_loader.resolve_profile_name", side_effect=lambda requested, profiles: requested or "E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    def test_generate_post_crq_manual_general_report(self, _load_connections, _resolve_profile, _db_manager, _run_post_crq):
        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "general", "selected_checks": ["CHECK_01"]},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("report_auditoria_post_crq_general_E13DB", res.headers.get("content-disposition", ""))
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Resum executiu", extracted)

    @patch("src.api.main.run_post_crq_audit")
    def test_generate_post_crq_manual_general_report_v2(self, run_post_crq_mock):
        run_post_crq_mock.return_value = _build_multi_lot_experimental_payload()["data"]

        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "general", "summary_version": "v2", "selected_checks": ["CHECK_01"]},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("_v2.pdf", res.headers.get("content-disposition", ""))
        self.assertEqual(res.headers.get("x-post-crq-summary-version"), "v2")
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:4])
        self.assertIn("Semàfor executiu", extracted)
        self.assertIn("Validacions de coherència", extracted)

    @patch("src.api.main.run_post_crq_audit")
    def test_generate_post_crq_manual_general_report_reuses_cached_report_data(self, run_post_crq_mock):
        payload = _build_multi_lot_experimental_payload()["data"]

        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "general", "report_data": payload},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        self.assertIn("report_auditoria_post_crq_general_E13DB", res.headers.get("content-disposition", ""))
        run_post_crq_mock.assert_not_called()

    @patch("src.api.main.utc_now", return_value=dt.datetime(2026, 3, 26, 10, 11, 12, tzinfo=dt.timezone.utc))
    @patch("src.api.main.run_post_crq_audit")
    def test_generate_post_crq_manual_general_report_uses_utc_timestamp_slug(self, run_post_crq_mock, _utc_now):
        payload = _build_multi_lot_experimental_payload()["data"]

        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "general", "report_data": payload},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(
            "attachment; filename=report_auditoria_post_crq_general_E13DB_20260326_101112.pdf",
            res.headers.get("content-disposition", ""),
        )
        run_post_crq_mock.assert_not_called()

    @patch("src.api.main.run_post_crq_audit", side_effect=lambda **kwargs: _build_multi_lot_experimental_payload()["data"])
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.config_loader.resolve_profile_name", side_effect=lambda requested, profiles: requested or "E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    def test_generate_post_crq_manual_provider_report(self, _load_connections, _resolve_profile, _db_manager, _run_post_crq):
        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "provider", "provider_code": "LOT_APP", "selected_checks": ["CHECK_01"]},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/pdf", res.headers.get("content-type", ""))
        reader = PdfReader(io.BytesIO(res.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("LOT LOT_APP", extracted)
        self.assertNotIn("LOT LOT_AUX", extracted)

    @patch("src.api.main.run_post_crq_audit", side_effect=lambda **kwargs: _build_multi_lot_experimental_payload()["data"])
    @patch("src.api.main.OracleDBManager")
    @patch("src.api.main.config_loader.resolve_profile_name", side_effect=lambda requested, profiles: requested or "E13DB")
    @patch("src.api.main.config_loader.load_connections", return_value={"E13DB": {"USER": "demo"}})
    def test_generate_post_crq_manual_all_reports_bundle(self, _load_connections, _resolve_profile, _db_manager, _run_post_crq):
        res = self.client.post(
            "/api/audit/post-crq/reports",
            json={"profile": "E13DB", "variant": "all", "selected_checks": ["CHECK_01"]},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/zip", res.headers.get("content-type", ""))
        with zipfile.ZipFile(io.BytesIO(res.content), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("general.pdf", names)
        self.assertIn("provider_LOT_APP.pdf", names)
        self.assertIn("provider_LOT_AUX.pdf", names)


if __name__ == "__main__":
    unittest.main()


def test_report_now_text_uses_utc_now():
    fixed = dt.datetime(2026, 3, 26, 10, 11, 12, tzinfo=dt.timezone.utc)
    with patch("src.api.report_builder.utc_now", return_value=fixed):
        assert _report_now_text() == "2026-03-26 10:11:12"


def test_automation_analytics_generated_at_text_uses_utc_now():
    fixed = dt.datetime(2026, 3, 26, 10, 11, 0, tzinfo=dt.timezone.utc)
    with patch("src.api.automation_analytics_pdf.utc_now", return_value=fixed):
        assert _generated_at_text() == "2026-03-26 10:11"


def test_generate_ai_text_returns_none_on_error():
    with patch("src.core.ai_assistant.AIAssistant", side_effect=RuntimeError("ai down")):
        assert _generate_ai_text("hola", timeout=5) is None


def test_build_standard_markdown_uses_ai_fallback_text():
    payload = [
        {
            "username": "APP_A",
            "audit_result": "PRECAUCIO",
            "obsolescence_score": 77,
            "summary": {
                "SIZE_GB": 1.5,
                "INBOUND_REFERENCES": 2,
                "ACTIVE_JOBS": 0,
                "APEX_APPLICATIONS": 1,
                "ENABLED_TRIGGERS": 0,
            },
            "executed_queries": [],
            "invalid_objects": [],
            "reason": "demo",
        }
    ]

    with patch(
        "src.api.report_builder._DESIGN_AGENT.get_report_structure",
        return_value=[
            {"id": "context", "title": "Context", "enabled": True},
            {"id": "ai_diagnostic", "title": "Diagnosi IA", "enabled": True},
        ],
    ), patch("src.api.report_builder._generate_ai_text", return_value=None):
        markdown = build_standard_markdown("E13DB", payload, ai_active=True)

    assert "_No s'ha pogut generar el diagnostic IA._" in markdown


def test_build_post_crq_markdown_uses_ai_fallback_text():
    payload = _build_multi_lot_experimental_payload()["data"]

    with patch(
        "src.api.report_builder._DESIGN_AGENT.get_report_structure",
        return_value=[
            {"id": "summary", "title": "Resum executiu", "type": "summary"},
            {"id": "ai_diagnostic", "title": "Diagnosi IA", "type": "ai_diagnostic", "condition": "ai_active"},
        ],
    ), patch("src.api.report_builder._generate_ai_text", return_value=None):
        markdown = build_post_crq_markdown("E13DB", payload, ai_active=True)

    assert "_IA no disponible._" in markdown


def test_generate_ai_text_returns_none_when_assistant_raises():
    with patch("src.core.ai_assistant.AIAssistant") as assistant_cls:
        assistant_cls.return_value.generate_response.side_effect = RuntimeError("ai down")

        result = _generate_ai_text("demo prompt")

    assert result is None

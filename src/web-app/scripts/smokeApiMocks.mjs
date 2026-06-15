const postCrqChecks = [
  {
    check_id: 'CHECK_01',
    title: 'TAULES RECENTS SENSE PRIMARY KEY',
    severitat: 'Mitjà',
    criticitat: 'Mitjà',
    criteri: 'Només taules modificades recentment',
  },
  {
    check_id: 'CHECK_03',
    title: 'SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT',
    severitat: 'Crític',
    criticitat: 'Crític',
    criteri: 'Només seqüències modificades recentment',
  },
  {
    check_id: 'CHECK_04',
    title: 'FOREIGN KEYS RECENTS SENSE ÍNDEX DE SUPORT',
    severitat: 'Crític',
    criticitat: 'Crític',
    criteri: 'Només foreign keys modificades recentment',
  },
];

const postCrqRunResponse = {
  audit_type: 'post_crq',
  context: {
    profile: 'E13DB',
    schemas: ['APP_USER'],
    time_filter: { mode: 'preset', preset: 'weekly', days_back: 7 },
    source_file: 'auditoria_post_crq.md',
  },
  summary: {
    selected_checks: 3,
    executed_checks: 3,
    checks_with_findings: 1,
    total_findings: 1,
    checks_with_errors: 0,
    error_count: 0,
    findings_by_criticality: { 'Crític': 0, 'Mitjà': 1, 'Baix': 0 },
    criticality_sections: [
      { criticality_key: 'CRITIC', criticality_label: 'Crític', action_text: "Aquestes incidències s'han de solucionar de manera urgent.", items: [] },
      { criticality_key: 'MITJA', criticality_label: 'Mitjà', action_text: "Aquestes incidències s'han de solucionar en un termini màxim de 15 dies.", items: [{ check_id: 'CHECK_01', summary_text: "S'ha trobat 1 taula dels esquemes APP_USER sense primary key." }] },
      { criticality_key: 'BAIX', criticality_label: 'Baix', action_text: "Aquestes incidències s'han de solucionar en un termini màxim d'1 mes.", items: [] },
    ],
    detected_time_range: { start_at: '2026-03-08 10:00', end_at: '2026-03-08 10:00' },
    environment_message: 'Corregir urgentment',
  },
  report_model: {
    agent_runtime: {
      orchestrator: 'orchestrator-e13bd',
      architect: 'architect-e13bd',
      dba: 'dba-e13bd',
      developer: 'developer-e13bd',
      tester: 'tester-e13bd',
      reporting: 'insights-reporting-e13bd',
      phases: [
        { id: 'context', lead: 'orchestrator-e13bd', validators: ['architect-e13bd'] },
        { id: 'reporting', lead: 'insights-reporting-e13bd', validators: ['tester-e13bd'] },
      ],
    },
    criticality_blocks: [
      { criticality_key: 'CRITIC', criticality_label: 'Crític', action_text: "Aquestes incidències s'han de solucionar de manera urgent.", items: [] },
      {
        criticality_key: 'MITJA',
        criticality_label: 'Mitjà',
        action_text: "Aquestes incidències s'han de solucionar en un termini màxim de 15 dies.",
        items: [
          {
            check_id: 'CHECK_01',
            title: 'TAULES RECENTS SENSE PRIMARY KEY',
            summary_text: "S'han detectat taules dels esquemes APP_USER sense primary key.",
            top_examples: [{ schema: 'APP_USER', object_name: 'TMP_EXAMPLE', lot: 'LOT_APP', responsable: 'No assignat' }],
          },
        ],
      },
      { criticality_key: 'BAIX', criticality_label: 'Baix', action_text: "Aquestes incidències s'han de solucionar en un termini màxim d'1 mes.", items: [] },
    ],
    critical_incident_cards: [],
    quality_gate: { status: 'ok', issues: [], critical_without_lot: 0 },
    execution_parameters: {
      profile: 'E13DB',
      generated_at: '2026-03-08 10:00',
      time_window: { start_at: '2026-03-08 10:00', end_at: '2026-03-08 10:00' },
    },
    lot_summary: [
      {
        lot: 'LOT_APP',
        critical: 0,
        medium: 1,
        low: 0,
        checks: ['CHECK_01'],
        check_descriptions: [{ check_id: 'CHECK_01', title: 'TAULES RECENTS SENSE PRIMARY KEY' }],
        schemas: ['APP_USER'],
        affected_objects: 1,
        first_action: "Crear la PRIMARY KEY o justificar documentalment l'excepció.",
        dominant_impact: "Risc d'integritat i dificultat de manteniment.",
        priority: 'Mitjà',
      },
    ],
    lot_incident_groups: [
      {
        lot: 'LOT_APP',
        check: 'CHECK_01',
        title: 'TAULES RECENTS SENSE PRIMARY KEY',
        description: "S'ha detectat una taula sense PRIMARY KEY activa.",
        severity: 'Mitjà',
        termini_dies: 15,
        impacte: 'Complica la integritat i el manteniment del model.',
        accio_recomanada: "Crear la PRIMARY KEY o justificar documentalment l'excepció.",
        validacio_posterior: 'Reexecutar el check i validar la unicitat de les dades.',
        schemas: [
          {
            nom: 'APP_USER',
            object_count: 1,
            objectes: [{ OBJECTE: 'TMP_EXAMPLE', TIPUS: 'TABLE', 'DADA TÈCNICA': 'Sense PK activa · volum baix' }],
          },
        ],
      },
    ],
    final_observations: {
      blocking_errors: [],
      warnings: [],
      next_steps: ["Aplicar la correcció i reexecutar l'auditoria."],
    },
  },
  report_options: { include_annex: true },
  executed_checks: [
    { check_id: 'CHECK_01', title: 'TAULES RECENTS SENSE PRIMARY KEY', severitat: 'Mitjà', criticitat: 'Mitjà', status: 'ok', row_count: 1 },
  ],
  results_by_check: [
    {
      check_id: 'CHECK_01',
      title: 'TAULES RECENTS SENSE PRIMARY KEY',
      severitat: 'Mitjà',
      criticitat: 'Mitjà',
      status: 'ok',
      row_count: 1,
      columns: ['ESQUEMA', 'TAULA'],
      rows: [{ ESQUEMA: 'APP_USER', TAULA: 'TMP_EXAMPLE' }],
    },
  ],
  query_export: {
    filename: 'consultes_post_crq_E13DB.txt',
    content: '-- Q01_SUMMARY_360\nselect * from dual;\n\n-- Q08_DEPS_INCOMING\nselect owner, table_name from all_tables;',
  },
  errors: [],
};

function json(route, data, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(data),
  });
}

function jsonError(route, detail, status = 500) {
  return json(route, { detail }, status);
}

function pdf(route, body = '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF', headers = {}) {
  return route.fulfill({
    status: 200,
    contentType: 'application/pdf',
    headers,
    body,
  });
}

function deepScanResponse(schemaName) {
  return {
    username: schemaName,
    summary: {
      INBOUND_REFERENCES: 0,
      EXTERNAL_DEPENDENCIES_OUT: 0,
      TABLES_WITH_MODS_30D: 0,
      TABLES_STATS_RECENT_30D: 0,
      LAST_LOGIN_DAYS: 365,
      SIZE_GB: 0.02,
      ACTIVE_JOBS: 0,
      ENABLED_TRIGGERS: 0,
      APEX_APPLICATIONS: 0,
      LAST_DDL_DAYS: 240,
      RECENT_DDL_COUNT: 0,
    },
    code_refs: [],
    tables_with_mods: [],
    recent_stats_tables: [],
    dependencies_incoming: [],
    dependencies_outgoing: [],
    executed_queries: [
      { id: 'Q01_SUMMARY_360', status: 'ok', rows: 1, optional: false },
      { id: 'Q08_DEPS_INCOMING', status: 'ok', rows: 0, optional: false },
      { id: 'Q09_DEPS_OUTGOING', status: 'ok', rows: 0, optional: false },
    ],
  };
}

function normalizePath(url) {
  return new URL(url).pathname;
}

export async function installApiMocks(page, options = {}) {
  const scenario = options.scenario || 'happy';
  const unknownRequests = new Set();
  let nextAutomationJobId = 10;
  const obsoletsItems = [
    {
      id: 1,
      schema_name: 'APP_USER',
      object_name: 'TMP_EXAMPLE',
      object_type: 'TABLE',
      risk_level: 'MEDIUM',
      recommendation: 'Revisar abans d’eliminar',
      source: 'manual',
      reason: 'Sense ús funcional conegut',
    },
  ];
  const automationJobs = [
    {
      id: 9,
      name: 'Job setmanal',
      enabled: true,
      audit_type: 'post_crq_distribution',
      profile: 'E13DB',
      schedule_type: 'weekly',
      timeout_seconds: 300,
      checks: ['CHECK_01'],
      schedule_config: { start_at: '2026-03-25T08:00:00' },
      delivery_targets: [],
      job_config: {
        lot_scope: { mode: 'all', selected_lots: [] },
        send_policy: { send_only_with_findings: true, send_without_findings: false, record_without_findings: true },
        email_template: { subject: '[Oracle Audit] Job setmanal - {lot}', body: 'Cos de prova' },
        report_options: { include_summary: true, include_lot_reports: true },
      },
    },
  ];
  const masterLots = [
    { code: 'LOT_APP', label: 'Aplicacions', description: 'Lot funcional', enabled: true },
  ];
  const schemaLots = [
    { schema_name: 'APP_USER', lot_name: 'LOT_APP' },
  ];
  const lotRoutes = [
    { lot_code: 'LOT_APP', audience: 'provider', label: 'Aplicacions', emails: ['app@example.com'], enabled: true },
  ];
  const deliveryTemplates = [
    { template_key: 'provider_with_findings', audience: 'provider', subject_template: 'Assumpte', body_template: 'Cos', enabled: true },
    { template_key: 'tic_summary', audience: 'tic', subject_template: 'Resum TIC', body_template: 'Cos TIC', enabled: true },
  ];
  let nextRetryQueueId = 502;
  const retryQueue = [
    { id: 501, run_id: 77, lot: 'LOT_APP', audience: 'provider', attempt_number: 1, retry_mode: 'manual', status: 'pending', last_error: 'SMTP KO' },
  ];
  let backfillRun = null;

  await page.route('**/*', async (route) => {
    const request = route.request();
    const path = normalizePath(request.url());
    const method = request.method();

    if (!path.startsWith('/api/')) {
      return route.continue();
    }

    if (path === '/api/profiles' && method === 'GET') {
      if (scenario === 'profiles-error') {
        return jsonError(route, 'Fallo controlado perfiles');
      }
      return json(route, { profiles: ['E13DB'], default: 'E13DB' });
    }

    if (path.startsWith('/api/audit/deep-scan/') && method === 'GET') {
      const schemaName = decodeURIComponent(path.split('/').pop() || 'APP_USER');
      return json(route, deepScanResponse(schemaName));
    }

    if (path === '/api/db/test' && method === 'POST') {
      return json(route, { status: 'success', message: 'Connexió correcta' });
    }

    if (path === '/api/audit/post-crq/checks' && method === 'GET') {
      if (scenario === 'load-error') {
        return jsonError(route, 'Fallo controlado carga checks');
      }
      return json(route, { checks: postCrqChecks });
    }

    if (path === '/api/audit/post-crq/run' && method === 'POST') {
      if (scenario === 'error') {
        return jsonError(route, 'Fallo controlado post-CRQ');
      }
      return json(route, postCrqRunResponse);
    }

    if (path === '/api/audit/post-crq/reports' && method === 'POST') {
      if (scenario === 'error') {
        return jsonError(route, 'Fallo controlado report Post-CRQ');
      }
      const payload = request.postDataJSON() || {};
      const isAllVariant = (payload.variant || 'all') === 'all';
      return route.fulfill({
        status: 200,
        contentType: isAllVariant ? 'application/zip' : 'application/pdf',
        headers: {
          'content-disposition': isAllVariant
            ? 'attachment; filename="auditoria_lots_E13DB.zip"'
            : 'attachment; filename="report_post_crq_E13DB.pdf"',
        },
        body: isAllVariant ? 'PK\x03\x04smoke-zip' : '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF',
      });
    }

    if (path === '/api/report/generate' && method === 'POST') {
      return pdf(route);
    }

    if (path === '/api/docs/technical-audit' && method === 'GET') {
      return json(route, { content: '# Documentació\n\nContingut tècnic de prova.' });
    }

    if (path === '/api/obsolets' && method === 'GET') {
      return json(route, { items: obsoletsItems, page: { limit: 200, offset: 0 } });
    }

    if (path === '/api/obsolets' && method === 'POST') {
      const payload = request.postDataJSON() || {};
      obsoletsItems.unshift({
        id: obsoletsItems.length + 1,
        schema_name: payload.schema_name || '',
        object_name: payload.object_name || '',
        object_type: payload.object_type || 'TABLE',
        risk_level: payload.risk_level || 'LOW',
        recommendation: payload.recommendation || '',
        source: 'manual',
        reason: payload.reason || '',
      });
      return json(route, { status: 'success' }, 201);
    }

    if (path === '/api/checks' && method === 'GET') {
      return json(route, [
        {
          check_id: 'CHECK_01',
          titol: 'Taules recents sense primary key',
          severitat_base: 'Mitjà',
          tipus: 'SQL',
          ordre: 1,
          activa: true,
          estat_explicacio: 'VIGENT',
          estat_sync: 'OK',
          criteri_funcional: 'Revisa taules recents sense PK',
          sql_text: 'select 1 from dual',
          explicacio_ia: 'Explicació de prova',
        },
      ]);
    }

    if (path.startsWith('/api/checks/') && method === 'GET') {
      if (path.endsWith('/history')) return json(route, []);
      if (path.endsWith('/sync-status')) return json(route, { status: 'OK' });
      return json(route, {
        check_id: 'CHECK_01',
        titol: 'Taules recents sense primary key',
        severitat_base: 'Mitjà',
        tipus: 'SQL',
        ordre: 1,
        activa: true,
        estat_explicacio: 'VIGENT',
        estat_sync: 'OK',
        criteri_funcional: 'Revisa taules recents sense PK',
        sql_text: 'select 1 from dual',
        explicacio_ia: 'Explicació de prova',
      });
    }

    if (path.startsWith('/api/checks/') && ['POST', 'PUT', 'DELETE'].includes(method)) {
      return json(route, { status: 'success' });
    }

    if (path.startsWith('/api/automation/')) {
      if (path === '/api/automation/change-events' && method === 'GET') {
        if (scenario === 'load-error') {
          return jsonError(route, 'Fallo controlado carga automatitzacions');
        }
        return json(route, { items: [{ id: 1, created_at: '2026-03-25T08:10:00Z', entity_type: 'template', entity_key: 'provider_with_findings', action: 'update', actor: 'automation_ui', reason: 'Smoke test' }] });
      }
      if (path === '/api/automation/jobs' && method === 'GET') {
        return json(route, { items: automationJobs });
      }
      if (path === '/api/automation/jobs' && method === 'POST') {
        const payload = request.postDataJSON() || {};
        const createdJob = {
          id: nextAutomationJobId++,
          name: payload.name || `Job ${nextAutomationJobId}`,
          enabled: payload.enabled !== false,
          audit_type: payload.audit_type || 'post_crq',
          profile: payload.profile || 'E13DB',
          schedule_type: payload.schedule_type || 'weekly',
          timeout_seconds: Number(payload.timeout_seconds || 300),
          checks: payload.checks || [],
          schedule_config: payload.schedule_config || { start_at: '2026-03-25T08:00:00' },
          delivery_targets: payload.delivery_targets || [],
          job_config: payload.job_config || {},
        };
        automationJobs.unshift(createdJob);
        return json(route, createdJob, 201);
      }
      if (/^\/api\/automation\/jobs\/\d+$/.test(path) && method === 'PUT') {
        const jobId = Number(path.split('/').pop());
        const payload = request.postDataJSON() || {};
        const targetJob = automationJobs.find((item) => item.id === jobId);
        if (!targetJob) {
          return jsonError(route, 'Job no trobat', 404);
        }
        Object.assign(targetJob, payload);
        return json(route, targetJob);
      }
      if (/^\/api\/automation\/jobs\/\d+$/.test(path) && method === 'DELETE') {
        const jobId = Number(path.split('/').pop());
        const jobIndex = automationJobs.findIndex((item) => item.id === jobId);
        if (jobIndex >= 0) {
          automationJobs.splice(jobIndex, 1);
        }
        return json(route, { status: 'success' });
      }
      if (/^\/api\/automation\/jobs\/\d+\/run-now$/.test(path) && method === 'POST') {
        return json(route, { status: 'started' });
      }
      if (path === '/api/automation/runs' && method === 'GET') {
        return json(route, {
          items: [{
            id: 77,
            job_id: 9,
            job_name: 'Job setmanal',
            started_at: '2026-03-25T08:00:00Z',
            status: 'partial_error',
            summary: { lot_execution: { with_findings: 1, without_findings: 0, query_errors: 0, unmapped: 0 } },
          }],
        });
      }
      if (path.startsWith('/api/automation/runs/') && path.endsWith('/lots') && method === 'GET') {
        return json(route, {
          items: [{
            lot: 'LOT_APP',
            detection_status: 'CON_HALLAZGOS',
            num_findings: 2,
            delivery_audience: 'provider',
            delivery_result: 'delivery_error',
            report_generated: true,
            email_sent: false,
            observaciones: 'SMTP KO',
          }],
        });
      }
      if (/^\/api\/automation\/runs\/\d+\/report$/.test(path) && method === 'GET') {
        const runId = path.split('/').at(-2) || 'run';
        return pdf(route, undefined, {
          'content-disposition': `attachment; filename="automation_run_${runId}_report.pdf"`,
        });
      }
      if (path.endsWith('/lots/export.csv') && method === 'GET') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado export CSV');
        }
        return route.fulfill({
          status: 200,
          contentType: 'text/csv',
          headers: {
            'content-disposition': 'attachment; filename="automation_run_77_lots.csv"',
          },
          body: 'lot,status\nLOT_APP,delivery_error\n',
        });
      }
      if (path === '/api/automation/tasks' && method === 'GET') return json(route, { items: [] });
      if (path === '/api/automation/severity-rules' && method === 'GET') {
        return json(route, { items: [{ id: 1, severity: 'ALT', create_task: true, task_priority: 'high', send_email: false, attach_report: true, recipients: [], conditions: { min_findings: 1 }, enabled: true }] });
      }
      if (path === '/api/automation/delivery-config' && method === 'GET') {
        if (scenario === 'load-error') {
          return jsonError(route, 'Fallo controlado carga SMTP');
        }
        return json(route, {
          smtp_host: 'smtp.local',
          smtp_port: 587,
          smtp_username: 'demo',
          smtp_password: 'secret',
          smtp_use_tls: true,
          from_email: 'oracle-audit@example.com',
          default_recipients: ['dba@example.com'],
          failure_notification_recipients: ['alerts@example.com'],
          auto_purge_enabled: true,
          history_retention_days: 30,
          retry_retention_days: 30,
        });
      }
      if (path === '/api/automation/delivery-config/test-email' && method === 'POST') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado SMTP');
        }
        return json(route, { status: 'success', message: 'Correu de prova enviat' });
      }
      if (path === '/api/automation/delivery-routes' && method === 'GET') {
        return json(route, {
          tic_summary_recipients: ['tic@example.com'],
          providers: [{ provider_code: 'LOT_APP', label: 'Aplicacions', emails: ['app@example.com'], enabled: true }],
        });
      }
      if (path === '/api/automation/master-lots' && method === 'GET') return json(route, { items: masterLots });
      if (path === '/api/automation/master-lots' && method === 'PUT') {
        const payload = request.postDataJSON() || {};
        masterLots.splice(0, masterLots.length, ...((payload.items || []).map((item) => ({ ...item }))));
        return json(route, { status: 'success', items: masterLots });
      }
      if (path === '/api/automation/schema-lots' && method === 'GET') return json(route, { items: schemaLots });
      if (path === '/api/automation/schema-lots' && method === 'PUT') {
        const payload = request.postDataJSON() || {};
        schemaLots.splice(0, schemaLots.length, ...((payload.items || []).map((item) => ({ ...item }))));
        return json(route, { status: 'success', items: schemaLots });
      }
      if (path === '/api/automation/master-lots/backfill-runs' && method === 'GET') {
        return json(route, { items: backfillRun ? [backfillRun] : [] });
      }
      if (path === '/api/automation/master-lots/backfill-preview' && method === 'GET') {
        backfillRun = {
          id: 10,
          summary: { distinct_lots: 1, to_create: 1, conflicts: 0 },
          items: [
            { lot_code: 'LOT_BACKFILL', action: 'create', conflict_code: null, schema_names: ['APP_BACKFILL'], selected: true },
          ],
        };
        return json(route, backfillRun);
      }
      if (path === '/api/automation/master-lots/backfill-apply' && method === 'POST') {
        const payload = request.postDataJSON() || {};
        const selectedLotCodes = new Set(payload.selected_lot_codes || []);
        if (selectedLotCodes.has('LOT_BACKFILL') && !masterLots.some((item) => item.code === 'LOT_BACKFILL')) {
          masterLots.push({ code: 'LOT_BACKFILL', label: 'LOT_BACKFILL', description: 'Lot creat des de backfill', enabled: true });
        }
        backfillRun = {
          ...backfillRun,
          items: (backfillRun?.items || []).map((item) => ({
            ...item,
            selected: selectedLotCodes.has(item.lot_code),
            action: selectedLotCodes.has(item.lot_code) ? 'created' : item.action,
          })),
        };
        return json(route, { status: 'success', applied: Array.from(selectedLotCodes) });
      }
      if (path === '/api/automation/lot-routes' && method === 'GET') {
        return json(route, { items: lotRoutes });
      }
      if (path === '/api/automation/lot-routes' && method === 'PUT') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado destinataris');
        }
        const payload = request.postDataJSON() || {};
        lotRoutes.splice(0, lotRoutes.length, ...((payload.items || []).map((item) => ({ ...item }))));
        return json(route, { status: 'success', items: lotRoutes });
      }
      if (path === '/api/automation/delivery-templates' && method === 'GET') {
        return json(route, { items: deliveryTemplates });
      }
      if (path === '/api/automation/delivery-templates' && method === 'PUT') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado plantilles');
        }
        const payload = request.postDataJSON() || {};
        deliveryTemplates.splice(0, deliveryTemplates.length, ...((payload.items || []).map((item) => ({ ...item }))));
        return json(route, { status: 'success', items: deliveryTemplates });
      }
      if (path === '/api/automation/delivery-attempts' && method === 'GET') return json(route, { items: [] });
      if (path === '/api/automation/retry-queue' && method === 'GET') {
        return json(route, { items: retryQueue });
      }
      if (/^\/api\/automation\/retry-queue\/\d+\/run-now$/.test(path) && method === 'POST') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado reintento');
        }
        const queueId = Number(path.split('/')[4]);
        const queueItem = retryQueue.find((item) => item.id === queueId);
        if (queueItem) {
          queueItem.status = 'done';
          queueItem.last_error = '';
        }
        return json(route, { status: 'success', message: 'Operació simulada' });
      }
      if (path === '/api/automation/maintenance/summary' && method === 'GET') {
        return json(route, {
          old_runs: 1,
          old_lot_statuses: 1,
          old_delivery_attempts: 1,
          old_retry_items: 1,
          retry_queue_total: retryQueue.length,
          retry_queue_pending: retryQueue.filter((item) => item.status === 'pending').length,
          retained_runs: 1,
          retained_retry_items: retryQueue.length,
          latest_run_at: '2026-03-25T08:00:00Z',
        });
      }
      if (path === '/api/automation/analytics/overview' && method === 'GET') {
        if (scenario === 'load-error') {
          return jsonError(route, 'Fallo controlado dashboard analytics');
        }
        return json(route, { runs: 2, total_findings: 3, lots_with_findings: 1, checks_with_errors: 0 });
      }
      if (path === '/api/automation/analytics/lots' && method === 'GET') return json(route, { items: [{ lot: 'LOT_APP', runs: 2, total_findings: 3 }] });
      if (path === '/api/automation/analytics/schemas' && method === 'GET') return json(route, { items: [{ schema_name: 'APP_USER', lot: 'LOT_APP', total_findings: 3 }] });
      if (path === '/api/automation/analytics/checks' && method === 'GET') return json(route, { items: [{ check_id: 'CHECK_01', executions: 2, total_findings: 3 }] });
      if (path === '/api/automation/analytics/monthly-report.pdf' && method === 'GET') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado PDF mensual');
        }
        return pdf(route);
      }
      if (path === '/api/automation/retry-queue' && method === 'POST') {
        if (scenario === 'error') {
          return jsonError(route, 'Fallo controlado alta reintent');
        }
        const payload = request.postDataJSON() || {};
        retryQueue.unshift({
          id: nextRetryQueueId++,
          run_id: payload.run_id || 77,
          lot: payload.lot || 'LOT_APP',
          audience: payload.audience || 'provider',
          attempt_number: 1,
          retry_mode: 'manual',
          status: 'pending',
          last_error: 'Pendent de reenviament',
        });
        return json(route, { status: 'success', message: 'Operació simulada' });
      }
      if (['POST', 'PUT', 'DELETE'].includes(method)) return json(route, { status: 'success', message: 'Operació simulada' });
    }

    unknownRequests.add(`${method} ${path}`);
    return json(route, { detail: `Unhandled mock for ${method} ${path}` }, 501);
  });

  return {
    assertNoUnhandledRequests() {
      if (unknownRequests.size > 0) {
        throw new Error(`Unhandled API mocks:\n${Array.from(unknownRequests).sort().join('\n')}`);
      }
    },
  };
}

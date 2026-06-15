import React from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  CheckCircle,
  Code,
  Cpu,
  Database,
  FileDown,
  FileText,
  HardDrive,
  Info,
  LayoutDashboard,
  Link as LinkIcon,
  Search,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  Terminal,
  Trash2,
  Zap,
} from 'lucide-react';

const Section = ({ title, icon: Icon, desc, children }) => (
  <div className="glass-card p-6">
    <div className="flex items-start justify-between gap-4 mb-5">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-primary/10 text-primary border border-primary/20">
          <Icon size={18} />
        </div>
        <div>
          <h3 className="text-lg font-extrabold tracking-tight">{title}</h3>
          {desc && <p className="text-xs text-muted-foreground mt-1">{desc}</p>}
        </div>
      </div>
    </div>
    {children}
  </div>
);

const Callout = ({ icon: Icon, title, children, tone = 'neutral' }) => (
  <div
    className={
      tone === 'warn'
        ? 'p-4 rounded-xl border border-yellow-500/20 bg-yellow-500/10'
        : tone === 'danger'
          ? 'p-4 rounded-xl border border-red-500/20 bg-red-500/10'
          : 'p-4 rounded-xl border border-white/10 bg-white/5'
    }
  >
    <div className="flex items-center gap-2 mb-2 font-bold">
      <Icon size={16} className={tone === 'warn' ? 'text-yellow-300' : tone === 'danger' ? 'text-red-300' : 'text-primary'} />
      <span className="text-sm">{title}</span>
    </div>
    <div className="text-sm text-muted-foreground leading-relaxed">{children}</div>
  </div>
);

const CodeExample = ({ label, children }) => (
  <div>
    {label && <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-2">{label}</p>}
    <pre className="bg-black/40 border border-white/10 rounded-lg p-3 text-xs font-mono overflow-auto whitespace-pre">
      {children}
    </pre>
  </div>
);

const DiagramNode = ({ icon: Icon, title, subtitle, tone = 'primary' }) => (
  <div
    className={
      tone === 'primary'
        ? 'glass-card px-4 py-3 border-primary/20 bg-primary/5'
        : tone === 'muted'
          ? 'glass-card px-4 py-3 bg-white/5'
          : 'glass-card px-4 py-3 border-yellow-500/20 bg-yellow-500/5'
    }
  >
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-lg bg-white/5 border border-white/10 text-primary">
        <Icon size={16} />
      </div>
      <div className="min-w-0">
        <div className="text-sm font-extrabold tracking-tight truncate">{title}</div>
        {subtitle && <div className="text-[11px] text-muted-foreground truncate">{subtitle}</div>}
      </div>
    </div>
  </div>
);

const DiagramArrow = ({ dir = 'right' }) => (
  <div className="flex items-center justify-center px-2 text-muted-foreground/60">
    {dir === 'down' ? <ArrowDown size={16} /> : <ArrowRight size={16} />}
  </div>
);

const DiagramRow = ({ children }) => (
  <div className="flex flex-wrap items-center gap-2">
    {children}
  </div>
);

const KV = ({ k, v }) => (
  <div className="flex items-start justify-between gap-6 py-2 border-b border-white/5 last:border-b-0">
    <div className="text-[10px] font-bold uppercase tracking-wider opacity-60">{k}</div>
    <div className="text-sm text-right max-w-[72%] text-muted-foreground">{v}</div>
  </div>
);

const MenuCard = ({ icon: Icon, name, objective, when, prereq, input, output, endpoints, example }) => (
  <div className="glass-card p-6">
    <div className="flex items-center gap-2 mb-4 text-primary font-bold">
      <Icon size={18} /> {name}
    </div>
    <div className="space-y-1">
      <KV k="Objectiu" v={objective} />
      <KV k="Quan usar-ho" v={when} />
      <KV k="Prerequisits" v={prereq} />
      <KV k="Entrada típica" v={input} />
      <KV k="Sortida" v={output} />
      <KV k="Endpoints" v={endpoints} />
    </div>
    {example && (
      <div className="mt-4">
        <CodeExample label="Exemple">{example}</CodeExample>
      </div>
    )}
  </div>
);

export default function TutorialView() {
  return (
    <div className="flex flex-col gap-8">
      <div className="glass-card p-8 border-l-4 border-primary">
        <h2 className="text-3xl font-extrabold tracking-tight mb-2">Tutorial</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Guia operativa i d’arquitectura del sistema unificat (React + FastAPI). Inclou: com començar, què fa cada menú,
          fluxos principals, exemples end-to-end i resolució de problemes.
        </p>
      </div>

      <Section title="Visió Ràpida (Quick-start)" icon={CheckCircle} desc="Si només tens 2 minuts, segueix això.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Callout icon={Info} title="Prerequisits">
            1. Perfil seleccionat a <b className="text-foreground">Connexió Activa</b>.<br />
            2. Si cal, afegeix connexió a <b className="text-foreground">Configuració</b>.<br />
            3. Per reports: cal haver executat una auditoria (Anàlisi o Deep Scan).
          </Callout>
          <Callout icon={CheckCircle} title="Checklist">
            <ul className="list-disc pl-5 space-y-1">
              <li>Test de connexió ràpid (Deep Scan) o “Provar connexió” (Configuració).</li>
              <li>Anàlisi: triatge ràpid d’esquemes.</li>
              <li>Deep Scan: evidència Q01..Q19 quan hi ha risc de drop.</li>
              <li>Generar Report: Markdown o PDF.</li>
            </ul>
          </Callout>
        </div>

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          <CodeExample label="Deep Scan (entrada)">
            {`APP_USER
APP_USER,CORE_DB
APP_USER CORE_DB`}
          </CodeExample>
          <CodeExample label="Connexió (format)">
            {`USER/PASSWORD@HOST:PORT/SERVICE`}
          </CodeExample>
        </div>

        <div className="mt-6">
          <Callout icon={FileDown} title="Resultat esperat">
            Després d’un Deep Scan, hauràs de veure un resultat per esquema (score, bloquejadors, dependències i traçabilitat).
            Llavors el botó <b className="text-foreground">Generar Report</b> et descarrega MD/PDF.
          </Callout>
        </div>
      </Section>

      <Section title="Arquitectura" icon={Cpu} desc="Com flueixen dades i responsabilitats entre mòduls.">
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            L’app és una SPA React servida per FastAPI (producció). FastAPI parla amb Oracle (si hi ha connexió),
            amb SQLite (Internal DB) i amb el sistema de fitxers (snapshots/reports).
          </p>

          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-3">Diagrama (components)</p>
            <DiagramRow>
              <DiagramNode icon={LayoutDashboard} title="Browser" subtitle="Usuari (UI)" />
              <DiagramArrow />
              <DiagramNode icon={Zap} title="React SPA" subtitle="src/web-app" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="FastAPI" subtitle="src/api/main.py" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="OracleDB" subtitle="Opcional (perfil)" tone="warn" />
              <DiagramArrow />
              <DiagramNode icon={HardDrive} title="Fitxers" subtitle="data/snapshots, data/reports" tone="muted" />
            </DiagramRow>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <DiagramNode icon={Terminal} title="SQLite Internal DB" subtitle="src/db/internal.db" tone="muted" />
              <DiagramArrow />
              <DiagramNode icon={Search} title="Repositori" subtitle="queries/knowledge" tone="muted" />
              <DiagramArrow />
              <DiagramNode icon={Trash2} title="Obsolets" subtitle="meta_objects" tone="muted" />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Callout icon={FileText} title="Dades clau">
              <ul className="list-disc pl-5 space-y-1">
                <li><code className="text-foreground">config/config.yaml</code>: paths de snapshots i reports.</li>
                <li><code className="text-foreground">src/db/internal.db</code>: consultes guardades + meta_objects.</li>
                <li><code className="text-foreground">data/snapshots/*.parquet</code>: dashboard legacy unificat.</li>
              </ul>
            </Callout>
            <Callout icon={Code} title="On és el codi">
              <ul className="list-disc pl-5 space-y-1">
                <li><code className="text-foreground">src/api/main.py</code>: endpoints HTTP + serve SPA.</li>
                <li><code className="text-foreground">src/api/audit_engine.py</code>: Deep Scan (Q01..Q19).</li>
                <li><code className="text-foreground">src/core/internal_db.py</code>: SQLite queries/meta_objects.</li>
                <li><code className="text-foreground">src/web-app/src/App.jsx</code>: menús/tabs.</li>
              </ul>
            </Callout>
          </div>

          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-3">Diagrama (IA)</p>
            <DiagramRow>
              <DiagramNode icon={Zap} title="React UI" subtitle="Analitzar amb IA" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="FastAPI" subtitle="/api/ai/chat" />
              <DiagramArrow />
              <DiagramNode icon={LinkIcon} title="OpenRouter" subtitle="Models free (rate-limit)" tone="warn" />
            </DiagramRow>
          </div>
        </div>
      </Section>

      <Section title="Mapa de Menús (què fa cada menú)" icon={LayoutDashboard} desc="Entrada, sortida, prerequisits, endpoints i un exemple.">
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <MenuCard
            icon={LayoutDashboard}
            name="Panell"
            objective="KPIs agregats i distribució de risc (vista executiva)."
            when="Quan vols impacte global i top candidats."
            prereq="Connexió configurada; idealment una llista d’esquemes a auditar."
            input="Llista d’esquemes (ActiveSchemas) + perfil."
            output="KPIs (GB totals, recovered, distribució, top candidates)."
            endpoints="/api/audit/dashboard-stats"
            example={`Schemas: APP_USER, CORE_DB\nAcció: Carregar estadístiques`}
          />

          <MenuCard
            icon={Zap}
            name="Anàlisi"
            objective="Auditoria transparent (resum) sobre esquemes seleccionats."
            when="Triage inicial abans d’un Deep Scan."
            prereq="Perfil vàlid; esquemes a analitzar."
            input="Esquemes (CSV) a la UI."
            output="Taula amb risc/decisió/score (resum)."
            endpoints="/api/audit"
            example={`Input UI: APP_USER, CORE_DB\nAcció: Iniciar auditoria`}
          />

          <MenuCard
            icon={Terminal}
            name="Consultes"
            objective="Editor SQL + execució + export Excel + anàlisi amb IA."
            when="Validació puntual (DBA/analista) i export de resultats."
            prereq="Perfil vàlid; permisos per executar SQL."
            input="SQL (text)."
            output="Resultats tabulars + Excel descarregable."
            endpoints="/api/queries/execute, /api/queries/export, /api/ai/chat"
            example={`SQL: SELECT username FROM dba_users\nAcció: Executar Consulta`}
          />

          <MenuCard
            icon={SlidersHorizontal}
            name="Optimització"
            objective="Espai reservat per mòdul de recomanacions de performance/optimització."
            when="Quan s’activi el mòdul (iteració futura)."
            prereq="Cap."
            input="—"
            output="—"
            endpoints="—"
            example={`Nota: si està buit, és normal.`}
          />

          <MenuCard
            icon={Activity}
            name="Snapshots"
            objective="Dashboard legacy: filtres + KPIs + export CSV sobre parquet."
            when="Quan treballes amb snapshots batch (històric)."
            prereq="Tenir parquet a data/snapshots."
            input="Filtres: schema/recommendation/min_score."
            output="Taula filtrada + CSV export."
            endpoints="/api/snapshots/*"
            example={`Filtres: schema=public, min_score=20\nAcció: Exportar CSV`}
          />

          <MenuCard
            icon={ShieldAlert}
            name="Deep Scan"
            objective="Auditoria 360 amb evidència Q01..Q19 (dependències, activitat, bloquejadors)."
            when="Abans de drop/cleanup quan cal prova robusta."
            prereq="Perfil vàlid; opcional: Test Connexió ràpid."
            input="Un esquema o llista (coma/espai)."
            output="Resultat per esquema + traçabilitat de queries."
            endpoints="/api/audit/deep-scan/*"
            example={`Input: APP_USER, CORE_DB\nAcció: Auditar`}
          />

          <MenuCard
            icon={Search}
            name="Repositori"
            objective="Repositori intern de consultes guardades (knowledge) + import bulk TXT."
            when="Quan vols reutilitzar consultes i mantenir un catàleg intern."
            prereq="Cap."
            input="Search term + import TXT."
            output="Llistat de consultes + explicació."
            endpoints="/api/knowledge, /api/queries/import"
            example={`Acció: Importar TXT Bulk\nResultat: consultes afegides al repositori`}
          />

          <MenuCard
            icon={Trash2}
            name="Obsolets"
            objective="Registre SQLite de meta_objects (candidats obsolets) amb alta manual."
            when="Quan vols traçabilitat de decisions i backlog intern."
            prereq="Cap."
            input="schema/object/type/reason/risk."
            output="Entrada persistent al registre."
            endpoints="/api/obsolets"
            example={`schema: APP_USER\nobjecte: TMP_USERS\ntipus: TABLE\nrisc: MEDIUM\nmotiu: taula temporal`}
          />

          <MenuCard
            icon={Settings}
            name="Configuració"
            objective="Models IA + OpenRouter key + alta de connexions Oracle."
            when="Quan falta un perfil o la IA està sense clau."
            prereq="Accés al fitxer env/config."
            input="Clau OpenRouter + cadena USER/PASSWORD@HOST:PORT/SERVICE."
            output="Perfil creat + IA configurada."
            endpoints="/api/config, /api/config/openrouter, /api/db/add, /api/db/test"
            example={`Perfil: PREPROD\nCadena: USER/PASS@HOST:1521/SVC\nAcció: Afegir des de cadena`}
          />
        </div>
      </Section>

      <Section title="Fluxos principals (diagrames)" icon={Activity} desc="Fluxos típics amb errors comuns i solució.">
        <div className="space-y-6">
          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-sm font-bold mb-3">Auditoria transparent (Anàlisi)</p>
            <DiagramRow>
              <DiagramNode icon={Zap} title="Anàlisi" subtitle="Esquemes" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="POST /api/audit" subtitle="resum" />
              <DiagramArrow />
              <DiagramNode icon={LayoutDashboard} title="Taula de resultats" subtitle="score/decisió" tone="muted" />
            </DiagramRow>
            <div className="mt-3 text-sm text-muted-foreground">
              Error típic: perfil no trobat. Solució: selecciona perfil existent o afegeix-lo a Configuració.
            </div>
          </div>

          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-sm font-bold mb-3">Deep Scan (single o bulk)</p>
            <DiagramRow>
              <DiagramNode icon={ShieldAlert} title="Deep Scan" subtitle="APP_USER,CORE_DB" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="GET /api/audit/deep-scan/*" subtitle="Q01..Q19" />
              <DiagramArrow />
              <DiagramNode icon={FileText} title="Evidència" subtitle="queries + bloquejadors" tone="muted" />
            </DiagramRow>
            <div className="mt-3 text-sm text-muted-foreground">
              Error típic: timeout/permís insuficient. Solució: prova “Test Connexió ràpid” i revisa permisos DBA.
            </div>
          </div>

          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-sm font-bold mb-3">Generar report (Markdown / PDF)</p>
            <DiagramRow>
              <DiagramNode icon={FileDown} title="Generar Report" subtitle="MD/PDF" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="POST /api/report/generate" subtitle="streaming" />
              <DiagramArrow />
              <DiagramNode icon={HardDrive} title="Descarrega" subtitle="fitxer al navegador" tone="muted" />
            </DiagramRow>
            <div className="mt-3 text-sm text-muted-foreground">
              Error típic: “No hi ha dades d’auditoria”. Solució: executa Anàlisi o Deep Scan abans.
            </div>
          </div>

          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            <p className="text-sm font-bold mb-3">Snapshots (filtrar + export CSV)</p>
            <DiagramRow>
              <DiagramNode icon={Activity} title="Snapshots" subtitle="filtres" />
              <DiagramArrow />
              <DiagramNode icon={Database} title="POST /api/snapshots/query" subtitle="paginació" />
              <DiagramArrow />
              <DiagramNode icon={FileDown} title="POST /api/snapshots/export.csv" subtitle="CSV" />
            </DiagramRow>
            <div className="mt-3 text-sm text-muted-foreground">
              Error típic: no hi ha parquet. Solució: genera snapshots a <code className="text-foreground">data/snapshots</code>.
            </div>
          </div>
        </div>
      </Section>

      <Section title="Exemples end-to-end" icon={FileText} desc="Dos escenaris complets amb resultat esperat.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass-card p-6">
            <p className="text-sm font-bold mb-2">1) Triage → Deep Scan → Report PDF</p>
            <ol className="list-decimal pl-5 space-y-2 text-sm text-muted-foreground">
              <li>Selecciona perfil a sidebar.</li>
              <li>Ves a <b className="text-foreground">Anàlisi</b> i audita <code className="text-foreground">APP_USER, CORE_DB</code>.</li>
              <li>Identifica l’esquema amb més risc/impacte.</li>
              <li>Ves a <b className="text-foreground">Deep Scan</b>, escriu l’esquema i prem <b className="text-foreground">Auditar</b>.</li>
              <li>Selecciona <b className="text-foreground">PDF</b> i prem <b className="text-foreground">Generar Report</b>.</li>
            </ol>
            <div className="mt-4">
              <Callout icon={CheckCircle} title="Resultat esperat">
                Descarrega un PDF amb evidència (Q01..Q19), bloquejadors i recomanació operativa.
              </Callout>
            </div>
          </div>

          <div className="glass-card p-6">
            <p className="text-sm font-bold mb-2">2) Snapshots → candidats → registrar a Obsolets</p>
            <ol className="list-decimal pl-5 space-y-2 text-sm text-muted-foreground">
              <li>Ves a <b className="text-foreground">Snapshots</b> i aplica <code className="text-foreground">min_score ≥ 70</code>.</li>
              <li>Identifica candidats (size/score/recommendation).</li>
              <li>Exporta CSV per compartir backlog.</li>
              <li>Ves a <b className="text-foreground">Obsolets</b> i registra l’objecte amb motiu i risc.</li>
            </ol>
            <div className="mt-4">
              <Callout icon={CheckCircle} title="Resultat esperat">
                L’entrada queda persistent a SQLite i apareix al llistat del registre.
              </Callout>
            </div>
          </div>
        </div>
      </Section>

      <Section title="FAQ / Troubleshooting" icon={AlertTriangle} desc="Problemes típics i solucions ràpides.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Callout icon={AlertTriangle} title="Connexió / perfil" tone="warn">
            Si veus “Perfil no trobat” o errors de connexió: ves a <b className="text-foreground">Configuració</b>, afegeix el perfil i prova connexió.
          </Callout>
          <Callout icon={AlertTriangle} title="IA (401/429/404)" tone="warn">
            Models free poden fer rate-limit (429) o no estar disponibles (404). Posa clau a Configuració i assumeix que cal reintentar.
          </Callout>
          <Callout icon={AlertTriangle} title="Report buit" tone="warn">
            Si “Generar Report” falla: executa abans una auditoria (Anàlisi o Deep Scan). El report no s’inventa dades.
          </Callout>
          <Callout icon={ShieldAlert} title="Què NO posar mai" tone="danger">
            No enganxis contrasenyes a captures o tickets. Usa el camp password (UI) i comparteix només errors/IDs/temps.
          </Callout>
        </div>
      </Section>
    </div>
  );
}


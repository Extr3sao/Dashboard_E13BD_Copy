import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight,
  BellRing,
  Boxes,
  FileText,
  History,
  LayoutDashboard,
  Mail,
  PlayCircle,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  Wand2,
} from 'lucide-react';
import MermaidBlock from './MermaidBlock.jsx';
import automationGuideMarkdown from '../docs/automation-guide.md?raw';

const screens = [
  {
    id: 'jobs',
    title: 'Jobs',
    icon: PlayCircle,
    kicker: 'Punt d’entrada',
    description: "Defineix quan s'executa l'auditoria, quin perfil usa i quins checks han d'entrar al run.",
    bullets: [
      'Crea, edita, activa o desactiva jobs.',
      'Executa manualment sense sortir de la pestanya.',
      'Configura timeout, planificació i política d’enviament.',
    ],
  },
  {
    id: 'lots',
    title: 'Lots i mapatge',
    icon: Boxes,
    kicker: 'Classificació',
    description: 'Relaciona schemas amb lots, detecta lots nous i manté el catàleg mestre que governa la distribució.',
    bullets: [
      'Mapeig schema -> lot.',
      'Backfill assistit per altes noves.',
      'Catàleg mestre de lots operatius.',
    ],
  },
  {
    id: 'recipients',
    title: 'Destinataris',
    icon: Mail,
    kicker: 'Entrega',
    description: 'Controla a qui arriba cada resum o informe i valida ràpidament si hi ha rutes mínimes configurades.',
    bullets: [
      'Rutes per lot.',
      'Resum TIC.',
      'Suport a reenviaments i revisió operativa.',
    ],
  },
  {
    id: 'templates',
    title: 'Plantilles',
    icon: Wand2,
    kicker: 'Comunicació',
    description: 'Ajusta el to i el contingut dels correus per cada tipus d’audiència sense tocar la lògica del job.',
    bullets: [
      'Missatge per lots amb troballes.',
      'Resum TIC.',
      'Reenviament manual i errors de generació.',
    ],
  },
  {
    id: 'history',
    title: 'Històric',
    icon: History,
    kicker: 'Traçabilitat',
    description: 'Consulta què ha passat a cada execució, descarrega resultats i filtra el detall per lot.',
    bullets: [
      'Estat del run.',
      'Detall per lot.',
      'Exportacions i anàlisi posterior.',
    ],
  },
  {
    id: 'retries',
    title: 'Reintents',
    icon: RefreshCcw,
    kicker: 'Recuperació',
    description: 'Reprocessa únicament els enviaments fallits o pendents sense repetir tota l’auditoria.',
    bullets: [
      'Cua de reintents.',
      'Gestió manual.',
      'Seguiment del resultat d’entrega.',
    ],
  },
];

const quickActions = [
  {
    title: 'Per començar',
    icon: Sparkles,
    tone: 'from-primary/15 via-white to-white',
    text: 'Si és la primera vegada, segueix l’ordre Jobs → Lots i mapatge → Destinataris → Plantilles.',
  },
  {
    title: 'Quan tocar plantilles',
    icon: FileText,
    tone: 'from-amber-500/15 via-white to-white',
    text: 'Edita plantilles quan vulguis canviar el missatge. Si el problema és de classificació o rutes, revisa abans lots i destinataris.',
  },
  {
    title: 'Si una entrega falla',
    icon: ShieldAlert,
    tone: 'from-emerald-500/15 via-white to-white',
    text: 'Comprova l’històric, revisa si falten rutes o adjunts i usa Reintents només quan el run ja és correcte.',
  },
];

const workflowSteps = [
  {
    title: 'Configura el job',
    description: 'Escull perfil, checks, planificació i format de report.',
  },
  {
    title: 'Relaciona schemas i lots',
    description: 'Mantén el mapatge tècnic i regularitza lots nous amb backfill.',
  },
  {
    title: 'Valida la distribució',
    description: 'Revisa destinataris, resum TIC i plantilles abans d’executar.',
  },
  {
    title: 'Executa i revisa',
    description: 'Llegeix l’històric, valida el detall per lot i exporta si cal.',
  },
];

const templates = [
  {
    label: 'Lot amb troballes',
    keyName: 'provider_with_findings',
    description: 'Missatge principal enviat quan el lot té incidències i s’adjunta l’informe individual.',
  },
  {
    label: 'Resum TIC',
    keyName: 'tic_summary',
    description: 'Correu resum amb el resultat global de l’execució per a l’Àrea TIC.',
  },
  {
    label: 'Reenviament manual',
    keyName: 'manual_resend',
    description: 'Plantilla usada quan es torna a enviar una entrega des de la cua de reintents.',
  },
  {
    label: "Lot sense troballes",
    keyName: 'provider_without_findings',
    description: 'Opcional. Informa que el lot s’ha avaluat correctament però sense anomalies.',
  },
  {
    label: "Error de generació de l'informe",
    keyName: 'job_generation_failure',
    description: "Avís quan no es pot generar l'informe i, per tant, no s'envia la distribució normal.",
  },
];

const systemDiagram = `flowchart LR
    A[Job] --> B[Execució d'auditoria]
    B --> C[Classificació per lot]
    C --> D[Resum TIC]
    C --> E[Informe del lot]
    C --> F[Decisió d'enviament]
    F --> G[Històric]
    F --> H[Reintents]
`;

const operatingDiagram = `flowchart LR
    A[Jobs] --> B[Lots i mapatge]
    B --> C[Destinataris]
    C --> D[Plantilles]
    D --> E[Execució]
    E --> F[Històric]
    F --> G[Reintents]
`;

const markdownComponents = {
  h2: ({ children }) => <h2 className="mt-10 text-2xl font-black tracking-tight text-slate-950">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-7 text-lg font-bold text-slate-950">{children}</h3>,
  p: ({ children }) => <p className="text-base leading-7 text-slate-700">{children}</p>,
  ul: ({ children }) => <ul className="ml-5 list-disc space-y-2 text-base leading-7 text-slate-700">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 list-decimal space-y-2 text-base leading-7 text-slate-700">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-bold text-slate-950">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="rounded-2xl border border-primary/20 bg-primary/10 px-5 py-4 text-slate-800 shadow-sm">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-slate-100">{children}</tbody>,
  th: ({ children }) => <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-[0.22em] text-slate-500">{children}</th>,
  td: ({ children }) => <td className="px-4 py-3 align-top text-sm leading-6 text-slate-700">{children}</td>,
  code: ({ inline, className, children }) => {
    const languageMatch = /language-(\w+)/.exec(className || '');
    const language = languageMatch?.[1];
    const value = String(children || '').replace(/\n$/, '');

    if (!inline && language === 'mermaid') {
      return (
        <div className="overflow-hidden rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm">
          <MermaidBlock chart={value} />
        </div>
      );
    }

    if (inline) {
      return <code className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[0.95em] font-semibold text-slate-900">{children}</code>;
    }

    return (
      <pre className="overflow-x-auto rounded-2xl border border-slate-200 bg-slate-950 px-4 py-4 text-sm text-slate-100">
        <code>{children}</code>
      </pre>
    );
  },
};

function GuideCard({ icon: Icon, title, kicker, description, bullets }) {
  return (
    <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.26em] text-primary">{kicker}</p>
          <h3 className="mt-2 text-xl font-black tracking-tight text-slate-950">{title}</h3>
        </div>
        <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white">
          <Icon size={20} />
        </span>
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-700">{description}</p>
      <ul className="mt-4 space-y-2">
        {bullets.map((bullet) => (
          <li key={bullet} className="flex items-start gap-2 text-sm leading-6 text-slate-700">
            <ArrowRight className="mt-1 shrink-0 text-primary" size={14} />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

const AutomationGuide = () => (
  <div className="mx-auto flex max-w-6xl flex-col gap-8">
    <section className="overflow-hidden rounded-[32px] border border-slate-200 bg-[radial-gradient(circle_at_top_left,rgba(192,0,0,0.14),transparent_32%),linear-gradient(135deg,#ffffff,#f8fafc)] p-6 shadow-sm md:p-8">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.9fr)]">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.35em] text-primary">
            <LayoutDashboard size={14} />
            Automatitzacions
          </p>
          <h1 className="mt-4 text-4xl font-black tracking-tight text-slate-950 md:text-5xl">
            Guia visual per entendre el mòdul sense perdre’t entre opcions.
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-slate-700 md:text-lg">
            Aquesta ajuda està pensada com una pantalla del producte: t’explica què fa cada àrea, quin ordre seguir i on has d’entrar segons el problema que vols resoldre.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <span className="rounded-full border border-primary/20 bg-white px-4 py-2 text-sm font-semibold text-slate-900">Jobs</span>
            <span className="rounded-full border border-primary/20 bg-white px-4 py-2 text-sm font-semibold text-slate-900">Lots i mapatge</span>
            <span className="rounded-full border border-primary/20 bg-white px-4 py-2 text-sm font-semibold text-slate-900">Destinataris</span>
            <span className="rounded-full border border-primary/20 bg-white px-4 py-2 text-sm font-semibold text-slate-900">Plantilles</span>
            <span className="rounded-full border border-primary/20 bg-white px-4 py-2 text-sm font-semibold text-slate-900">Històric i reintents</span>
          </div>
        </div>

        <div className="grid gap-4">
          {quickActions.map(({ title, icon: Icon, text, tone }) => (
            <article key={title} className={`rounded-[24px] border border-slate-200 bg-gradient-to-br ${tone} p-5 shadow-sm`}>
              <div className="flex items-start gap-3">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white">
                  <Icon size={18} />
                </span>
                <div>
                  <h2 className="text-lg font-black tracking-tight text-slate-950">{title}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-700">{text}</p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>

    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {workflowSteps.map((step, index) => (
        <article key={step.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Pas {index + 1}</p>
          <h2 className="mt-3 text-lg font-black tracking-tight text-slate-950">{step.title}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-700">{step.description}</p>
        </article>
      ))}
    </section>

    <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
      <article className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-white">
            <LayoutDashboard size={20} />
          </span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-primary">Arquitectura funcional</p>
            <h2 className="text-2xl font-black tracking-tight text-slate-950">Com circula la informació</h2>
          </div>
        </div>
        <div className="mt-6 overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50 p-4">
          <MermaidBlock chart={systemDiagram} />
        </div>
      </article>

      <article className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white">
            <BellRing size={20} />
          </span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-slate-500">Flux operatiu</p>
            <h2 className="text-2xl font-black tracking-tight text-slate-950">Quin ordre convé seguir</h2>
          </div>
        </div>
        <div className="mt-6 overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50 p-4">
          <MermaidBlock chart={operatingDiagram} />
        </div>
      </article>
    </section>

    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:p-8">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-white">
          <Boxes size={20} />
        </span>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-primary">Pantalles del mòdul</p>
          <h2 className="text-2xl font-black tracking-tight text-slate-950">Què hi ha a cada pantalla</h2>
        </div>
      </div>
      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        {screens.map((screen) => (
          <GuideCard key={screen.id} {...screen} />
        ))}
      </div>
    </section>

    <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
      <article className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white">
            <Wand2 size={20} />
          </span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-slate-500">Plantilles per audiència</p>
            <h2 className="text-2xl font-black tracking-tight text-slate-950">Noms visibles en català</h2>
          </div>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {templates.map((template) => (
            <article key={template.keyName} className="rounded-[24px] border border-slate-200 bg-slate-50 p-5">
              <p className="text-lg font-black tracking-tight text-slate-950">{template.label}</p>
              <p className="mt-1 inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500">
                {template.keyName}
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-700">{template.description}</p>
            </article>
          ))}
        </div>
      </article>

      <article className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,#fff7ed,#ffffff)] p-6 shadow-sm md:p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-500 text-white">
            <ShieldAlert size={20} />
          </span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-amber-700">Quan hi ha una incidència</p>
            <h2 className="text-2xl font-black tracking-tight text-slate-950">Què mirar primer</h2>
          </div>
        </div>
        <ul className="mt-6 space-y-3">
          <li className="rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700">
            Si falta un lot o un esquema, entra a <strong>Lots i mapatge</strong>.
          </li>
          <li className="rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700">
            Si el correu no arriba al destinatari correcte, revisa <strong>Destinataris</strong>.
          </li>
          <li className="rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700">
            Si el missatge no és adequat, modifica <strong>Plantilles</strong>.
          </li>
          <li className="rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700">
            Si el job ha acabat però una entrega ha fallat, usa <strong>Reintents</strong>.
          </li>
          <li className="rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700">
            Si vols saber què ha passat exactament, consulta <strong>Històric</strong>.
          </li>
        </ul>
      </article>
    </section>

    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:p-8">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-white">
          <FileText size={20} />
        </span>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-primary">Guia ampliada</p>
          <h2 className="text-2xl font-black tracking-tight text-slate-950">Detall funcional i glossari</h2>
        </div>
      </div>
      <div className="mt-6 prose prose-slate max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {automationGuideMarkdown}
        </ReactMarkdown>
      </div>
    </section>
  </div>
);

export default AutomationGuide;

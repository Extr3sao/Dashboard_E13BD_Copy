import React from 'react';
import { X } from 'lucide-react';

import PageGuideMindMap from './PageGuideMindMap.jsx';
import { GuideIcon } from './pageGuideIcons.js';

function SectionHeading({ eyebrow, title, description }) {
  return (
    <div className="mb-4">
      {eyebrow ? (
        <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-primary">{eyebrow}</p>
      ) : null}
      <h4 className="mt-2 text-xl font-extrabold tracking-tight text-foreground">{title}</h4>
      {description ? (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function FactCard({ fact }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/70 p-4">
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{fact.label}</p>
      <p className="mt-2 text-sm font-semibold leading-relaxed text-foreground">{fact.value}</p>
    </div>
  );
}

function BulletList({ items }) {
  if (!Array.isArray(items) || items.length === 0) return null;

  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item} className="flex gap-3 text-sm leading-relaxed text-muted-foreground">
          <span className="mt-[0.45rem] h-2 w-2 shrink-0 rounded-full bg-primary/50" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function ActionCard({ action }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/70 p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl border border-primary/20 bg-primary/5 p-2 text-primary">
          <GuideIcon icon={action.icon} size={16} />
        </div>
        <div>
          <h5 className="text-sm font-bold text-foreground">{action.title}</h5>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{action.description}</p>
        </div>
      </div>
    </article>
  );
}

function WorkflowStep({ step, index }) {
  return (
    <li className="relative flex gap-4">
      <div className="flex flex-col items-center">
        <div className="flex h-9 w-9 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-sm font-black text-primary">
          {index + 1}
        </div>
        <div className="mt-2 h-full w-px bg-gradient-to-b from-primary/25 to-transparent" />
      </div>
      <div className="pb-6 pt-1">
        <h5 className="text-sm font-bold text-foreground">{step.title}</h5>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.description}</p>
      </div>
    </li>
  );
}

function ArchitectureColumn({ title, items }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/70 p-4">
      <h5 className="text-sm font-bold text-foreground">{title}</h5>
      <div className="mt-4">
        <BulletList items={items} />
      </div>
    </div>
  );
}

function DataCard({ item }) {
  const toneClass = item.kind === 'output'
    ? 'border-emerald-500/20 bg-emerald-500/5'
    : item.kind === 'store'
      ? 'border-amber-500/20 bg-amber-500/5'
      : 'border-blue-500/20 bg-blue-500/5';

  return (
    <article className={`rounded-2xl border p-4 ${toneClass}`}>
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{item.label}</p>
      <p className="mt-2 text-sm leading-relaxed text-foreground">{item.detail}</p>
    </article>
  );
}

function RelationshipColumn({ title, items }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/70 p-4">
      <h5 className="text-sm font-bold text-foreground">{title}</h5>
      <div className="mt-4">
        <BulletList items={items} />
      </div>
    </div>
  );
}

function LegacySection({ section }) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/70 p-4">
      <h5 className="text-sm font-bold text-foreground">{section.title}</h5>
      {section.body ? (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{section.body}</p>
      ) : null}
      <div className="mt-4">
        <BulletList items={section.items} />
      </div>
    </article>
  );
}

export default function PageGuideDialog({
  guide,
  closeButtonRef,
  onClose,
}) {
  if (!guide) return null;

  const hasArchitecture = guide.architecture && Object.values(guide.architecture).some((items) => Array.isArray(items) && items.length > 0);
  const hasRelationships = guide.relationships && Object.values(guide.relationships).some((items) => Array.isArray(items) && items.length > 0);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={guide.title}
        className="max-h-[90vh] w-full max-w-6xl overflow-y-auto rounded-[32px] border border-white/10 bg-background shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 border-b border-white/10 bg-background/95 px-6 py-5 backdrop-blur">
          <div className="flex items-start justify-between gap-4">
            <div className="max-w-4xl">
              <p className="text-xs font-bold uppercase tracking-[0.32em] text-primary">Guía contextual</p>
              <h3 className="mt-2 text-3xl font-extrabold tracking-tight text-foreground">{guide.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{guide.summary}</p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              aria-label="Tanca ajuda"
              title="Tanca ajuda"
              onClick={onClose}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5 text-foreground transition hover:bg-white/10"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="space-y-8 px-6 py-6">
          <section className="rounded-[28px] border border-white/10 bg-gradient-to-br from-white via-white to-primary/5 p-6">
            <SectionHeading
              eyebrow="Resumen rápido"
              title="Qué hace esta página y para qué sirve"
              description={guide.purpose}
            />
            {Array.isArray(guide.highlights) && guide.highlights.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-3">
                {guide.highlights.map((fact) => (
                  <FactCard key={fact.label} fact={fact} />
                ))}
              </div>
            ) : null}
          </section>

          {guide.diagram ? (
            <div>
              <SectionHeading
                eyebrow="Mapa visual"
                title="Mapa mental y relaciones funcionales"
                description="El nodo central representa la pantalla activa. Las ramas resumen propósito, entradas, procesos, salidas y conexiones."
              />
              <PageGuideMindMap diagram={guide.diagram} />
            </div>
          ) : null}

          {Array.isArray(guide.actions) && guide.actions.length > 0 ? (
            <section>
              <SectionHeading
                eyebrow="Qué puedes hacer aquí"
                title="Acciones principales disponibles"
              />
              <div className="grid gap-4 lg:grid-cols-2">
                {guide.actions.map((action) => (
                  <ActionCard key={action.title} action={action} />
                ))}
              </div>
            </section>
          ) : null}

          {Array.isArray(guide.workflow) && guide.workflow.length > 0 ? (
            <section>
              <SectionHeading
                eyebrow="Cómo funciona"
                title="Flujo de trabajo de la pantalla"
              />
              <ol className="rounded-[28px] border border-white/10 bg-white/60 p-5">
                {guide.workflow.map((step, index) => (
                  <WorkflowStep key={step.title} step={step} index={index} />
                ))}
              </ol>
            </section>
          ) : null}

          {hasArchitecture ? (
            <section>
              <SectionHeading
                eyebrow="Cómo está construida"
                title="Componentes, datos, procesos e integraciones"
              />
              <div className="grid gap-4 xl:grid-cols-2">
                <ArchitectureColumn title="Componentes principales" items={guide.architecture.components} />
                <ArchitectureColumn title="Fuentes de datos" items={guide.architecture.dataSources} />
                <ArchitectureColumn title="Procesos internos" items={guide.architecture.processes} />
                <ArchitectureColumn title="Llamadas e integraciones" items={guide.architecture.integrations} />
              </div>
            </section>
          ) : null}

          {Array.isArray(guide.relatedData) && guide.relatedData.length > 0 ? (
            <section>
              <SectionHeading
                eyebrow="Datos relacionados"
                title="Inputs, estados persistidos y outputs"
              />
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {guide.relatedData.map((item) => (
                  <DataCard key={item.label} item={item} />
                ))}
              </div>
            </section>
          ) : null}

          {hasRelationships ? (
            <section>
              <SectionHeading
                eyebrow="Relación con otras páginas"
                title="Dependencias y efectos cruzados"
              />
              <div className="grid gap-4 xl:grid-cols-3">
                <RelationshipColumn title="Entradas desde otras vistas" items={guide.relationships.incoming} />
                <RelationshipColumn title="Impacto sobre otros módulos" items={guide.relationships.outgoing} />
                <RelationshipColumn title="Dependencias técnicas" items={guide.relationships.dependencies} />
              </div>
            </section>
          ) : null}

          {Array.isArray(guide.tips) && guide.tips.length > 0 ? (
            <section>
              <SectionHeading
                eyebrow="Buenas prácticas"
                title="Consejos de uso"
              />
              <div className="rounded-[28px] border border-white/10 bg-gradient-to-br from-white via-white to-amber-500/5 p-5">
                <BulletList items={guide.tips} />
              </div>
            </section>
          ) : null}

          {Array.isArray(guide.extraSections) && guide.extraSections.length > 0 ? (
            <section>
              <SectionHeading
                eyebrow="Contexto adicional"
                title="Notas específicas de la pantalla"
              />
              <div className="grid gap-4 lg:grid-cols-2">
                {guide.extraSections.map((section) => (
                  <LegacySection key={section.title} section={section} />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

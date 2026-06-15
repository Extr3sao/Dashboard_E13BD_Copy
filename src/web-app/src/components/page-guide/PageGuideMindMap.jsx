import React from 'react';

import { GuideIcon } from './pageGuideIcons.js';

const TONE_CLASS_MAP = {
  primary: 'border-primary/20 bg-primary/5 text-primary',
  data: 'border-blue-500/20 bg-blue-500/5 text-blue-700',
  process: 'border-amber-500/20 bg-amber-500/5 text-amber-700',
  related: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-700',
  warning: 'border-rose-500/20 bg-rose-500/5 text-rose-700',
  neutral: 'border-white/10 bg-white/5 text-foreground',
};

function toneClasses(tone) {
  return TONE_CLASS_MAP[tone] || TONE_CLASS_MAP.neutral;
}

function BranchCard({ branch }) {
  return (
    <article className={`page-guide-branch relative rounded-2xl border p-4 shadow-sm ${toneClasses(branch.tone)}`}>
      <div className="flex items-start gap-3">
        <div className="rounded-2xl border border-current/10 bg-white/70 p-2">
          <GuideIcon icon={branch.icon} size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-bold text-foreground">{branch.title}</h4>
          {branch.description ? (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{branch.description}</p>
          ) : null}
          {Array.isArray(branch.items) && branch.items.length > 0 ? (
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-muted-foreground">
              {branch.items.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current/50" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export default function PageGuideMindMap({ diagram }) {
  if (!diagram) return null;

  return (
    <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-white via-white to-primary/5 p-5">
      <div className="page-guide-map relative overflow-hidden rounded-[28px] border border-white/10 bg-white/70 px-4 py-6">
        <div className="page-guide-spine" aria-hidden="true" />

        <div className="relative mx-auto max-w-xl">
          <div className="page-guide-core rounded-[28px] border border-primary/20 bg-primary/5 p-6 shadow-sm">
            <div className="flex items-center gap-4">
              <div className="rounded-[22px] border border-primary/20 bg-white p-3 text-primary shadow-sm">
                <GuideIcon icon={diagram.center?.icon} size={22} />
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.28em] text-primary">Nodo central</p>
                <h3 className="mt-1 text-2xl font-extrabold tracking-tight text-foreground">{diagram.center?.label}</h3>
                {diagram.center?.subtitle ? (
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{diagram.center.subtitle}</p>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <div className="page-guide-map-grid mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(diagram.branches || []).map((branch) => (
            <BranchCard key={branch.title} branch={branch} />
          ))}
        </div>
      </div>
    </section>
  );
}

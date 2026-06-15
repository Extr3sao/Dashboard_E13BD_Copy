import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export function SectionToggleButton({ open, onClick, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"
    >
      {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      {label || (open ? 'Encongeix' : 'Desplega')}
    </button>
  );
}

export default function AutomationSection({ title, description, open, onToggle, actions, children, className = '' }) {
  return (
    <section className={`glass-card p-6 ${className}`.trim()}>
      <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <h4 className="text-lg font-bold text-foreground">{title}</h4>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {actions}
          <SectionToggleButton open={open} onClick={onToggle} />
        </div>
      </div>
      {open ? children : null}
    </section>
  );
}

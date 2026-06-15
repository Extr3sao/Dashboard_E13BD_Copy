import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Info } from 'lucide-react';

import { getPageHelp } from '../content/pageHelp.js';
import PageGuideDialog from './page-guide/PageGuideDialog.jsx';

function normalizeLegacyGuide(content) {
  if (!content) return null;
  if (content.diagram || content.purpose || content.actions || content.workflow || content.architecture) {
    return content;
  }

  return {
    title: content.title,
    summary: content.summary,
    purpose: content.summary,
    highlights: [],
    actions: [],
    workflow: [],
    architecture: {
      components: [],
      dataSources: [],
      processes: [],
      integrations: [],
    },
    relatedData: [],
    relationships: {
      incoming: [],
      outgoing: [],
      dependencies: [],
    },
    tips: [],
    extraSections: content.sections || [],
  };
}

export default function PageHelpButton({
  helpKey,
  helpContent,
  className = '',
  buttonTitle,
}) {
  const [open, setOpen] = useState(false);
  const triggerButtonRef = useRef(null);
  const closeButtonRef = useRef(null);
  const wasOpenRef = useRef(false);
  const content = useMemo(
    () => normalizeLegacyGuide(helpContent || getPageHelp(helpKey)),
    [helpContent, helpKey],
  );

  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  useEffect(() => {
    let frameId;

    if (open) {
      frameId = window.requestAnimationFrame(() => {
        closeButtonRef.current?.focus();
      });
    } else if (wasOpenRef.current) {
      frameId = window.requestAnimationFrame(() => {
        triggerButtonRef.current?.focus();
      });
    }

    wasOpenRef.current = open;

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [open]);

  if (!content) return null;

  const title = buttonTitle || `Ajuda: ${content.title}`;

  return (
    <>
      <button
        ref={triggerButtonRef}
        type="button"
        aria-label={title}
        title={title}
        onClick={() => setOpen(true)}
        className={`inline-flex h-10 w-10 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-primary transition hover:bg-primary/20 focus:outline-none focus:ring-2 focus:ring-primary/40 ${className}`.trim()}
      >
        <Info size={16} />
      </button>

      {open ? (
        <PageGuideDialog
          guide={content}
          closeButtonRef={closeButtonRef}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

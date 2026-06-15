import { useEffect, useId, useRef } from 'react';

let mermaidInitialized = false;
let mermaidModulePromise = null;

const loadMermaid = async () => {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((mod) => mod.default);
  }
  return mermaidModulePromise;
};

const ensureMermaidInitialized = (mermaid) => {
  if (mermaidInitialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    securityLevel: 'loose',
    fontFamily: 'Open Sans, Segoe UI, Arial, sans-serif',
  });
  mermaidInitialized = true;
};

const MermaidBlock = ({ chart }) => {
  const containerRef = useRef(null);
  const uid = useId().replace(/:/g, '');

  useEffect(() => {
    let isCancelled = false;
    const renderChart = async () => {
      const mermaid = await loadMermaid();
      ensureMermaidInitialized(mermaid);
      if (!containerRef.current) return;

      try {
        const renderId = `mermaid-${uid}-${Date.now()}`;
        const { svg } = await mermaid.render(renderId, chart);
        if (!isCancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (error) {
        if (!isCancelled && containerRef.current) {
          containerRef.current.innerHTML = '';
        }
        console.error('Error renderitzant Mermaid:', error);
      }
    };

    renderChart();
    return () => {
      isCancelled = true;
    };
  }, [chart, uid]);

  return (
    <div className="mermaid-wrapper">
      <div ref={containerRef} />
    </div>
  );
};

export default MermaidBlock;

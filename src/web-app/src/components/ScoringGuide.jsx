import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MermaidBlock from './MermaidBlock.jsx';
import scoringGuideMarkdown from '../docs/deep-scan-scoring.md?raw';

const markdownComponents = {
  h1: ({ children }) => <h1 className="scoring-guide-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="scoring-guide-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="scoring-guide-h3">{children}</h3>,
  p: ({ children }) => <p className="scoring-guide-p">{children}</p>,
  ul: ({ children }) => <ul className="scoring-guide-ul">{children}</ul>,
  ol: ({ children }) => <ol className="scoring-guide-ol">{children}</ol>,
  li: ({ children }) => <li className="scoring-guide-li">{children}</li>,
  table: ({ children }) => <table className="scoring-guide-table">{children}</table>,
  thead: ({ children }) => <thead className="scoring-guide-thead">{children}</thead>,
  tbody: ({ children }) => <tbody className="scoring-guide-tbody">{children}</tbody>,
  tr: ({ children }) => <tr className="scoring-guide-tr">{children}</tr>,
  th: ({ children }) => <th className="scoring-guide-th">{children}</th>,
  td: ({ children }) => <td className="scoring-guide-td">{children}</td>,
  code: ({ inline, className, children }) => {
    const languageMatch = /language-(\w+)/.exec(className || '');
    const language = languageMatch?.[1];
    const value = String(children || '').replace(/\n$/, '');

    if (!inline && language === 'mermaid') {
      return <MermaidBlock chart={value} />;
    }

    if (inline) {
      return <code className="scoring-guide-inline-code">{children}</code>;
    }

    return (
      <pre className="scoring-guide-pre">
        <code className="scoring-guide-code">{children}</code>
      </pre>
    );
  },
};

const ScoringGuide = () => (
  <div className="scoring-guide">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {scoringGuideMarkdown}
    </ReactMarkdown>
  </div>
);

export default ScoringGuide;

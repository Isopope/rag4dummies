import { MessageContent, MessageSource } from '@/types/chat';
import ChartRenderer from './ChartRenderer';
import { TableDisplay } from './TableDisplay';
import { FileCode, FileJson, Copy, Check, BookOpen } from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import type { Components } from 'react-markdown';

interface MessageRendererProps {
  content: MessageContent;
  /** Map citation_number → MessageSource, built from citation_infos at done event. */
  citationSources?: Record<number, MessageSource>;
  /** Called when a citation chip is clicked — opens the PdfGroundingModal. */
  onOpenViewer?: (source: MessageSource) => void;
}

const CodeBlock = ({ code, language }: { code: string; language?: string }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg overflow-hidden border border-border my-2">
      <div className="flex items-center justify-between px-4 py-2 bg-muted">
        <span className="text-xs font-mono text-muted-foreground">{language || 'code'}</span>
        <button onClick={handleCopy} className="text-muted-foreground hover:text-foreground transition-colors">
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto bg-muted/50 text-sm">
        <code className="font-mono text-foreground">{code}</code>
      </pre>
    </div>
  );
};

/** Badge cliquable pour les citations [[N]](url) générées par le backend. */
const CitationChip = ({
  num,
  href,
  source,
  onOpenViewer,
}: {
  num: string;
  href: string;
  source?: MessageSource;
  onOpenViewer?: (source: MessageSource) => void;
}) => {
  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (source && onOpenViewer) {
      e.preventDefault();
      onOpenViewer(source);
    }
    // else: default link opens in new tab
  };

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={`Voir la source ${num}${source ? ` — page ${(source.pageIdx ?? 0) + 1}` : ''}`}
      onClick={handleClick}
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 text-xs font-semibold rounded
                 bg-primary/10 text-primary border border-primary/20
                 hover:bg-primary/20 hover:border-primary/40 transition-colors
                 no-underline align-baseline cursor-pointer"
    >
      {num}
      <BookOpen className="w-2.5 h-2.5 opacity-60 flex-shrink-0" />
    </a>
  );
};

/** Composants ReactMarkdown partagés — gère citations + code blocks. */
const makeMarkdownComponents = (
  citationMap?: Record<number, MessageSource>,
  onOpenViewer?: (source: MessageSource) => void,
): Components => ({
  pre: ({ children }) => <div className="not-prose">{children}</div>,
  code: ({ className, children, ...props }) => {
    const isBlock = className?.startsWith('language-');
    if (isBlock) {
      const lang = className?.replace('language-', '') ?? '';
      return <CodeBlock code={String(children).replace(/\n$/, '')} language={lang} />;
    }
    return (
      <code className="text-primary bg-muted px-1 py-0.5 rounded text-xs font-mono" {...props}>
        {children}
      </code>
    );
  },
  a: ({ href, children }) => {
    // Détecte les liens de citation [[N]](url) — le texte rendu est "[N]"
    const text = Array.isArray(children)
      ? children.map(String).join('')
      : String(children ?? '');
    const match = text.match(/^\[(\d+)\]$/);
    if (match && href) {
      const num = parseInt(match[1], 10);
      const source = citationMap?.[num];
      return (
        <CitationChip
          num={match[1]}
          href={href}
          source={source}
          onOpenViewer={onOpenViewer}
        />
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
});

const JsonBlock = ({ data }: { data: unknown }) => {
  const [copied, setCopied] = useState(false);
  const jsonStr = JSON.stringify(data, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg overflow-hidden border border-border my-2">
      <div className="flex items-center justify-between px-4 py-2 bg-muted">
        <div className="flex items-center gap-2">
          <FileJson className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-mono text-muted-foreground">JSON</span>
        </div>
        <button onClick={handleCopy} className="text-muted-foreground hover:text-foreground transition-colors">
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto bg-muted/50 text-sm">
        <code className="font-mono text-foreground">{jsonStr}</code>
      </pre>
    </div>
  );
};

const MessageRenderer = ({ content, citationSources, onOpenViewer }: MessageRendererProps) => {
  const mdComponents = makeMarkdownComponents(citationSources, onOpenViewer);

  switch (content.type) {
    case 'text':
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert
            prose-p:leading-relaxed prose-p:my-1
            prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
            prose-h1:text-lg prose-h2:text-base prose-h3:text-sm
            prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
            prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:rounded-lg
            prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
            prose-blockquote:border-l-primary/40 prose-blockquote:text-muted-foreground
            prose-a:text-primary prose-a:no-underline hover:prose-a:underline
            prose-table:text-sm prose-th:py-1 prose-td:py-1
            prose-strong:font-semibold">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={mdComponents}
          >
            {content.text ?? ''}
          </ReactMarkdown>
        </div>
      );

    case 'chart':
      return content.chartData ? <ChartRenderer chartData={content.chartData} /> : null;

    case 'table':
      return content.tableData ? (
        <TableDisplay
          data={content.tableData.rows}
          columns={content.tableData.columns}
          title={content.tableData.title}
        />
      ) : null;

    case 'json':
      return <JsonBlock data={content.jsonData} />;

    case 'code':
      return <CodeBlock code={content.code || ''} language={content.language} />;

    case 'image':
      return (
        <div className="my-2 rounded-lg overflow-hidden border border-border max-w-md">
          <img src={content.imageUrl} alt="Response image" className="w-full h-auto" />
        </div>
      );

    case 'file':
      return (
        <div className="my-2 flex items-center gap-3 p-3 rounded-lg border border-border bg-muted/50 max-w-xs">
          <FileCode className="w-8 h-8 text-primary" />
          <div>
            <p className="text-sm font-medium">{content.fileName}</p>
            {content.fileSize && <p className="text-xs text-muted-foreground">{content.fileSize}</p>}
          </div>
        </div>
      );

    default:
      return null;
  }
};

export default MessageRenderer;

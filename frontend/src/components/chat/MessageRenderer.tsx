import { MessageContent } from '@/types/chat';
import ChartRenderer from './ChartRenderer';
import { TableDisplay } from './TableDisplay';
import { FileCode, FileJson, Copy, Check } from 'lucide-react';
import { useState } from 'react';

interface MessageRendererProps {
  content: MessageContent;
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

const MessageRenderer = ({ content }: MessageRendererProps) => {
  switch (content.type) {
    case 'text':
      return (
        <div className="prose prose-sm max-w-none">
          <p className="whitespace-pre-wrap leading-relaxed">{content.text}</p>
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

import { useCallback, useState } from 'react';

export function useCopyToClipboard(timeout = 2000) {
  const [isCopied, setIsCopied] = useState(false);

  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), timeout);
      } catch (err) {
        console.error('Failed to copy text:', err);
      }
    },
    [timeout],
  );

  return { isCopied, copy };
}

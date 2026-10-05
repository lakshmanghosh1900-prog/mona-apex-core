export type StreamEvent = {
  type: 'status' | 'token' | 'heal' | 'error' | 'result';
  node?: string;
  message?: string;
  text?: string;
  attempt?: number;
  answer?: string;
  verified?: boolean;
  attempts?: number;
  trace?: Array<Record<string, unknown>>;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  steps: string[];
  failed?: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

export async function* streamChat(
  message: string,
  context = '',
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context, remember: true }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`backend responded with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((entry) => entry.startsWith('data:'));
      if (!line) continue;
      const raw = line.slice(5).trim();
      if (raw === '[DONE]') return;
      try {
        yield JSON.parse(raw) as StreamEvent;
      } catch {
        continue;
      }
    }
  }
}

export async function health() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error('backend unreachable');
  return response.json();
}

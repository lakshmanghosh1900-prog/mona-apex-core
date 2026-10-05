'use client';

import { useEffect, useRef, useState } from 'react';
import { ChatMessage, health, streamChat } from '@/lib/api';

const NODE_LABEL: Record<string, string> = {
  plan: 'planning',
  act: 'executing',
  verify: 'verifying',
  heal: 'self-healing',
  deliver: 'delivering',
};

export default function Page() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const [status, setStatus] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    health()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setBusy(true);
    setStatus('connecting');

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text, steps: [] };
    const reply: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', steps: [] };
    setMessages((prev) => [...prev, userMessage, reply]);
    setOnline(true);

    try {
      for await (const event of streamChat(text)) {
        if (event.type === 'status') {
          const label = NODE_LABEL[event.node || ''] || event.message || event.node || '';
          setStatus(label);
          reply.steps = [...reply.steps, label];
        } else if (event.type === 'heal') {
          setStatus(`self-healing (attempt ${event.attempt ?? 1})`);
          reply.steps = [...reply.steps, `healed: ${event.message || event.node || 'retry'}`];
        } else if (event.type === 'token') {
          reply.content += event.text || '';
        } else if (event.type === 'error') {
          reply.failed = true;
          reply.content = reply.content || `Error: ${event.message || 'unknown failure'}`;
          reply.steps = [...reply.steps, 'error'];
        } else if (event.type === 'result') {
          if (event.answer && reply.content.trim() !== event.answer.trim()) {
            reply.content = event.answer;
          }
          reply.steps = [
            ...reply.steps,
            event.verified ? `verified in ${event.attempts ?? 0} attempt(s)` : 'best-effort answer',
          ];
        }
        setMessages((prev) => prev.map((m) => (m.id === reply.id ? { ...reply } : m)));
      }
    } catch (error) {
      reply.failed = true;
      reply.content = reply.content || `Backend unreachable: ${(error as Error).message}`;
      setOnline(false);
      setMessages((prev) => prev.map((m) => (m.id === reply.id ? { ...reply } : m)));
    } finally {
      setStatus('');
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className={`dot ${online ? 'online' : ''}`} />
          Mona
        </div>
        <span className="badge">{busy ? status || 'working' : online ? 'apex core online' : 'offline'}</span>
      </header>

      <section className="thread">
        {messages.length === 0 ? (
          <div className="empty">
            <h1>Apex Core ready</h1>
            <p>
              Self-healing orchestrator, long-term memory and a Telegram human-in-the-loop gate.
              Ask anything - Mona plans, executes, verifies and repairs its own steps.
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`row ${message.role}`}>
              <div className="bubble">{message.content || (busy ? '...' : '')}</div>
              {message.role === 'assistant' && message.steps.length > 0 && (
                <div className="meta">
                  {message.steps.map((step, index) => (
                    <span
                      key={`${step}-${index}`}
                      className={`chip ${
                        step.startsWith('healed') ? 'heal' : step === 'error' ? 'error' : step.startsWith('verified') ? 'ok' : ''
                      }`}
                    >
                      {step}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
        <div ref={bottomRef} />
      </section>

      <footer className="composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="Message Mona... (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={busy}
        />
        <button className="send" onClick={() => void send()} disabled={busy || !input.trim()}>
          {busy ? '...' : 'Send'}
        </button>
      </footer>
    </main>
  );
}

import { useMemo } from 'react';

import type { Event } from '../contract.ts';
import { EventType, Verdict } from '../contract.ts';

interface LedgerProps {
  events: Event[];
}

interface LedgerEntry {
  seq: number;
  t: number;
  tool: string;
  verdict: Verdict;
  reason: string;
}

function verdictValue(value: unknown): Verdict | null {
  return Object.values(Verdict).includes(value as Verdict) ? value as Verdict : null;
}

function deriveLedger(events: Event[]): LedgerEntry[] {
  const toolsByCall = new Map<string, string>();
  const toolsByTask = new Map<string, string>();
  const entries: LedgerEntry[] = [];

  for (const event of events) {
    if (event.type === EventType.TASK_DISPATCH) {
      const callId = event.payload.call_id;
      const taskId = event.payload.task_id;
      const tool = event.payload.tool;
      if (typeof tool === 'string') {
        if (typeof callId === 'string') toolsByCall.set(callId, tool);
        if (typeof taskId === 'string') toolsByTask.set(taskId, tool);
      }
      continue;
    }

    if (event.type !== EventType.VERDICT) continue;

    const verdict = verdictValue(event.payload.verdict);
    if (verdict === null) continue;

    const callId = typeof event.payload.call_id === 'string' ? event.payload.call_id : '';
    const taskId = typeof event.payload.task_id === 'string' ? event.payload.task_id : '';
    const explicitTool = event.payload.tool;
    const tool = typeof explicitTool === 'string'
      ? explicitTool
      : toolsByCall.get(callId) ?? toolsByTask.get(taskId) ?? (taskId || 'unknown tool');
    const reason = typeof event.payload.reason === 'string'
      ? event.payload.reason
      : 'No reason recorded.';

    entries.push({ seq: event.seq, t: event.t, tool, verdict, reason });
  }

  return entries;
}

const badgeStyles: Record<Verdict, string> = {
  [Verdict.COMMIT]: 'border-emerald-200 bg-emerald-100 text-emerald-800',
  [Verdict.STALE]: 'border-red-300 bg-red-600 text-white',
  [Verdict.DUPLICATE]: 'border-slate-300 bg-slate-200 text-slate-700',
  [Verdict.CANCELLED]: 'border-slate-300 bg-slate-200 text-slate-700',
  [Verdict.INVALID]: 'border-amber-300 bg-amber-100 text-amber-800',
};

export default function Ledger({ events }: LedgerProps) {
  const entries = useMemo(() => deriveLedger(events), [events]);

  return (
    <section className="flex min-h-[26rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-black/10">
      <header className="border-b border-slate-200 px-5 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Zone 2</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">Verdict ledger</h2>
      </header>

      <div className="flex-1 overflow-y-auto" aria-live="polite">
        {entries.length === 0 ? (
          <p className="px-5 py-10 text-sm text-slate-400">Waiting for a verdict…</p>
        ) : (
          <ol className="divide-y divide-slate-200">
            {entries.map((entry) => {
              const isStale = entry.verdict === Verdict.STALE;
              return (
                <li
                  key={entry.seq}
                  className={`px-5 py-4 ${isStale ? 'border-l-4 border-red-600 bg-red-50 py-5' : 'border-l-4 border-transparent'}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <time className="font-mono text-xs text-slate-500">{entry.t.toFixed(2)}s</time>
                    <span className={`rounded border px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${badgeStyles[entry.verdict]}`}>
                      {entry.verdict}
                    </span>
                    <span className={`font-mono text-xs ${isStale ? 'font-bold text-red-950' : 'font-medium text-slate-700'}`}>
                      {entry.tool}
                    </span>
                  </div>
                  <p className={`mt-2 break-words text-sm leading-6 ${isStale ? 'font-semibold text-red-950' : 'text-slate-600'}`}>
                    {entry.reason}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}

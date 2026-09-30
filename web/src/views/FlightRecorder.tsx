import { useMemo } from 'react';

import type { Event } from '../contract.ts';
import { EventType } from '../contract.ts';

interface FlightRecorderProps {
  events: Event[];
}

function summarize(event: Event): string {
  const p = event.payload;
  switch (event.type) {
    case EventType.STATE_PATCH:
      return `${(p.changed_paths as string[] | undefined)?.join(', ') ?? 'state changed'}`;
    case EventType.TASK_DISPATCH:
      return `${p.tool} · fp=${String(p.dispatch_fp).slice(0, 14)}${p.speculative ? ' · speculative' : ''}`;
    case EventType.TASK_FREEZE:
      return `${(p.frozen_tasks as string[] | undefined)?.length ?? 0} task(s) frozen · lead time ${p.lead_time_ms}ms`;
    case EventType.VERDICT:
      return `${p.tool ?? p.task_id} → ${String(p.verdict).toUpperCase()}`;
    case EventType.RECONCILE:
      return `invalidated ${(p.invalidated as string[] | undefined)?.length ?? 0}, added ${(p.added as string[] | undefined)?.length ?? 0}`;
    case EventType.COMPENSATING:
      return `${p.action} · ${p.reservation_id}`;
    case EventType.BARGE_IN:
      return `trigger=${p.trigger} · ${p.latency_ms}ms`;
    case EventType.SPEECH_ENVELOPE:
      return `${p.text_partial ?? ''}`;
    default:
      return '';
  }
}

const typeLabel: Record<string, string> = {
  [EventType.STATE_PATCH]: 'STATE_PATCH',
  [EventType.TASK_DISPATCH]: 'TASK_DISPATCH',
  [EventType.TASK_FREEZE]: 'TASK_FREEZE',
  [EventType.VERDICT]: 'VERDICT',
  [EventType.RECONCILE]: 'RECONCILE',
  [EventType.COMPENSATING]: 'COMPENSATING',
  [EventType.BARGE_IN]: 'BARGE_IN',
  [EventType.SPEECH_ENVELOPE]: 'SPEECH',
};

export default function FlightRecorder({ events }: FlightRecorderProps) {
  const rows = useMemo(() => events.slice().reverse(), [events]);

  return (
    <section className="panel flex max-h-96 flex-col overflow-hidden">
      <header className="panel-header flex items-center justify-between">
        <div>
          <p className="eyebrow">Every event, in order, hash-chained</p>
          <h2 className="panel-title">Flight recorder</h2>
        </div>
        <span className="flex items-center gap-1.5 rounded border border-red-900/50 bg-red-950/20 px-2.5 py-1 font-mono text-[11px] font-semibold text-red-400">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
          RECORDING
        </span>
      </header>
      <div className="flex-1 overflow-y-auto px-5 py-3 font-mono text-xs">
        {rows.length === 0 ? (
          <p className="py-6 text-dim">No events yet.</p>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {rows.map((event) => (
                <tr key={event.seq} className="animate-entry border-b border-line/60 align-top last:border-0">
                  <td className="whitespace-nowrap py-1.5 pr-3 text-dim">{event.t.toFixed(2)}s</td>
                  <td className="whitespace-nowrap py-1.5 pr-3 font-semibold text-cyan-300">{typeLabel[event.type] ?? event.type}</td>
                  <td className="py-1.5 text-slate-400">{summarize(event)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

import { useMemo } from 'react';

import type { Event } from '../contract.ts';
import { EventType, Verdict } from '../contract.ts';

interface IncidentReplayProps {
  allEvents: Event[];
  onReplay: () => void;
  disabled?: boolean;
}

interface IncidentSummary {
  initialUtterance: string | null;
  correctionUtterance: string | null;
  actionsAttempted: number;
  invalidated: number;
  committed: number;
  wrongActions: number;
}

function summarize(events: Event[]): IncidentSummary {
  const dispatchedTasks = new Set<string>();
  const committedCalls = new Set<string>();
  const invalidatedTasks = new Set<string>();
  let initialUtterance: string | null = null;
  let correctionUtterance: string | null = null;
  let wrongActions = 0;
  let seenFirstReconcile = false;

  for (const event of events) {
    if (event.type === EventType.STATE_PATCH) {
      const utterance = event.payload.utterance as string | undefined;
      if (utterance && initialUtterance === null) {
        initialUtterance = utterance;
      } else if (utterance && !seenFirstReconcile) {
        correctionUtterance = utterance;
      }
    }
    if (event.type === EventType.TASK_DISPATCH) {
      dispatchedTasks.add((event.payload.task_id as string) ?? event.seq.toString());
    }
    if (event.type === EventType.RECONCILE) {
      seenFirstReconcile = true;
      ((event.payload.invalidated as string[]) ?? []).forEach((id) => invalidatedTasks.add(id));
    }
    if (event.type === EventType.VERDICT) {
      const p = event.payload as { call_id?: string; verdict?: Verdict; agent?: string; wrong_action?: boolean };
      if (p.verdict === Verdict.COMMIT && typeof p.call_id === 'string') committedCalls.add(p.call_id);
      if (p.agent === 'replan' && p.wrong_action === true) wrongActions += 1;
    }
  }

  return {
    initialUtterance,
    correctionUtterance,
    actionsAttempted: dispatchedTasks.size,
    invalidated: invalidatedTasks.size,
    committed: committedCalls.size,
    wrongActions,
  };
}

export default function IncidentReplay({ allEvents, onReplay, disabled = false }: IncidentReplayProps) {
  const summary = useMemo(() => summarize(allEvents), [allEvents]);

  return (
    <section className="panel px-6 py-6 sm:px-8">
      <p className="eyebrow text-center">Incident #0421</p>
      {summary.correctionUtterance ? (
        <>
          <h2 className="mt-1.5 text-center font-mono text-lg font-semibold text-hi">User changed intent mid-execution</h2>
          <div className="mx-auto mt-4 max-w-xl space-y-2 font-mono text-sm">
            <p>
              <span className="text-dim">initial: </span>
              <span className="text-slate-300">&ldquo;{summary.initialUtterance}&rdquo;</span>
            </p>
            <p>
              <span className="text-dim">correction: </span>
              <span className="text-cyan-300">&ldquo;{summary.correctionUtterance}&rdquo;</span>
            </p>
          </div>
        </>
      ) : (
        <h2 className="mt-1.5 text-center font-mono text-lg font-semibold text-hi">Recorded execution trace</h2>
      )}

      <div className="mx-auto mt-6 grid max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="attempted" value={summary.actionsAttempted} />
        <Stat label="invalidated" value={summary.invalidated} tone="text-red-400" />
        <Stat label="committed" value={summary.committed} tone="text-emerald-400" />
        <Stat label="wrong actions" value={summary.wrongActions} tone={summary.wrongActions > 0 ? 'text-red-400' : 'text-emerald-400'} />
      </div>

      <div className="mt-6 flex justify-center">
        <button onClick={onReplay} disabled={disabled} className="btn-primary px-5 py-2 tracking-wider">
          &#9654; Replay incident
        </button>
      </div>
    </section>
  );
}

function Stat({ label, value, tone = 'text-hi' }: { label: string; value: number; tone?: string }) {
  return (
    <div className="subpanel px-3 py-3 text-center">
      <p className={`font-mono text-2xl font-bold tabular-nums ${tone}`}>{value}</p>
      <p className="eyebrow mt-1 text-[10px]">{label}</p>
    </div>
  );
}

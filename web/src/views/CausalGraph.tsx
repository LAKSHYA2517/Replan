import { useMemo, useState } from 'react';

import type { Event } from '../contract.ts';
import { EventType, Verdict } from '../contract.ts';

interface CausalGraphProps {
  events: Event[];
}

interface ActionNode {
  taskId: string;
  tool: string;
  dispatchFp: string;
  speculative: boolean;
  t: number;
  status: Verdict | 'pending';
  reason: string | null;
  dispatchedAtV: number | null;
  currentV: number | null;
  callId: string | null;
}

interface Generation {
  index: number;
  stateVersion: number;
  utterance: string | null;
  oldColumn: ActionNode[];
  newColumn: ActionNode[];
  adoptedTools: string[];
}

function buildActions(events: Event[]): Map<string, ActionNode> {
  const actions = new Map<string, ActionNode>();

  for (const event of events) {
    if (event.type === EventType.TASK_DISPATCH) {
      const p = event.payload as { task_id: string; tool: string; dispatch_fp: string; speculative?: boolean; call_id?: string };
      actions.set(p.task_id, {
        taskId: p.task_id,
        tool: p.tool,
        dispatchFp: p.dispatch_fp,
        speculative: p.speculative ?? false,
        t: event.t,
        status: 'pending',
        reason: null,
        dispatchedAtV: null,
        currentV: null,
        callId: p.call_id ?? null,
      });
    }
    if (event.type === EventType.VERDICT) {
      const p = event.payload as {
        task_id: string;
        call_id?: string;
        verdict: Verdict;
        reason: string;
        dispatched_at_v?: number;
        current_v?: number;
      };
      const existing = actions.get(p.task_id);
      if (existing && (existing.status === 'pending' || p.verdict !== Verdict.DUPLICATE)) {
        actions.set(p.task_id, {
          ...existing,
          status: p.verdict,
          reason: p.reason,
          dispatchedAtV: p.dispatched_at_v ?? null,
          currentV: p.current_v ?? null,
          callId: p.call_id ?? existing.callId,
        });
      }
    }
  }

  return actions;
}

function buildGenerations(events: Event[]): Generation[] {
  const actions = buildActions(events);
  const reconciles = events.filter((e) => e.type === EventType.RECONCILE);
  const generations: Generation[] = [];

  const firstReconcileSeq = reconciles[0]?.seq ?? Infinity;
  const gen0Tasks: ActionNode[] = [];
  for (const event of events) {
    if (event.type === EventType.TASK_DISPATCH && event.seq < firstReconcileSeq) {
      const p = event.payload as { task_id: string };
      const action = actions.get(p.task_id);
      if (action) gen0Tasks.push(action);
    }
  }

  const firstStatePatch = events.find((e) => e.type === EventType.STATE_PATCH);
  generations.push({
    index: 0,
    stateVersion: firstStatePatch?.state_version ?? 1,
    utterance: (firstStatePatch?.payload.utterance as string) ?? null,
    oldColumn: [],
    newColumn: gen0Tasks,
    adoptedTools: [],
  });

  reconciles.forEach((reconcileEvent, i) => {
    const p = reconcileEvent.payload as {
      invalidated?: string[];
      added?: string[];
      adopted?: string[];
    };
    const utterance = events.find(
      (e) => e.type === EventType.STATE_PATCH && e.state_version === reconcileEvent.state_version,
    )?.payload.utterance as string | undefined;

    generations.push({
      index: i + 1,
      stateVersion: reconcileEvent.state_version,
      utterance: utterance ?? null,
      oldColumn: (p.invalidated ?? []).map((id) => actions.get(id)).filter((a): a is ActionNode => a !== undefined),
      newColumn: (p.added ?? []).map((id) => actions.get(id)).filter((a): a is ActionNode => a !== undefined),
      adoptedTools: (p.adopted ?? []).map((id) => actions.get(id)?.tool ?? id),
    });
  });

  return generations;
}

const statusColor: Record<Verdict | 'pending', string> = {
  [Verdict.COMMIT]: 'border-emerald-500 text-emerald-300',
  [Verdict.STALE]: 'border-red-500 text-red-300',
  [Verdict.DUPLICATE]: 'border-yellow-500 text-yellow-300',
  [Verdict.CANCELLED]: 'border-slate-500 text-slate-400',
  [Verdict.INVALID]: 'border-amber-500 text-amber-300',
  pending: 'border-slate-600 text-slate-400',
};

const statusDot: Record<Verdict | 'pending', string> = {
  [Verdict.COMMIT]: 'bg-emerald-400',
  [Verdict.STALE]: 'bg-red-400',
  [Verdict.DUPLICATE]: 'bg-yellow-400',
  [Verdict.CANCELLED]: 'bg-slate-500',
  [Verdict.INVALID]: 'bg-amber-400',
  pending: 'bg-slate-500 animate-pulse',
};

function ActionNodeBox({
  action,
  faded,
  onSelect,
}: {
  action: ActionNode;
  faded: boolean;
  onSelect: (action: ActionNode) => void;
}) {
  return (
    <button
      onClick={() => onSelect(action)}
      className={`animate-entry flex w-full items-center gap-2 rounded border bg-black/30 px-2.5 py-1.5 text-left font-mono text-xs transition-opacity hover:opacity-100 ${statusColor[action.status]} ${faded ? 'opacity-45' : 'opacity-100'}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot[action.status]}`} />
      <span className="truncate text-hi">{action.tool}</span>
      <span className="ml-auto shrink-0 text-[10px] uppercase text-dim">{action.status}</span>
    </button>
  );
}

export default function CausalGraph({ events }: CausalGraphProps) {
  const generations = useMemo(() => buildGenerations(events), [events]);
  const [selected, setSelected] = useState<ActionNode | null>(null);

  return (
    <section className="panel relative overflow-hidden">
      <header className="panel-header">
        <p className="eyebrow">World state &rarr; plan &rarr; action &rarr; result &rarr; verdict</p>
        <h2 className="panel-title">Causal execution graph</h2>
      </header>

      <div className="flex">
        <div className="flex-1 overflow-x-auto px-6 py-6">
          <div className="relative border-l-2 border-cyan-900/60 pl-6">
            {generations.map((gen, i) => (
              <div key={gen.index} className="relative mb-8 last:mb-0">
                <span className="absolute -left-[31px] top-0 flex h-4 w-4 items-center justify-center rounded-full border-2 border-cyan-500 bg-replan-dark">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                </span>

                <div className="font-mono text-sm font-bold text-cyan-300">
                  STATE v{gen.stateVersion}
                  {i > 0 && <span className="eyebrow ml-2 text-[10px] font-normal tracking-wide">user correction</span>}
                </div>
                {gen.utterance && i > 0 && (
                  <p className="mt-0.5 font-mono text-xs text-dim">&ldquo;{gen.utterance}&rdquo;</p>
                )}

                {gen.adoptedTools.length > 0 && (
                  <p className="mt-1.5 font-mono text-[10px] text-dim">
                    adopted from previous plan: {gen.adoptedTools.join(', ')}
                  </p>
                )}

                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  {gen.oldColumn.length > 0 && (
                    <div className="subpanel border-red-900/50 bg-red-950/10 p-3">
                      <p className="eyebrow mb-2 text-[10px] tracking-wider text-red-400">
                        old execution &middot; invalidated
                      </p>
                      <div className="space-y-1.5">
                        {gen.oldColumn.map((action) => (
                          <div key={action.taskId} className="relative">
                            <span className="absolute -left-4 top-1/2 h-px w-3 bg-red-500/50" />
                            <ActionNodeBox action={action} faded onSelect={setSelected} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {gen.newColumn.length > 0 && (
                    <div className={`subpanel p-3 ${i > 0 ? 'border-emerald-900/50 bg-emerald-950/10' : ''}`}>
                      {i > 0 && (
                        <p className="eyebrow mb-2 text-[10px] tracking-wider text-emerald-400">
                          new execution &middot; active
                        </p>
                      )}
                      <div className="space-y-1.5">
                        {gen.newColumn.map((action) => (
                          <ActionNodeBox key={action.taskId} action={action} faded={false} onSelect={setSelected} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {selected && (
          <aside className="w-72 shrink-0 border-l border-line bg-black/30 px-4 py-4">
            <div className="flex items-center justify-between">
              <p className="eyebrow">Inspector</p>
              <button onClick={() => setSelected(null)} className="font-mono text-xs text-dim hover:text-hi">
                &times;
              </button>
            </div>
            <h3 className="panel-title">{selected.tool}</h3>
            <dl className="mt-3 space-y-2 font-mono text-xs">
              <Field label="task id" value={selected.taskId} />
              <Field label="timestamp" value={`${selected.t.toFixed(2)}s`} />
              <Field label="status" value={selected.status} tone={statusColor[selected.status]} />
              <Field label="dispatch fingerprint" value={selected.dispatchFp} />
              {selected.dispatchedAtV !== null && <Field label="dispatched at state" value={`v${selected.dispatchedAtV}`} />}
              {selected.currentV !== null && <Field label="current state" value={`v${selected.currentV}`} />}
              {selected.speculative && <Field label="speculative" value="yes" />}
              {selected.reason && (
                <div>
                  <dt className="text-dim">reason for decision</dt>
                  <dd className="mt-1 leading-relaxed text-slate-300">{selected.reason}</dd>
                </div>
              )}
            </dl>
          </aside>
        )}
      </div>
    </section>
  );
}

function Field({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-dim">{label}</dt>
      <dd className={`truncate text-right ${tone ? tone.split(' ').find((c) => c.startsWith('text-')) : 'text-hi'}`}>{value}</dd>
    </div>
  );
}

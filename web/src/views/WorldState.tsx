import { useMemo } from 'react';

import type { Event } from '../contract.ts';
import { EventType, Verdict } from '../contract.ts';

interface WorldStateProps {
  events: Event[];
}

type Bag = Record<string, unknown>;

interface Snapshot {
  version: number;
  slots: Bag;
  constraints: Bag;
  policy: Bag;
}

const emptySnapshot: Snapshot = { version: 0, slots: {}, constraints: {}, policy: {} };

function fold(events: Event[]): Snapshot {
  let snap = emptySnapshot;
  for (const event of events) {
    if (event.type !== EventType.STATE_PATCH) continue;
    const patch = (event.payload.patch as { slots?: Bag; constraints?: Bag; policy?: Bag }) ?? {};
    snap = {
      version: event.state_version,
      slots: { ...snap.slots, ...(patch.slots ?? {}) },
      constraints: { ...snap.constraints, ...(patch.constraints ?? {}) },
      policy: { ...snap.policy, ...(patch.policy ?? {}) },
    };
  }
  return snap;
}

function formatValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'YES' : 'NO';
  if (typeof value === 'number') return value.toLocaleString();
  return String(value);
}

function prettyKey(key: string): string {
  return key.replace(/_/g, ' ');
}

// The system fingerprints individual dispatches, not "the world state" as a
// single value — so rather than inventing a state-level fingerprint that
// doesn't exist in the runtime, we surface the real dispatch_fp behind the
// most recently committed call, labeled for what it actually is.
function lastCommittedFingerprint(events: Event[]): { fp: string; tool: string } | null {
  const dispatchFpByCall = new Map<string, { fp: string; tool: string }>();
  let last: { fp: string; tool: string } | null = null;

  for (const event of events) {
    if (event.type === EventType.TASK_DISPATCH) {
      const p = event.payload as { call_id?: string; tool?: string; dispatch_fp?: string };
      if (typeof p.call_id === 'string' && typeof p.dispatch_fp === 'string') {
        dispatchFpByCall.set(p.call_id, { fp: p.dispatch_fp, tool: p.tool ?? 'unknown' });
      }
    }
    if (event.type === EventType.VERDICT) {
      const p = event.payload as { call_id?: string; verdict?: Verdict };
      if (p.verdict === Verdict.COMMIT && typeof p.call_id === 'string') {
        const found = dispatchFpByCall.get(p.call_id);
        if (found) last = found;
      }
    }
  }
  return last;
}

export default function WorldState({ events }: WorldStateProps) {
  const current = useMemo(() => fold(events), [events]);
  const previous = useMemo(() => fold(events.slice(0, -1)), [events]);
  const fingerprint = useMemo(() => lastCommittedFingerprint(events), [events]);

  const lastEvent = events[events.length - 1];
  const changedPaths = useMemo(() => {
    if (!lastEvent || lastEvent.type !== EventType.STATE_PATCH) return new Set<string>();
    return new Set((lastEvent.payload.changed_paths as string[]) ?? []);
  }, [lastEvent]);

  const rows = useMemo(() => {
    const out: Array<{ path: string; key: string; value: unknown; prevValue: unknown; changed: boolean }> = [];
    (['slots', 'constraints', 'policy'] as const).forEach((bucket) => {
      Object.entries(current[bucket]).forEach(([key, value]) => {
        const path = `${bucket}.${key}`;
        out.push({
          path,
          key,
          value,
          prevValue: previous[bucket][key],
          changed: changedPaths.has(path),
        });
      });
    });
    return out;
  }, [current, previous, changedPaths]);

  return (
    <section className="panel flex flex-col overflow-hidden">
      <header className="panel-header flex items-center justify-between">
        <div>
          <p className="eyebrow">World state</p>
          <h2 className="panel-title">
            STATE <span className="text-cyan-400">v{current.version || 0}</span>
          </h2>
        </div>
        {fingerprint && (
          <div className="text-right">
            <p className="eyebrow text-[10px] tracking-[0.16em]">last committed fingerprint</p>
            <p className="font-mono text-xs text-cyan-300">
              {fingerprint.fp} <span className="text-dim">({fingerprint.tool})</span>
            </p>
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {rows.length === 0 ? (
          <p className="text-sm text-dim">No state committed yet.</p>
        ) : (
          <dl className="divide-y divide-line">
            {rows.map((row) => (
              <div key={row.path} className={`flex items-center justify-between py-2 ${row.changed ? 'animate-flash-row' : ''}`}>
                <dt className="font-mono text-xs uppercase tracking-wide text-dim">{prettyKey(row.key)}</dt>
                <dd className="font-mono text-sm text-hi">
                  {row.changed && row.prevValue !== undefined && row.prevValue !== row.value ? (
                    <span className="flex items-center gap-2">
                      <span className="text-dim line-through decoration-red-500/70">{formatValue(row.prevValue)}</span>
                      <span className="text-cyan-400">&rarr;</span>
                      <span className="font-bold text-cyan-300">{formatValue(row.value)}</span>
                    </span>
                  ) : (
                    formatValue(row.value)
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}

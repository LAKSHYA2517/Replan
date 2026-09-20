import React, { useState, useEffect, useRef } from 'react';
import {
  Event,
  EventType,
  Verdict,
  TaskStatus,
  Effect,
  PlanTask,
  CommitDecision,
} from '../contract.ts';
import { eventReducer, initialUIState, UIState } from '../useEventStream.ts';

interface ConsoleProps {
  events: Event[];
}

interface VersionItem {
  version: number;
  eventSeq: number;
  t: number;
  changedPaths: string[];
  summary: string;
}

export default function Console({ events }: ConsoleProps) {
  const [pinnedVersion, setPinnedVersion] = useState<number | null>(null);
  const [animatingAdopted, setAnimatingAdopted] = useState<Set<string>>(new Set());
  const ledgerEndRef = useRef<HTMLDivElement>(null);

  // Derive state based on pinned version or live events
  const currentEvents = React.useMemo(() => {
    if (pinnedVersion === null) return events;
    // Find highest event matching pinned version
    let lastIdx = -1;
    for (let i = 0; i < events.length; i++) {
      if (events[i].state_version <= pinnedVersion) {
        lastIdx = i;
      }
    }
    return lastIdx >= 0 ? events.slice(0, lastIdx + 1) : events;
  }, [events, pinnedVersion]);

  const state: UIState = React.useMemo(() => {
    return currentEvents.reduce(eventReducer, initialUIState);
  }, [currentEvents]);

  // Extract version stack from events
  const versionStack: VersionItem[] = React.useMemo(() => {
    const stack: VersionItem[] = [];
    const seenVersions = new Set<number>();

    events.forEach((ev) => {
      if (ev.type === EventType.STATE_PATCH) {
        const v = ev.state_version;
        const changedPaths = (ev.payload.changed_paths as string[]) || [];
        const patch = (ev.payload.patch as Record<string, Record<string, unknown>>) || {};
        let summary = changedPaths.join(', ');

        if (patch.slots?.locality) {
          summary = `slots.locality: → ${patch.slots.locality}`;
        } else if (patch.policy?.booking_enabled !== undefined) {
          summary = `policy.booking_enabled: → ${patch.policy.booking_enabled}`;
        }

        if (!seenVersions.has(v) || changedPaths.length > 0) {
          seenVersions.add(v);
          stack.unshift({
            version: v,
            eventSeq: ev.seq,
            t: ev.t,
            changedPaths,
            summary,
          });
        }
      }
    });

    // Ensure initial version 1 exists if not captured
    if (stack.length === 0 && events.length > 0) {
      stack.push({
        version: 1,
        eventSeq: 1,
        t: 0.0,
        changedPaths: ['initial_state'],
        summary: 'initial state',
      });
    }

    return stack;
  }, [events]);

  // Handle adoption animation when a RECONCILE event arrives
  useEffect(() => {
    const lastEvent = events[events.length - 1];
    if (lastEvent && lastEvent.type === EventType.RECONCILE) {
      const adopted = (lastEvent.payload.adopted as string[]) || [];
      if (adopted.length > 0) {
        setAnimatingAdopted(new Set(adopted));
        const timer = setTimeout(() => {
          setAnimatingAdopted(new Set());
        }, 800); // 400ms transition + lingering glow
        return () => clearTimeout(timer);
      }
    }
  }, [events]);

  // Auto-scroll ledger to bottom on new decisions
  useEffect(() => {
    if (pinnedVersion === null) {
      ledgerEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [state.decisions.length, pinnedVersion]);

  const getTaskStatusStyle = (status: TaskStatus) => {
    switch (status) {
      case TaskStatus.RUNNING:
        return 'bg-blue-950/60 border-blue-500 text-blue-200 shadow-blue-500/20';
      case TaskStatus.FROZEN:
        return 'bg-purple-950/70 border-purple-500 text-purple-200 hatched-pattern shadow-purple-500/20';
      case TaskStatus.DONE:
        return 'bg-emerald-950/60 border-emerald-500 text-emerald-200 shadow-emerald-500/20';
      case TaskStatus.INVALIDATED:
      case TaskStatus.CANCELLED:
        return 'bg-red-950/40 border-red-800/80 text-red-400 opacity-60 line-through';
      default:
        return 'bg-slate-900 border-slate-700 text-slate-400';
    }
  };

  const getEffectBadge = (effect?: Effect) => {
    switch (effect) {
      case Effect.IRREVERSIBLE:
        return 'bg-rose-950 text-rose-300 border-rose-800';
      case Effect.REVERSIBLE:
        return 'bg-amber-950 text-amber-300 border-amber-800';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="w-full bg-slate-950/90 rounded-xl border border-slate-800/90 p-5 shadow-2xl flex flex-col space-y-4 font-sans">
      {/* Top Reconcile Live Counters Bar */}
      <div className="bg-slate-900/80 border border-slate-800 p-3 rounded-lg flex items-center justify-between font-mono text-xs">
        <div className="flex items-center space-x-2">
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
          <span className="font-semibold text-white uppercase text-[11px] tracking-wider">
            Reconciliation Live Counters
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div className="px-3 py-1 bg-emerald-950/50 border border-emerald-800/60 rounded">
            <span className="text-emerald-400 text-[10px] block uppercase">Adopted (Preserved)</span>
            <span className="text-emerald-300 font-bold text-sm">
              {state.reconcileMetrics.adopted.length}
            </span>
          </div>

          <div className="px-3 py-1 bg-cyan-950/50 border border-cyan-800/60 rounded">
            <span className="text-cyan-400 text-[10px] block uppercase">Reused (Cache Hits)</span>
            <span className="text-cyan-300 font-bold text-sm">
              {state.reconcileMetrics.reused.length}
            </span>
          </div>

          <div className="px-3 py-1 bg-rose-950/50 border border-rose-800/60 rounded">
            <span className="text-rose-400 text-[10px] block uppercase">Invalidated</span>
            <span className="text-rose-300 font-bold text-sm">
              {state.reconcileMetrics.invalidated.length}
            </span>
          </div>

          <div className="px-3 py-1 bg-amber-950/50 border border-amber-800/60 rounded">
            <span className="text-amber-400 text-[10px] block uppercase">Compensated</span>
            <span className="text-amber-300 font-bold text-sm">
              {state.reconcileMetrics.compensate.length}
            </span>
          </div>
        </div>
      </div>

      {/* Three-Column Inspection Cockpit */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[500px]">
        {/* Column 1: State Version Stack (3 Cols) */}
        <div className="lg:col-span-3 bg-slate-900/60 border border-slate-800 rounded-lg p-3.5 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
            <div className="flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              <h4 className="font-semibold text-slate-200">Version Stack</h4>
            </div>
            {pinnedVersion !== null ? (
              <button
                onClick={() => setPinnedVersion(null)}
                className="px-2 py-0.5 text-[10px] font-bold bg-cyan-600 hover:bg-cyan-500 text-white rounded shadow animate-pulse"
              >
                LIVE ✕
              </button>
            ) : (
              <span className="text-[10px] text-slate-500 font-mono">Newest First</span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-xs">
            {versionStack.length === 0 ? (
              <div className="text-slate-500 text-center py-8 italic">No versions yet</div>
            ) : (
              versionStack.map((item) => {
                const isSelected =
                  pinnedVersion === item.version || (pinnedVersion === null && item.version === state.version);
                return (
                  <button
                    key={item.version}
                    onClick={() => setPinnedVersion(item.version)}
                    className={`w-full text-left p-2.5 rounded-lg border transition-all ${
                      isSelected
                        ? 'bg-cyan-950/80 border-cyan-500 text-cyan-200 shadow-md shadow-cyan-950'
                        : 'bg-slate-950/70 border-slate-800 hover:border-slate-700 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-white text-xs">v{item.version}</span>
                      <span className="text-[10px] text-slate-400">event #{item.eventSeq}</span>
                    </div>
                    <div className="text-[11px] text-cyan-300/90 truncate font-sans">
                      {item.summary}
                    </div>
                    <div className="text-[9.5px] text-slate-500 mt-1">t={item.t.toFixed(2)}s</div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Column 2: Plan DAG with Adoption Animation (5 Cols) */}
        <div className="lg:col-span-5 bg-slate-900/60 border border-slate-800 rounded-lg p-3.5 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
            <div className="flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              <h4 className="font-semibold text-slate-200">Execution Plan DAG</h4>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Plan: {state.activePlanId}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto pr-1 space-y-3 p-1">
            {Object.keys(state.tasks).length === 0 ? (
              <div className="text-slate-500 text-center py-16 font-mono text-xs italic">
                No active plan tasks
              </div>
            ) : (
              Object.values(state.tasks).map((task: PlanTask) => {
                const isAdopted = animatingAdopted.has(task.id);
                return (
                  <div
                    key={task.id}
                    className={`p-3 rounded-lg border transition-all duration-400 shadow-sm relative ${getTaskStatusStyle(
                      task.status
                    )} ${
                      isAdopted
                        ? 'translate-x-3 scale-[1.02] ring-2 ring-emerald-400 bg-emerald-950/80 shadow-emerald-500/40'
                        : 'translate-x-0'
                    }`}
                  >
                    {isAdopted && (
                      <span className="absolute -top-2 -right-2 px-1.5 py-0.2 text-[9px] font-bold bg-emerald-500 text-slate-950 rounded uppercase shadow">
                        Preserved & Adopted
                      </span>
                    )}

                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-bold text-white font-mono text-xs">{task.tool}</span>
                          <span
                            className={`px-1.5 py-0.2 text-[9.5px] rounded border font-mono uppercase ${getEffectBadge(
                              undefined // effect can be added if attached to task payload
                            )}`}
                          >
                            PURE
                          </span>
                          {task.speculative && (
                            <span className="px-1.5 py-0.2 text-[9.5px] rounded bg-purple-950 text-purple-300 border border-purple-800 font-mono font-semibold">
                              SPEC
                            </span>
                          )}
                        </div>

                        <div className="text-[11px] text-slate-300 font-mono mt-1">
                          id: <span className="text-slate-400">{task.id}</span>
                          {task.call_id && (
                            <span className="ml-2 text-slate-400">· call: {task.call_id}</span>
                          )}
                        </div>
                      </div>

                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase border">
                        {task.status}
                      </span>
                    </div>

                    {/* Resolved Arg Spec & Fingerprint */}
                    <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10.5px] font-mono text-slate-400 flex items-center justify-between">
                      <div className="truncate max-w-[200px]">
                        args: {JSON.stringify(task.arg_spec)}
                      </div>
                      {task.dispatch_fp && (
                        <span className="text-cyan-400/90 text-[10px]">
                          fp:{task.dispatch_fp.slice(0, 10)}…
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Column 3: Monospace Auto-scrolling Verdict Ledger (4 Cols) */}
        <div className="lg:col-span-4 bg-slate-900/60 border border-slate-800 rounded-lg p-3.5 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
            <div className="flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <h4 className="font-semibold text-slate-200">Verdict Ledger</h4>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              {state.decisions.length} decisions
            </span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-[11px]">
            {state.decisions.length === 0 ? (
              <div className="text-slate-500 text-center py-16 italic">No verdicts adjudicated</div>
            ) : (
              state.decisions.map((dec: CommitDecision, idx: number) => {
                const isStale = dec.verdict === Verdict.STALE;
                const isCommit = dec.verdict === Verdict.COMMIT;
                const isDup = dec.verdict === Verdict.DUPLICATE;

                return (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-lg border transition-all ${
                      isStale
                        ? 'bg-red-950/70 border-red-500 text-red-200 shadow-md shadow-red-950 ring-1 ring-red-500/50'
                        : isCommit
                        ? 'bg-emerald-950/40 border-emerald-700/60 text-emerald-300'
                        : isDup
                        ? 'bg-amber-950/40 border-amber-700/60 text-amber-300'
                        : 'bg-slate-950/80 border-slate-800 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center space-x-2">
                        <span
                          className={`font-bold px-1.5 py-0.2 rounded text-[10px] uppercase ${
                            isStale
                              ? 'bg-red-600 text-white'
                              : isCommit
                              ? 'bg-emerald-600 text-white'
                              : 'bg-amber-600 text-black'
                          }`}
                        >
                          {dec.verdict}
                        </span>
                        <span className="text-slate-300 font-semibold">{dec.task_id}</span>
                      </div>
                      <span className="text-[10px] text-slate-400">t={dec.t.toFixed(2)}s</span>
                    </div>

                    {/* Human Readable / Mathematical Reason String */}
                    <p
                      className={`text-[10.5px] leading-relaxed mt-1 font-mono break-words ${
                        isStale ? 'text-red-300 font-semibold' : 'text-slate-300'
                      }`}
                    >
                      {dec.reason}
                    </p>

                    <div className="text-[9px] text-slate-500 mt-1 flex justify-between">
                      <span>call: {dec.call_id}</span>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={ledgerEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}

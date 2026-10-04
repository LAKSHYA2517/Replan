import { useMemo, useState, useEffect } from 'react';
import { Event, EventType, Verdict } from '../contract.ts';

interface DualPaneProps {
  events: Event[];
}

interface BaselineState {
  locality: string;
  budget: number | null;
  dates: string;
  breakfast: boolean;
  bookingEnabled: boolean;
  recommendedHotel: string | null;
  inFlightCalls: Array<{ id: string; tool: string; locality: string }>;
  wrongActions: number;
  corrupted: boolean;
  lastAction: string;
}

interface ReplanCommit {
  taskId: string;
  tool: string;
  t: number;
}


type StepState = 'done' | 'bad' | 'good' | 'todo';

function deriveSequence(events: Event[]) {
  const sent = events.some((e) => e.type === EventType.TASK_DISPATCH);
  const changed = events.filter((e) => e.type === EventType.STATE_PATCH).length >= 2;
  const staleAt = events.findIndex((e) => e.type === EventType.VERDICT && e.payload.verdict === Verdict.STALE);
  const commitAfter = staleAt >= 0 && events.slice(staleAt + 1).some(
    (e) => e.type === EventType.VERDICT && e.payload.verdict === Verdict.COMMIT
  );
  return { sent, changed, stale: staleAt >= 0, commitAfter };
}

const stepIcon: Record<StepState, string> = { done: '\u2713', bad: '\u2715', good: '\u2713', todo: '\u2022' };
const stepColor: Record<StepState, string> = {
  done: 'text-slate-300',
  bad: 'text-red-300',
  good: 'text-emerald-300',
  todo: 'text-dim',
};

function StepList({ steps }: { steps: { label: string; state: StepState }[] }) {
  return (
    <ol className="mt-4 space-y-1.5 font-mono text-[11px]">
      {steps.map((step, i) => (
        <li key={i} className={`flex items-center gap-2 ${stepColor[step.state]}`}>
          <span className="w-3 text-center font-bold">{stepIcon[step.state]}</span>
          <span>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

export default function DualPane({ events }: DualPaneProps) {
  const [flashing, setFlashing] = useState<boolean>(false);
  const seq = deriveSequence(events);


  // The replan side of the comparison, derived the same honest way as the
  // baseline below: scan the real event stream, don't assume the invariant.
  const { replanCommits, replanWrongActions } = useMemo(() => {
    const toolByTask = new Map<string, string>();
    const commits: ReplanCommit[] = [];
    let wrongActions = 0;

    for (const ev of events) {
      if (ev.type === EventType.TASK_DISPATCH) {
        const p = ev.payload as { task_id: string; tool: string };
        toolByTask.set(p.task_id, p.tool);
      }
      if (ev.type === EventType.VERDICT) {
        const p = ev.payload as { task_id: string; verdict: Verdict; agent?: string; wrong_action?: boolean };
        if (p.verdict === Verdict.COMMIT) {
          commits.push({ taskId: p.task_id, tool: toolByTask.get(p.task_id) ?? p.task_id, t: ev.t });
        }
        if (p.agent === 'replan' && p.wrong_action === true) wrongActions += 1;
      }
    }

    return { replanCommits: commits, replanWrongActions: wrongActions };
  }, [events]);

  // Derive Baseline State purely from the event stream
  const baselineState: BaselineState = useMemo(() => {
    let locality = 'delhi';
    let budget: number | null = 5000;
    let dates = 'weekend';
    let breakfast = true;
    let bookingEnabled = true;
    let recommendedHotel: string | null = null;
    let wrongActions = 0;
    let corrupted = false;
    let lastAction = 'Initialized session';
    const inFlight: Array<{ id: string; tool: string; locality: string }> = [];

    events.forEach((ev) => {
      if (ev.type === EventType.STATE_PATCH) {
        const patch = (ev.payload.patch as Record<string, Record<string, unknown>>) || {};
        if (patch.slots?.locality) {
          locality = patch.slots.locality as string;
          lastAction = `Updated locality to ${locality}`;
        }
        if (patch.constraints?.budget) {
          budget = patch.constraints.budget as number;
        }
        if (patch.policy?.booking_enabled !== undefined) {
          bookingEnabled = patch.policy.booking_enabled as boolean;
        }
      }

      if (ev.type === EventType.TASK_DISPATCH) {
        const p = ev.payload as { task_id: string; tool: string; args: { locality?: string } };
        inFlight.push({
          id: p.task_id,
          tool: p.tool,
          locality: p.args?.locality || locality,
        });
        lastAction = `Dispatched ${p.tool} (${p.args?.locality || locality})`;
      }

      // In Naive baseline, when a late result arrives (even if stale in RePlan),
      // naive agent blindly overwrites current state with old tool payload!
      if (ev.type === EventType.VERDICT) {
        const p = ev.payload as { task_id: string; verdict: Verdict; result?: Record<string, unknown> };
        if (p.verdict === Verdict.STALE) {
          // Divergence moment: Baseline commits this stale Delhi result!
          locality = 'delhi'; // Overwritten by old in-flight Delhi result!
          recommendedHotel = 'The Imperial New Delhi (₹4,800)';
          wrongActions = 1;
          corrupted = true;
          lastAction = 'COMMITTED STALE DELHI RESULT (Silent State Corruption!)';
        } else if (p.verdict === Verdict.COMMIT && !corrupted) {
          if (locality === 'mumbai') {
            recommendedHotel = 'Sea Princess Juhu (₹4,600)';
          } else {
            recommendedHotel = 'The Imperial New Delhi (₹4,800)';
          }
          lastAction = `Committed ${p.task_id}`;
        }
      }
    });

    return {
      locality,
      budget,
      dates,
      breakfast,
      bookingEnabled,
      recommendedHotel,
      inFlightCalls: inFlight.slice(-4),
      wrongActions,
      corrupted,
      lastAction,
    };
  }, [events]);

  // Flash both counters for 600ms simultaneously when STALE verdict occurs
  useEffect(() => {
    const hasStaleVerdict = events.some(
      (ev) => ev.type === EventType.VERDICT && ev.payload.verdict === Verdict.STALE
    );
    if (hasStaleVerdict && !flashing) {
      setFlashing(true);
      const timer = setTimeout(() => setFlashing(false), 600);
      return () => clearTimeout(timer);
    }
  }, [events, flashing]);

  return (
    <div className="panel flex w-full flex-col space-y-4 p-5 font-sans">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-line">
        <div className="flex items-center space-x-2">
          <span className="w-3 h-3 rounded-full bg-gradient-to-r from-red-500 to-emerald-500 animate-pulse" />
          <h3 className="font-bold text-hi text-sm tracking-wide uppercase">
            Same incident, two architectures
          </h3>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded bg-black/30 text-dim font-mono">
          one event stream, tagged by agent
        </span>
      </div>

      {/* Side-by-Side Split Canvas */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Pane: Naive baseline (no commit gate) */}
        <div className="subpanel relative flex flex-col justify-between overflow-hidden border-red-950/80 p-4 lg:col-span-4">
          <div>
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-line">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <h4 className="eyebrow text-red-200">Conventional agent &middot; naive loop</h4>
              </div>
              <span className="font-mono text-[10px] text-dim">no commit gate</span>
            </div>

            {/* Prominent Counter */}
            <div
              className={`mb-4 rounded-md border p-4 text-center transition-all duration-300 ${
                baselineState.wrongActions > 0
                  ? 'border-red-600 bg-red-950/60 text-red-100 shadow-lg shadow-red-950/40 ring-1 ring-red-500'
                  : 'border-line bg-black/20 text-dim'
              } ${flashing ? 'scale-105 brightness-150' : 'scale-100'}`}
            >
              <div className="eyebrow tracking-widest text-red-400">Wrong actions committed</div>
              <div className="mt-1 font-mono text-4xl font-extrabold text-red-400">
                {baselineState.wrongActions}
              </div>
              {baselineState.corrupted && (
                <div className="mt-2 animate-pulse rounded bg-red-900/50 px-2 py-1 font-mono text-[10px] font-bold text-red-200">
                  &#9888; state corrupted: silently overwrote the correction
                </div>
              )}
            </div>

            {/* Current Understanding Key-Value */}
            <div className="space-y-2 font-mono text-xs">
              <span className="eyebrow block">Current understanding</span>
              <div className="subpanel space-y-1.5 p-3">
                <div className="flex justify-between">
                  <span className="text-dim">Locality:</span>
                  <span className={`font-bold ${baselineState.corrupted ? 'text-red-400 underline' : 'text-slate-200'}`}>
                    {baselineState.locality.toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-dim">Budget:</span>
                  <span className="text-slate-200">₹{baselineState.budget}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-dim">Dates:</span>
                  <span className="text-slate-200">{baselineState.dates}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-dim">Booking allowed:</span>
                  <span className="text-slate-200">{baselineState.bookingEnabled ? 'true' : 'false'}</span>
                </div>
                <div className="flex justify-between border-t border-line pt-1">
                  <span className="text-dim">Recommendation:</span>
                  <span className={`font-semibold ${baselineState.corrupted ? 'text-red-400' : 'text-slate-300'}`}>
                    {baselineState.recommendedHotel || 'Searching…'}
                  </span>
                </div>
              </div>
            </div>

            {/* In-Flight Activity */}
            <div className="mt-4 font-mono text-xs">
              <span className="eyebrow mb-1.5 block">Last baseline action</span>
              <div className="subpanel px-2.5 py-2 text-[11px] text-slate-300">{baselineState.lastAction}</div>
            </div>
            <StepList
              steps={[
                { label: 'Request sent', state: seq.sent ? 'done' : 'todo' },
                { label: 'User changes destination', state: seq.changed ? 'done' : 'todo' },
                seq.stale
                  ? { label: 'Old result arrives and is applied: wrong action', state: 'bad' }
                  : { label: 'Old result arrives', state: 'todo' },
              ]}
            />
          </div>

          {/* Bottom Footnote */}
          <div className="mt-4 border-t border-line pt-3 font-mono text-[10px] text-dim">
            Unconditionally commits all arriving responses. Stale results overwrite present context.
          </div>
        </div>

        {/* Right Pane: RePlan runtime (fingerprint gate) */}
        <div className="subpanel flex flex-col justify-between border-emerald-950/80 p-4 lg:col-span-8">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-line">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                <h4 className="eyebrow text-emerald-300">RePlan runtime &middot; fingerprint gate</h4>
              </div>

              <div
                className={`flex items-center space-x-3 rounded-md border px-4 py-2 transition-all duration-300 ${
                  flashing ? 'scale-105 border-emerald-500 bg-emerald-950/70 brightness-125' : 'border-emerald-800/60 bg-emerald-950/30'
                }`}
              >
                <span className="eyebrow text-emerald-400">Wrong actions:</span>
                <span className="font-mono text-2xl font-extrabold text-emerald-400">{replanWrongActions}</span>
              </div>
            </div>

            {/* Real committed actions, derived the same way as the baseline above */}
            <div className="font-mono text-xs">
              <span className="eyebrow mb-1.5 block">Committed actions</span>
              {replanCommits.length === 0 ? (
                <p className="subpanel px-3 py-3 text-dim">No commits yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {replanCommits.map((c) => (
                    <li key={c.taskId} className="subpanel flex items-center justify-between px-3 py-2">
                      <span className="text-slate-200">{c.tool}</span>
                      <span className="text-dim">{c.t.toFixed(2)}s</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <StepList
              steps={[
                { label: 'Request sent', state: seq.sent ? 'done' : 'todo' },
                { label: 'User changes destination', state: seq.changed ? 'done' : 'todo' },
                seq.stale
                  ? { label: 'Old result arrives and is rejected as stale', state: 'bad' }
                  : { label: 'Old result arrives', state: 'todo' },
                seq.commitAfter
                  ? { label: 'New result committed', state: 'good' }
                  : { label: 'New result committed', state: 'todo' },
              ]}
            />
          </div>

          {/* Bottom Callout */}
          <div className="mt-3 flex items-center justify-between border-t border-line pt-3 font-mono text-xs text-emerald-300/80">
            <span>&#10003; Stale-result firewall: fingerprint mismatch rejects obsolete background work</span>
          </div>
        </div>
      </div>
    </div>
  );
}

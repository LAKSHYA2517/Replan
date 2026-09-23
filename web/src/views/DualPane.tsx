import { useMemo, useState, useEffect } from 'react';
import { Event, EventType, Verdict } from '../contract.ts';
import Timeline from './Timeline.tsx';

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

export default function DualPane({ events }: DualPaneProps) {
  const [flashing, setFlashing] = useState<boolean>(false);

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
    <div className="w-full bg-slate-950/90 rounded-xl border border-slate-800/90 p-5 shadow-2xl flex flex-col space-y-4 font-sans">
      {/* Dual Pane Mode Header Banner */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <span className="w-3 h-3 rounded-full bg-gradient-to-r from-red-500 to-emerald-500 animate-pulse" />
          <h3 className="font-bold text-white text-sm tracking-wide uppercase">
            Head-to-Head Architectural Comparison (Beat 5 Divergence)
          </h3>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
          Single Event Stream Tagged by Agent
        </span>
      </div>

      {/* Side-by-Side Split Canvas */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Pane: Baseline Agent (Conventional Architecture) (5 Cols) */}
        <div className="lg:col-span-4 bg-slate-900/70 rounded-xl border border-red-950/80 p-4 flex flex-col justify-between shadow-lg relative overflow-hidden">
          {/* Header */}
          <div>
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <h4 className="font-bold text-red-200 text-xs uppercase tracking-wider">
                  Conventional Agent (Naive Loop)
                </h4>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">No Commit Gate</span>
            </div>

            {/* Prominent Counter */}
            <div
              className={`p-4 rounded-xl border mb-4 text-center transition-all duration-300 ${
                baselineState.wrongActions > 0
                  ? 'bg-red-950/80 border-red-600 text-red-100 shadow-xl shadow-red-950 ring-2 ring-red-500'
                  : 'bg-slate-950/80 border-slate-800 text-slate-400'
              } ${flashing ? 'scale-105 brightness-150' : 'scale-100'}`}
            >
              <div className="text-[11px] font-mono uppercase tracking-widest text-red-400 font-semibold">
                Wrong Actions Committed
              </div>
              <div className="text-4xl font-extrabold font-mono mt-1 text-red-400">
                {baselineState.wrongActions}
              </div>
              {baselineState.corrupted && (
                <div className="mt-2 text-[10px] font-bold text-red-200 bg-red-900/70 py-1 px-2 rounded font-mono animate-pulse">
                  ⚠ STATE CORRUPTED: DELPHI OVERWROTE MUMBAI
                </div>
              )}
            </div>

            {/* Current Understanding Key-Value */}
            <div className="space-y-2 text-xs font-mono">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block">
                Current Understanding
              </span>
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Locality:</span>
                  <span
                    className={`font-bold ${
                      baselineState.corrupted ? 'text-red-400 font-bold underline' : 'text-slate-200'
                    }`}
                  >
                    {baselineState.locality.toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Budget:</span>
                  <span className="text-slate-200">₹{baselineState.budget}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Dates:</span>
                  <span className="text-slate-200">{baselineState.dates}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Booking Allowed:</span>
                  <span className="text-slate-200">
                    {baselineState.bookingEnabled ? 'true' : 'false'}
                  </span>
                </div>
                <div className="flex justify-between pt-1 border-t border-slate-800/80">
                  <span className="text-slate-400">Recommendation:</span>
                  <span
                    className={`font-semibold ${
                      baselineState.corrupted ? 'text-red-400' : 'text-slate-300'
                    }`}
                  >
                    {baselineState.recommendedHotel || 'Searching…'}
                  </span>
                </div>
              </div>
            </div>

            {/* In-Flight Activity */}
            <div className="mt-4 text-xs font-mono">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1.5">
                Last Baseline Action
              </span>
              <div className="p-2.5 bg-slate-950/80 rounded border border-slate-800 text-[11px] text-slate-300">
                {baselineState.lastAction}
              </div>
            </div>
          </div>

          {/* Bottom Footnote */}
          <div className="mt-4 pt-3 border-t border-slate-800/80 text-[10px] text-slate-500 font-mono">
            Unconditionally commits all arriving responses. Stale results overwrite present context.
          </div>
        </div>

        {/* Right Pane: RePlan Runtime (Deterministic Coordination) (8 Cols) */}
        <div className="lg:col-span-8 bg-slate-900/70 rounded-xl border border-emerald-950/80 p-4 flex flex-col justify-between shadow-lg">
          <div>
            {/* Header & RePlan Counter */}
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                <h4 className="font-bold text-emerald-300 text-xs uppercase tracking-wider">
                  RePlan Runtime (Fingerprint Gate)
                </h4>
              </div>

              {/* Matching Size Counter for RePlan */}
              <div
                className={`px-4 py-2 rounded-xl border flex items-center space-x-3 transition-all duration-300 ${
                  flashing
                    ? 'bg-emerald-950/90 border-emerald-500 scale-105 brightness-125'
                    : 'bg-emerald-950/50 border-emerald-800/60'
                }`}
              >
                <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
                  Wrong Actions:
                </span>
                <span className="text-2xl font-extrabold font-mono text-emerald-400">0</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-900/80 text-emerald-200 font-mono border border-emerald-700">
                  Invariant I2 Held
                </span>
              </div>
            </div>

            {/* Embedded Timeline View from D2 */}
            <div className="w-full overflow-hidden">
              <Timeline events={events} />
            </div>
          </div>

          {/* Bottom Callout */}
          <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono text-emerald-300/80">
            <span>✓ Stale-Result Firewall: Fingerprint mismatch rejects obsolete background work</span>
            <span className="text-[10px] text-slate-400">Total Order Monotonic Chain</span>
          </div>
        </div>
      </div>
    </div>
  );
}

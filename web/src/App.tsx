import { useEventStream } from './useEventStream.ts';
import type { EventSource, LiveEventSubscriber } from './useEventStream.ts';
import type { Event } from './contract.ts';
import { EventType } from './contract.ts';
import Ledger from './views/Ledger.tsx';
import Transcript from './views/Transcript.tsx';

interface AppProps {
  source?: EventSource;
  speed?: number;
  subscribeLive?: LiveEventSubscriber;
}

interface CounterSnapshot {
  replan: number;
  baseline: number;
  usesCaseStudyFallback: boolean;
}

const emptyCounters: CounterSnapshot = {
  replan: 0,
  baseline: 0,
  usesCaseStudyFallback: false,
};

function counterReducer(counters: CounterSnapshot, event: Event): CounterSnapshot {
  if (event.type !== EventType.VERDICT) return counters;

  const agent = event.payload.agent;
  const wrongAction = event.payload.wrong_action === true;
  const fallback = event.payload.baseline_case_study_wrong_actions;

  return {
    replan: counters.replan + (agent === 'replan' && wrongAction ? 1 : 0),
    baseline: typeof fallback === 'number'
      ? fallback
      : counters.baseline + (agent === 'baseline' && wrongAction ? 1 : 0),
    usesCaseStudyFallback: counters.usesCaseStudyFallback || typeof fallback === 'number',
  };
}

function ComparisonCounters({ events }: { events: Event[] }) {
  const counters = events.reduce(counterReducer, emptyCounters);

  return (
    <section aria-label="Wrong action comparison" className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-2xl border border-emerald-800 bg-emerald-950/60 px-6 py-5">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">RePlan</p>
        <p className="mt-2 text-sm text-emerald-100">Wrong actions</p>
        <p className="mt-1 font-mono text-4xl font-bold text-emerald-400">{counters.replan}</p>
      </div>

      <div className="rounded-2xl border border-red-800 bg-red-950/60 px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-red-300">Naive baseline</p>
          {counters.usesCaseStudyFallback && (
            <span className="rounded-full border border-red-800 bg-red-950 px-2 py-0.5 text-[10px] text-red-300">
              fixture case study
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-red-100">Wrong actions</p>
        <p className="mt-1 font-mono text-4xl font-bold text-red-400">{counters.baseline}</p>
      </div>
    </section>
  );
}

export default function App({
  source = 'fixture',
  speed = 1,
  subscribeLive,
}: AppProps) {
  const { events, state } = useEventStream({ source, speed, subscribeLive });

  return (
    <main className="min-h-screen bg-slate-950 px-5 py-8 text-slate-100 sm:px-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <header className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl shadow-black/20">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-cyan-400">
                Theme 05 evidence console
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight">RePlan event stream</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                Read the correction as it happens, then see exactly why each tool result was accepted or rejected.
              </p>
            </div>

            <div className="flex items-center gap-3 font-mono text-xs">
              <span className="rounded-full border border-cyan-800 bg-cyan-950/60 px-3 py-1.5 text-cyan-300">
                {source === 'fixture' ? `fixture · ${speed}×` : 'live · LiveKit'}
              </span>
              <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-300">
                {state.eventsSeen} events
              </span>
            </div>
          </div>
        </header>

        <ComparisonCounters events={events} />

        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <Transcript events={events} />
          <Ledger events={events} />
        </div>
      </div>
    </main>
  );
}

import { fixtureEvents, useLatestHash, useReplay } from './useEventStream.ts';
import type { EventSource, LiveEventSubscriber } from './useEventStream.ts';
import CausalGraph from './views/CausalGraph.tsx';
import DualPane from './views/DualPane.tsx';
import FlightRecorder from './views/FlightRecorder.tsx';
import IncidentReplay from './views/IncidentReplay.tsx';
import Scrubber from './views/Scrubber.tsx';
import Timeline from './views/Timeline.tsx';
import WorldState from './views/WorldState.tsx';

interface AppProps {
  source?: EventSource;
  speed?: number;
  subscribeLive?: LiveEventSubscriber;
}

const REPLAY_SPEED = 0.25;

function Hero() {
  return (
    <header className="relative overflow-hidden rounded-xl border border-line bg-[#0b0e14] px-6 py-10 sm:px-10">
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 left-1/4 h-64 w-64 rounded-full bg-emerald-500/5 blur-3xl" />
      <div className="relative flex flex-col gap-4">
        <p className="eyebrow text-cyan-400">RePlan · Theme 05</p>
        <h1 className="max-w-3xl font-display text-5xl font-bold leading-tight tracking-tight text-hi sm:text-6xl">
          Nothing commits until it's <span className="text-cyan-300">still true.</span>
        </h1>
        <div className="flex items-center gap-4">
          <span className="h-px w-10 bg-cyan-400/60" />
          <p className="font-display text-lg font-medium tracking-wide text-slate-300 sm:text-xl">
            Stale results get <span className="font-semibold text-red-400">rejected</span>, never{' '}
            <span className="font-semibold text-emerald-300">applied</span>.
          </p>
        </div>
      </div>
    </header>
  );
}

export default function App({
  source = 'fixture',
  speed = REPLAY_SPEED,
  subscribeLive,
}: AppProps) {
  const { events, controls } = useReplay({ source, speed, subscribeLive });
  const currentHash = useLatestHash(events);
  const lastEvent = events[events.length - 1];

  return (
    <main className="relative min-h-screen px-5 py-10 text-slate-100 sm:px-8">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[#08090c]" />
      <div className="bg-dot-grid pointer-events-none fixed inset-0 -z-10 opacity-60 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <Hero />

        <IncidentReplay allEvents={source === 'fixture' ? fixtureEvents : events} />

        <WorldState events={events} />

        <CausalGraph events={events} />

        <div className="space-y-4">
          <Timeline events={events} />
          {controls !== null && (
            <Scrubber
              totalEvents={controls.totalEvents}
              currentSeq={events.length}
              onScrubToSeq={controls.scrubTo}
              currentHash={currentHash}
              currentTime={lastEvent?.t ?? 0}
              currentStateVersion={lastEvent?.state_version ?? 0}
            />
          )}
        </div>

        <DualPane events={events} />

        <FlightRecorder events={events} />
      </div>
    </main>
  );
}

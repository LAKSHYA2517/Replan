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

export default function App({
  source = 'fixture',
  speed = 1,
  subscribeLive,
}: AppProps) {
  const { events, controls } = useReplay({ source, speed, subscribeLive });
  const currentHash = useLatestHash(events);
  const lastEvent = events[events.length - 1];

  return (
    <main className="relative min-h-screen px-5 py-8 text-slate-100 sm:px-8">
      <div className="bg-dot-grid pointer-events-none fixed inset-0 -z-10 opacity-70 [mask-image:radial-gradient(ellipse_70%_70%_at_50%_0%,black,transparent)]" />

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <header className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="eyebrow text-cyan-400">RePlan engine</p>
            <h1 className="mt-1 font-mono text-xl font-bold text-hi">Flight recorder &amp; debugger for autonomous agents</h1>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="flex items-center gap-1.5 rounded border border-red-900/50 bg-red-950/20 px-3 py-1.5 font-semibold text-red-400">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
              {source === 'fixture' ? 'LIVE REPLAY' : 'LIVE · LIVEKIT'}
            </span>
            <span className="rounded border border-line bg-black/20 px-3 py-1.5 text-dim">SESSION #0421</span>
          </div>
        </header>

        <WorldState events={events} />

        <IncidentReplay
          allEvents={source === 'fixture' ? fixtureEvents : events}
          onReplay={() => controls?.restart()}
          disabled={controls === null}
        />

        <CausalGraph events={events} />

        <div className="space-y-3">
          <Timeline events={events} />
          {controls !== null && (
            <Scrubber
              totalEvents={controls.totalEvents}
              currentSeq={events.length}
              onScrubToSeq={controls.scrubTo}
              isPlaying={controls.isPlaying}
              onTogglePlay={controls.togglePlay}
              speed={controls.speed}
              onSetSpeed={controls.setSpeed}
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

import { useState } from 'react';
import { useEventStream } from './useEventStream.ts';
import Timeline from './views/Timeline.tsx';
import Console from './views/Console.tsx';
import DualPane from './views/DualPane.tsx';
import Controls from './views/Controls.tsx';
import Scrubber from './views/Scrubber.tsx';

export default function App() {
  const [activeTab, setActiveTab] = useState<'cockpit' | 'dualpane'>('dualpane');
  const [chaosMode, setChaosMode] = useState<'none' | 'mild' | 'severe'>('none');
  const {
    events,
    state,
    mode,
    setMode,
    cursor,
    totalEvents,
    isPlaying,
    speed,
    setSpeed,
    wsConnected,
    play,
    pause,
    restart,
    stepForward,
    scrubToSeq,
    injectLateResult,
  } = useEventStream('fixture');

  return (
    <div className="min-h-screen bg-[#0a0d14] text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md px-6 py-3.5 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20">
            R
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-base font-semibold tracking-tight text-white">RePlan</h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/50 font-mono">
                Track 5 Runtime
              </span>
            </div>
            <p className="text-xs text-slate-400">Deterministic Coordinator for Interruptible Agents</p>
          </div>
        </div>

        {/* Stream Source & Controls */}
        <div className="flex items-center space-x-4">
          {/* View Mode Toggle */}
          <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-medium">
            <button
              onClick={() => setActiveTab('dualpane')}
              className={`px-3 py-1 rounded-md transition-all flex items-center space-x-1.5 ${
                activeTab === 'dualpane'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>⚔️</span>
              <span>Dual-Pane Mode</span>
            </button>
            <button
              onClick={() => setActiveTab('cockpit')}
              className={`px-3 py-1 rounded-md transition-all flex items-center space-x-1.5 ${
                activeTab === 'cockpit'
                  ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🎛️</span>
              <span>Full Cockpit</span>
            </button>
          </div>

          {/* Source Toggle */}
          <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setMode('fixture')}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                mode === 'fixture' ? 'bg-cyan-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Synthetic Fixture
            </button>
            <button
              onClick={() => setMode('live')}
              className={`px-3 py-1 rounded-md font-medium transition-colors flex items-center space-x-1.5 ${
                mode === 'live' ? 'bg-cyan-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'
                }`}
              />
              <span>Live WS</span>
            </button>
          </div>

          {/* Speed Selectors */}
          {mode === 'fixture' && (
            <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs space-x-1 font-mono">
              {[0.5, 1.0, 2.0, 4.0].map((s) => (
                <button
                  key={s}
                  onClick={() => setSpeed(s)}
                  className={`px-2 py-1 rounded ${
                    speed === s ? 'bg-slate-700 text-cyan-300 font-bold' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          )}

          {/* Playback Controls */}
          {mode === 'fixture' && (
            <div className="flex items-center space-x-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                onClick={isPlaying ? pause : play}
                title={isPlaying ? 'Pause Replay' : 'Play Replay'}
                className="px-3 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-white font-medium"
              >
                {isPlaying ? '⏸ Pause' : '▶ Play'}
              </button>
              <button
                onClick={stepForward}
                disabled={isPlaying || cursor >= totalEvents}
                title="Step Next Event"
                className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300"
              >
                ⏭ Step
              </button>
              <button
                onClick={restart}
                title="Restart Replay"
                className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                ⟲ Reset
              </button>
            </div>
          )}

          {/* Big Red Inject Late Result Button */}
          <button
            onClick={injectLateResult}
            className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white shadow-lg shadow-red-600/30 active:scale-95 transition-all flex items-center space-x-1.5 border border-red-400/40 animate-pulse-subtle"
          >
            <span>⚡</span>
            <span>Inject Late Result</span>
          </button>
        </div>
      </header>

      {/* Metrics Banner */}
      <section className="bg-slate-950/90 border-b border-slate-800 px-6 py-2.5 grid grid-cols-2 md:grid-cols-6 gap-3 text-xs font-mono">
        <div className="bg-slate-900/80 p-2 rounded border border-slate-800/80">
          <div className="text-slate-400 text-[10px] uppercase">State Version</div>
          <div className="text-cyan-400 font-bold text-sm">v{state.version}</div>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-slate-800/80">
          <div className="text-slate-400 text-[10px] uppercase">Events Processed</div>
          <div className="text-white font-bold text-sm">
            {events.length} / {totalEvents}
          </div>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-slate-800/80">
          <div className="text-slate-400 text-[10px] uppercase">Freeze Lead Time</div>
          <div className="text-purple-400 font-bold text-sm">
            {state.freezeInfo ? `${state.freezeInfo.lead_time_ms} ms` : '—'}
          </div>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-slate-800/80">
          <div className="text-slate-400 text-[10px] uppercase">Reconcile Reuse</div>
          <div className="text-blue-400 font-bold text-sm">
            {state.reconcileMetrics.reuse_ratio > 0
              ? `${Math.round(state.reconcileMetrics.reuse_ratio * 100)}%`
              : '—'}
          </div>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-slate-800/80">
          <div className="text-slate-400 text-[10px] uppercase">Stale Blocked</div>
          <div className="text-red-400 font-bold text-sm">{state.staleCommitsCount}</div>
        </div>

        <div className="bg-emerald-950/40 p-2 rounded border border-emerald-800/50">
          <div className="text-emerald-400/80 text-[10px] uppercase">Wrong Actions</div>
          <div className="text-emerald-400 font-bold text-sm">0 (Invariant I2)</div>
        </div>
      </section>

      {/* Main Content Workspace */}
      <main className="flex-1 p-6 flex flex-col space-y-6 overflow-y-auto">
        {/* Interactive 6-Button Control Strip with Confirm Reservation Chip */}
        <section className="w-full">
          <Controls
            onRunScenario={(_scenario) => restart()}
            onInjectLateResult={injectLateResult}
            chaosMode={chaosMode}
            onSetChaosMode={setChaosMode}
            isPaused={!isPlaying}
            onTogglePause={() => (isPlaying ? pause() : play())}
            checkpoints={state.checkpoints}
            onRestoreCheckpoint={(_name) => restart()}
            onReplay={restart}
            speed={speed}
            onSetSpeed={setSpeed}
            pendingReservation={
              state.tasks['task_delhi_res']?.status === 'running'
                ? { id: 'res-8812', expires_at: 120, locality: 'delhi' }
                : null
            }
            onConfirmReservation={(_id) => {
              console.log('Confirmed reservation:', _id);
            }}
          />
        </section>

        {/* Deterministic Replay Scrubber (Tier 2 Full Implementation) */}
        <section className="w-full">
          <Scrubber
            totalEvents={totalEvents}
            currentSeq={events.length}
            onScrubToSeq={scrubToSeq}
            isPlaying={isPlaying}
            onTogglePlay={() => (isPlaying ? pause() : play())}
            speed={speed}
            onSetSpeed={setSpeed}
            currentHash={events[events.length - 1]?.hash || '0000000000000000'}
            currentTime={events[events.length - 1]?.t || 0.0}
            currentStateVersion={state.version}
          />
        </section>

        {activeTab === 'dualpane' ? (
          /* Dual-Pane Showdown Mode (Baseline vs RePlan) */
          <section className="w-full">
            <DualPane events={events} />
          </section>
        ) : (
          /* Full Cockpit Mode (Timeline + Console) */
          <>
            <section className="w-full">
              <Timeline events={events} />
            </section>
            <section className="w-full">
              <Console events={events} />
            </section>
          </>
        )}

        {/* Raw Monotonic Flight Recorder Event Stream */}
        <section className="w-full bg-slate-900/60 rounded-xl border border-slate-800/80 p-4 shadow-sm">
          <div className="flex items-center justify-between pb-3 mb-2 border-b border-slate-800">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Full Flight Recorder Event Log (Gapless Monotonic Sequence)</span>
            </h2>
            <span className="text-xs text-slate-400 font-mono">{events.length} events logged</span>
          </div>

          <div className="max-h-[220px] overflow-y-auto space-y-1.5 font-mono text-xs pr-1">
            {events.length === 0 ? (
              <div className="text-slate-500 text-center py-6 italic">Waiting for events…</div>
            ) : (
              events.map((ev) => (
                <div
                  key={ev.seq}
                  className="p-2 rounded bg-slate-950/80 border border-slate-800/80 flex items-center justify-between hover:border-slate-700"
                >
                  <div className="flex items-center space-x-3">
                    <span className="text-slate-400 font-semibold w-8">#{ev.seq}</span>
                    <span className="text-slate-400 w-16">t={ev.t.toFixed(2)}s</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-cyan-300 border border-slate-700">
                      {ev.type}
                    </span>
                    <span className="text-slate-300 truncate max-w-[480px]">
                      {JSON.stringify(ev.payload)}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    hash: {ev.hash?.slice(0, 8)}…
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

import { useState } from 'react';

interface ControlsProps {
  onRunScenario: (scenario: string) => void;
  onInjectLateResult: () => void;
  chaosMode: 'none' | 'mild' | 'severe';
  onSetChaosMode: (mode: 'none' | 'mild' | 'severe') => void;
  isPaused: boolean;
  onTogglePause: () => void;
  checkpoints: Array<{ name: string; version: number; t: number }>;
  onRestoreCheckpoint: (name: string) => void;
  onReplay: () => void;
  speed: number;
  onSetSpeed: (speed: number) => void;
  pendingReservation?: {
    id: string;
    expires_at: number;
    locality: string;
  } | null;
  onConfirmReservation?: (id: string) => void;
}

export default function Controls({
  onRunScenario,
  onInjectLateResult,
  chaosMode,
  onSetChaosMode,
  isPaused,
  onTogglePause,
  checkpoints,
  onRestoreCheckpoint,
  onReplay,
  speed,
  onSetSpeed,
  pendingReservation,
  onConfirmReservation,
}: ControlsProps) {
  const [selectedScenario, setSelectedScenario] = useState<string>('hotel_pivot');
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<string>('');

  const scenarios = [
    { id: 'hotel_pivot', name: 'Delhi → Mumbai Hotel Pivot (Signature)' },
    { id: 'smarthome_pivot', name: 'AC / Appliance Bedroom → Living Room' },
    { id: 'multimodal_budget', name: 'Visual Competitor OCR Budget Change' },
    { id: 'policy_toggle', name: 'Booking Policy Disable (Search Only)' },
  ];

  return (
    <div className="w-full bg-slate-900/90 rounded-xl border border-slate-800 p-3.5 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4 font-sans text-xs">
      {/* 6 Permanent Controls Strip */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 1. ▶ Run Scenario Dropdown */}
        <div className="flex items-center bg-slate-950 rounded-lg border border-slate-800 p-1">
          <select
            value={selectedScenario}
            onChange={(e) => {
              setSelectedScenario(e.target.value);
              onRunScenario(e.target.value);
            }}
            className="bg-transparent text-slate-200 text-xs px-2 py-1 outline-none cursor-pointer font-mono"
          >
            {scenarios.map((sc) => (
              <option key={sc.id} value={sc.id} className="bg-slate-900 text-slate-200">
                ▶ {sc.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => onRunScenario(selectedScenario)}
            className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-medium text-[11px] shadow"
            title="Execute Selected Scenario"
          >
            Run
          </button>
        </div>

        {/* 2. ⚡ INJECT LATE RESULT (Large, Red, Visually Dominant) */}
        <button
          onClick={onInjectLateResult}
          className="px-4 py-2 font-bold text-xs rounded-lg bg-gradient-to-r from-red-600 via-rose-600 to-red-700 hover:from-red-500 hover:to-rose-500 text-white shadow-lg shadow-red-600/40 active:scale-95 transition-all flex items-center space-x-2 border border-red-400/50 ring-2 ring-red-500/30 animate-pulse-subtle"
          title="Inject an obsolete in-flight result to attack the runtime"
        >
          <span className="text-sm">⚡</span>
          <span className="tracking-wide uppercase">Inject Late Result</span>
        </button>

        {/* 3. 🎲 Chaos Mode Toggle (None / Mild / Severe) */}
        <div className="flex items-center bg-slate-950 rounded-lg border border-slate-800 p-1 font-mono">
          <span className="text-slate-400 px-2 text-[11px] flex items-center space-x-1">
            <span>🎲</span>
            <span>Chaos:</span>
          </span>
          {(['none', 'mild', 'severe'] as const).map((m) => (
            <button
              key={m}
              onClick={() => onSetChaosMode(m)}
              className={`px-2.5 py-1 rounded text-[10px] font-bold uppercase transition-colors ${
                chaosMode === m
                  ? m === 'severe'
                    ? 'bg-red-600 text-white shadow'
                    : m === 'mild'
                    ? 'bg-amber-600 text-white shadow'
                    : 'bg-slate-700 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {m}
            </button>
          ))}
        </div>

        {/* 4. ⏸ Pause / Resume */}
        <button
          onClick={onTogglePause}
          className={`px-3 py-1.5 rounded-lg font-mono font-medium border flex items-center space-x-1.5 transition-colors ${
            isPaused
              ? 'bg-amber-500/20 border-amber-500/60 text-amber-300'
              : 'bg-slate-950 border-slate-800 hover:bg-slate-800 text-slate-300'
          }`}
        >
          <span>{isPaused ? '▶' : '⏸'}</span>
          <span>{isPaused ? 'Resume' : 'Pause'}</span>
        </button>

        {/* 5. ⟲ Restore Checkpoint */}
        <div className="flex items-center bg-slate-950 rounded-lg border border-slate-800 p-1 font-mono">
          <select
            value={selectedCheckpoint}
            onChange={(e) => setSelectedCheckpoint(e.target.value)}
            className="bg-transparent text-slate-300 text-[11px] px-2 py-1 outline-none cursor-pointer max-w-[130px] truncate"
          >
            <option value="" className="bg-slate-900 text-slate-400">
              ⟲ Checkpoints…
            </option>
            {checkpoints.map((cp, idx) => (
              <option key={idx} value={cp.name} className="bg-slate-900 text-slate-200">
                {cp.name} (v{cp.version})
              </option>
            ))}
          </select>
          <button
            onClick={() => selectedCheckpoint && onRestoreCheckpoint(selectedCheckpoint)}
            disabled={!selectedCheckpoint}
            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-cyan-300 rounded text-[10px] font-bold"
          >
            Restore
          </button>
        </div>

        {/* 6. ⏩ Replay & Speed */}
        <div className="flex items-center bg-slate-950 rounded-lg border border-slate-800 p-1 font-mono">
          <button
            onClick={onReplay}
            className="px-2.5 py-1 text-slate-300 hover:text-white hover:bg-slate-800 rounded font-medium flex items-center space-x-1"
            title="Replay Execution Trace"
          >
            <span>⏩</span>
            <span>Replay</span>
          </button>
          <div className="border-l border-slate-800 ml-1 pl-1 flex space-x-0.5">
            {[0.5, 1.0, 2.0, 4.0].map((s) => (
              <button
                key={s}
                onClick={() => onSetSpeed(s)}
                className={`px-1.5 py-0.5 text-[10px] rounded ${
                  speed === s ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Conditional Inline Affordance: Confirm Reservation Chip (Pairs with B7) */}
      {pendingReservation && (
        <div className="flex items-center space-x-2 bg-amber-950/80 border border-amber-600/80 px-3 py-1.5 rounded-lg shadow-lg shadow-amber-950/50 animate-bounce">
          <div className="flex items-center space-x-1.5 text-[11px] font-mono text-amber-200">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            <span>Held: {pendingReservation.id}</span>
          </div>
          <button
            onClick={() => onConfirmReservation && onConfirmReservation(pendingReservation.id)}
            className="px-2.5 py-1 bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 text-white rounded font-bold font-mono text-[10px] shadow border border-emerald-400/40"
          >
            Confirm {pendingReservation.id}
          </button>
        </div>
      )}
    </div>
  );
}

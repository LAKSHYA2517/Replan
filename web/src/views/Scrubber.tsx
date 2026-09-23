interface ScrubberProps {
  totalEvents: number;
  currentSeq: number;
  onScrubToSeq: (seq: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  speed: number;
  onSetSpeed: (speed: number) => void;
  currentHash?: string;
  currentTime?: number;
  currentStateVersion?: number;
}

export default function Scrubber({
  totalEvents,
  currentSeq,
  onScrubToSeq,
  isPlaying,
  onTogglePlay,
  speed,
  onSetSpeed,
  currentHash = '0000000000000000',
  currentTime = 0.0,
  currentStateVersion = 1,
}: ScrubberProps) {
  const speeds = [0.25, 0.5, 1.0, 2.0, 4.0];

  return (
    <div className="w-full bg-slate-900/95 border border-slate-800 p-3.5 rounded-xl shadow-2xl flex flex-col space-y-2.5 font-mono text-xs">
      {/* Top Header: Timeline Progress & Cryptographic Chain Hash */}
      <div className="flex items-center justify-between text-[11px]">
        <div className="flex items-center space-x-2">
          <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-bold text-white uppercase tracking-wider">
            Deterministic Replay Scrubber
          </span>
          <span className="text-slate-400 text-[10px]">
            (Event #{currentSeq} / {totalEvents} · t={currentTime.toFixed(2)}s · v{currentStateVersion})
          </span>
        </div>

        {/* Cryptographic Total-Order Hash Badge */}
        <div className="flex items-center space-x-1.5 bg-slate-950 px-2.5 py-1 rounded-md border border-cyan-900/50">
          <span className="text-cyan-400 text-xs">🔗</span>
          <span className="text-slate-400 text-[10px] uppercase tracking-wider">Chain Hash:</span>
          <span className="text-cyan-300 font-bold text-[11px] font-mono">
            {currentHash.slice(0, 16)}
          </span>
        </div>
      </div>

      {/* Center Range Slider */}
      <div className="flex items-center space-x-3 w-full">
        <button
          onClick={() => onScrubToSeq(Math.max(0, currentSeq - 1))}
          disabled={currentSeq <= 0}
          className="px-2 py-1 bg-slate-950 hover:bg-slate-800 disabled:opacity-30 border border-slate-800 text-slate-300 rounded text-[11px]"
          title="Step Back"
        >
          ◀
        </button>

        <div className="flex-1 relative flex items-center">
          <input
            type="range"
            min={0}
            max={totalEvents}
            value={currentSeq}
            onChange={(e) => onScrubToSeq(Number(e.target.value))}
            className="w-full h-2 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-cyan-500 hover:accent-cyan-400 border border-slate-800"
          />
        </div>

        <button
          onClick={() => onScrubToSeq(Math.min(totalEvents, currentSeq + 1))}
          disabled={currentSeq >= totalEvents}
          className="px-2 py-1 bg-slate-950 hover:bg-slate-800 disabled:opacity-30 border border-slate-800 text-slate-300 rounded text-[11px]"
          title="Step Forward"
        >
          ▶
        </button>
      </div>

      {/* Bottom Bar: Play/Pause, Replay Speed Mult */}
      <div className="flex items-center justify-between pt-1 border-t border-slate-800/80 text-[11px]">
        <div className="flex items-center space-x-2">
          <button
            onClick={onTogglePlay}
            className={`px-3 py-1 rounded font-bold transition-colors flex items-center space-x-1.5 ${
              isPlaying
                ? 'bg-amber-600 hover:bg-amber-500 text-white shadow'
                : 'bg-cyan-600 hover:bg-cyan-500 text-white shadow'
            }`}
          >
            <span>{isPlaying ? '⏸' : '▶'}</span>
            <span>{isPlaying ? 'Pause' : 'Play Replay'}</span>
          </button>
          <button
            onClick={() => onScrubToSeq(0)}
            className="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded"
          >
            ⟲ Start
          </button>
          <button
            onClick={() => onScrubToSeq(totalEvents)}
            className="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded"
          >
            ⏭ End
          </button>
        </div>

        {/* Speed Controls */}
        <div className="flex items-center space-x-1 bg-slate-950 p-0.5 rounded border border-slate-800">
          <span className="text-[10px] text-slate-400 px-1.5">Speed:</span>
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSetSpeed(s)}
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                speed === s ? 'bg-cyan-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

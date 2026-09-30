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
    <div className="panel flex w-full flex-col space-y-2.5 p-3.5 font-mono text-xs">
      {/* Top Header: Timeline Progress & Cryptographic Chain Hash */}
      <div className="flex items-center justify-between text-[11px]">
        <div className="flex items-center space-x-2">
          <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="eyebrow text-hi">Replay scrubber</span>
          <span className="text-dim text-[10px]">
            (event #{currentSeq} / {totalEvents} · t={currentTime.toFixed(2)}s · v{currentStateVersion})
          </span>
        </div>

        {/* Cryptographic Total-Order Hash Badge */}
        <div className="subpanel flex items-center space-x-1.5 px-2.5 py-1">
          <span className="text-cyan-400 text-xs">&#9670;</span>
          <span className="eyebrow text-[10px]">chain hash:</span>
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
          className="btn-ghost tracking-normal"
          title="Step Back"
        >
          &#9664;
        </button>

        <div className="flex-1 relative flex items-center">
          <input
            type="range"
            min={0}
            max={totalEvents}
            value={currentSeq}
            onChange={(e) => onScrubToSeq(Number(e.target.value))}
            className="w-full h-2 bg-black/30 rounded-lg appearance-none cursor-pointer accent-cyan-500 hover:accent-cyan-400 border border-line"
          />
        </div>

        <button
          onClick={() => onScrubToSeq(Math.min(totalEvents, currentSeq + 1))}
          disabled={currentSeq >= totalEvents}
          className="btn-ghost tracking-normal"
          title="Step Forward"
        >
          &#9654;
        </button>
      </div>

      {/* Bottom Bar: Play/Pause, Replay Speed Mult */}
      <div className="flex items-center justify-between pt-2 border-t border-line text-[11px]">
        <div className="flex items-center space-x-2">
          <button
            onClick={onTogglePlay}
            className={`btn tracking-normal flex items-center gap-1.5 ${isPlaying ? 'border-amber-500/50 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20' : 'btn-primary'}`}
          >
            <span>{isPlaying ? '⏸' : '▶'}</span>
            <span>{isPlaying ? 'Pause' : 'Play replay'}</span>
          </button>
          <button onClick={() => onScrubToSeq(0)} className="btn-ghost tracking-normal">
            &#8634; Start
          </button>
          <button onClick={() => onScrubToSeq(totalEvents)} className="btn-ghost tracking-normal">
            &#9197; End
          </button>
        </div>

        {/* Speed Controls */}
        <div className="subpanel flex items-center space-x-1 p-0.5">
          <span className="eyebrow px-1.5 text-[10px]">speed:</span>
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSetSpeed(s)}
              className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold transition-colors ${
                speed === s ? 'bg-cyan-500/20 text-cyan-300' : 'text-dim hover:text-hi'
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

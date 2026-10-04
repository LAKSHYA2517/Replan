interface ScrubberProps {
  totalEvents: number;
  currentSeq: number;
  onScrubToSeq: (seq: number) => void;
  currentHash?: string;
  currentTime?: number;
  currentStateVersion?: number;
}

export default function Scrubber({
  totalEvents,
  currentSeq,
  onScrubToSeq,
  currentHash = '0000000000000000',
  currentTime = 0.0,
  currentStateVersion = 1,
}: ScrubberProps) {
  const atEnd = currentSeq >= totalEvents;

  return (
    <section id="replay-controls" className="panel flex w-full flex-col gap-4 p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Walkthrough</p>
          <h2 className="panel-title">Step through the session</h2>
        </div>
        <div className="subpanel flex items-center gap-2 px-3 py-1.5 font-mono text-[11px]">
          <span className="text-dim">chain hash</span>
          <span className="font-bold text-cyan-300">{currentHash.slice(0, 16)}</span>
        </div>
      </header>

      <div className="flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={totalEvents}
          value={currentSeq}
          onChange={(e) => onScrubToSeq(Number(e.target.value))}
          aria-label="Replay position"
          className="w-full cursor-pointer accent-cyan-500"
        />
        <button
          onClick={() => onScrubToSeq(Math.min(totalEvents, currentSeq + 1))}
          disabled={atEnd}
          className="btn-primary shrink-0 px-5 py-2 tracking-wider"
        >
          Next &#9654;
        </button>
      </div>

      <p className="font-mono text-[11px] text-dim">
        event {currentSeq} of {totalEvents} · t = {currentTime.toFixed(2)}s · state v{currentStateVersion}
      </p>
    </section>
  );
}

import { useEffect, useMemo, useRef } from 'react';

import type { Event } from '../contract.ts';
import { EventType } from '../contract.ts';

interface TranscriptProps {
  events: Event[];
}

interface TranscriptTurn {
  seq: number;
  text: string;
  isFinal: boolean;
}

function textPayload(event: Event, key: 'text_partial' | 'text_final' | 'utterance'): string | null {
  const value = event.payload[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function deriveTurns(events: Event[]): TranscriptTurn[] {
  const turns: TranscriptTurn[] = [];

  for (const event of events) {
    const partial = textPayload(event, 'text_partial');
    const final = textPayload(event, 'text_final')
      ?? (event.type === EventType.STATE_PATCH ? textPayload(event, 'utterance') : null);

    if (partial !== null) {
      const pending = turns[turns.length - 1];
      if (pending !== undefined && !pending.isFinal) {
        pending.seq = event.seq;
        pending.text = partial;
      } else {
        turns.push({ seq: event.seq, text: partial, isFinal: false });
      }
    }

    if (final !== null) {
      const pending = turns[turns.length - 1];
      if (pending !== undefined && !pending.isFinal) {
        pending.seq = event.seq;
        pending.text = final;
        pending.isFinal = true;
      } else {
        turns.push({ seq: event.seq, text: final, isFinal: true });
      }
    }
  }

  return turns;
}

export default function Transcript({ events }: TranscriptProps) {
  const turns = useMemo(() => deriveTurns(events), [events]);
  const scrollArea = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollArea.current !== null) {
      scrollArea.current.scrollTop = scrollArea.current.scrollHeight;
    }
  }, [turns]);

  return (
    <section className="flex min-h-[26rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-black/10">
      <header className="border-b border-slate-200 px-5 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Zone 1</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">Live transcript</h2>
      </header>

      <div
        ref={scrollArea}
        aria-live="polite"
        aria-label="User transcript"
        className="flex-1 space-y-4 overflow-y-auto px-5 py-5"
      >
        {turns.length === 0 ? (
          <p className="text-sm text-slate-400">Waiting for speech…</p>
        ) : (
          turns.map((turn) => (
            <div key={turn.seq} className="border-l-2 border-slate-200 pl-4">
              <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                User · {turn.isFinal ? 'final' : 'partial'}
              </p>
              <p className={`mt-1 text-base leading-7 ${turn.isFinal ? 'font-medium text-black' : 'text-slate-400'}`}>
                {turn.text}
              </p>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

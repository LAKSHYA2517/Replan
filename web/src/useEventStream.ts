import { useEffect, useMemo, useRef, useState } from 'react';

import type { Event } from './contract.ts';
import signatureFixture from './fixtures/signature.json';

export type EventSource = 'fixture' | 'live';
export type LiveEventSubscriber = (onEvent: (event: Event) => void) => void | (() => void);

interface EventStreamOptions {
  source: EventSource;
  speed?: number;
  subscribeLive?: LiveEventSubscriber;
}

export interface StreamState {
  eventsSeen: number;
  stateVersion: number;
  lastSequence: number;
  lastEventType: Event['type'] | null;
}

const initialState: StreamState = {
  eventsSeen: 0,
  stateVersion: 0,
  lastSequence: 0,
  lastEventType: null,
};

export const fixtureEvents = signatureFixture as Event[];

export function eventReducer(state: StreamState, event: Event): StreamState {
  return {
    eventsSeen: state.eventsSeen + 1,
    stateVersion: event.state_version,
    lastSequence: event.seq,
    lastEventType: event.type,
  };
}

/** Wall-clock delay (ms) between revealing fixtureEvents[index - 1] and fixtureEvents[index],
 * scaled by the current replay speed. Shared by autoplay and used to derive a speed-independent
 * "index at time t" mapping isn't needed since we replay index-by-index, not by wall clock. */
function stepDelay(index: number, speed: number): number {
  const event = fixtureEvents[index];
  const previous = index > 0 ? fixtureEvents[index - 1] : null;
  const raw = previous ? (event.t - previous.t) * 1000 : 200;
  return Math.max(80, raw) / Math.max(speed, 0.1);
}

export interface ReplayControls {
  totalEvents: number;
  isPlaying: boolean;
  togglePlay: () => void;
  scrubTo: (index: number) => void;
  stepBack: () => void;
  stepForward: () => void;
  speed: number;
  setSpeed: (speed: number) => void;
  restart: () => void;
}

/**
 * Fixture replay with real scrubbing: the full trace is already in memory
 * (JSON import), so "revealing" events up to a cursor and letting the user
 * drag/step/play that cursor is just index math, not a new data source.
 * Live mode has no such tape to scrub — events arrive once and controls
 * are null so the UI can hide/disable transport controls for it.
 */
export function useReplay({
  source,
  speed: initialSpeed = 1,
  subscribeLive,
}: EventStreamOptions): { events: Event[]; state: StreamState; controls: ReplayControls | null } {
  const [cursor, setCursor] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [speed, setSpeed] = useState(initialSpeed);
  const [liveEvents, setLiveEvents] = useState<Event[]>([]);

  useEffect(() => {
    setCursor(0);
    setIsPlaying(true);
    setLiveEvents([]);
  }, [source]);

  useEffect(() => {
    if (source !== 'fixture' || !isPlaying || cursor >= fixtureEvents.length) {
      return;
    }
    const timer = window.setTimeout(() => {
      setCursor((current) => Math.min(current + 1, fixtureEvents.length));
    }, stepDelay(cursor, speed));
    return () => window.clearTimeout(timer);
  }, [source, isPlaying, cursor, speed]);

  useEffect(() => {
    if (source !== 'live' || subscribeLive === undefined) {
      return;
    }
    return subscribeLive((event) => {
      setLiveEvents((current) => [...current, event]);
    });
  }, [source, subscribeLive]);

  const events = useMemo(
    () => (source === 'fixture' ? fixtureEvents.slice(0, cursor) : liveEvents),
    [source, cursor, liveEvents],
  );

  const state = useMemo(() => events.reduce(eventReducer, initialState), [events]);

  const controls: ReplayControls | null = useMemo(() => {
    if (source !== 'fixture') return null;
    return {
      totalEvents: fixtureEvents.length,
      isPlaying,
      togglePlay: () => setIsPlaying((p) => !p),
      scrubTo: (index: number) => setCursor(Math.max(0, Math.min(index, fixtureEvents.length))),
      stepBack: () => setCursor((c) => Math.max(0, c - 1)),
      stepForward: () => setCursor((c) => Math.min(fixtureEvents.length, c + 1)),
      speed,
      setSpeed,
      restart: () => {
        setCursor(0);
        setIsPlaying(true);
      },
    };
  }, [source, isPlaying, speed]);

  return { events, state, controls };
}

// Kept for any external caller expecting the plain drip-only hook (unused internally now).
export function useEventStream(options: EventStreamOptions): { events: Event[]; state: StreamState } {
  const { events, state } = useReplay(options);
  return { events, state };
}

export function useLatestHash(events: Event[]): string {
  const last = events[events.length - 1];
  return last ? last.hash : '0000000000000000';
}

export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T>();
  useEffect(() => {
    ref.current = value;
  });
  return ref.current;
}

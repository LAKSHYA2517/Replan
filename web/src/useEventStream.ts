import { useEffect, useMemo, useState } from 'react';

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

const fixtureEvents = signatureFixture as Event[];

export function eventReducer(state: StreamState, event: Event): StreamState {
  return {
    eventsSeen: state.eventsSeen + 1,
    stateVersion: event.state_version,
    lastSequence: event.seq,
    lastEventType: event.type,
  };
}

export function useEventStream({
  source,
  speed = 1,
  subscribeLive,
}: EventStreamOptions): { events: Event[]; state: StreamState } {
  const [events, setEvents] = useState<Event[]>([]);

  const state = useMemo(
    () => events.reduce(eventReducer, initialState),
    [events],
  );

  useEffect(() => {
    setEvents([]);
  }, [source]);

  useEffect(() => {
    if (source !== 'fixture' || events.length >= fixtureEvents.length) {
      return;
    }

    const event = fixtureEvents[events.length];
    const previous = events.length > 0 ? fixtureEvents[events.length - 1] : null;
    const fixtureDelay = previous ? (event.t - previous.t) * 1000 : 200;
    const delay = Math.max(100, fixtureDelay) / Math.max(speed, 0.1);
    const timer = window.setTimeout(() => {
      setEvents((current) => [...current, event]);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [events.length, source, speed]);

  useEffect(() => {
    if (source !== 'live' || subscribeLive === undefined) {
      return;
    }

    return subscribeLive((event) => {
      setEvents((current) => [...current, event]);
    });
  }, [source, subscribeLive]);

  return { events, state };
}

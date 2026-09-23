import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Event,
  EventType,
  SessionState,
  PlanTask,
  TaskStatus,
  CommitDecision,
  Verdict,
  Hypothesis,
  Effect,
} from './contract.ts';
import signatureFixture from './fixtures/signature.json';

export interface UIState {
  version: number;
  sessionState: SessionState;
  tasks: Record<string, PlanTask>;
  activePlanId: string;
  decisions: CommitDecision[];
  speechEnvelope: {
    start_t: number;
    end_t: number;
    text_partial?: string;
    active: boolean;
  } | null;
  freezeInfo: {
    hypothesis: Hypothesis;
    frozen_tasks: string[];
    lead_time_ms: number;
    at: number;
  } | null;
  reconcileMetrics: {
    adopted: string[];
    reused: string[];
    invalidated: string[];
    added: string[];
    compensate: string[];
    reuse_ratio: number;
  };
  bargeIn: {
    latency_ms: number;
    trigger: string;
  } | null;
  compensations: Array<{
    task_id: string;
    action: string;
    reservation_id: string;
    reason: string;
    t: number;
  }>;
  paused: boolean;
  checkpoints: Array<{ name: string; version: number; t: number }>;
  wrongActionsCount: number;
  staleCommitsCount: number;
  lastEvent: Event | null;
  eventsCount: number;
}

const initialSessionState: SessionState = {
  version: 0,
  slots: {},
  constraints: {},
  policy: {},
};

export const initialUIState: UIState = {
  version: 0,
  sessionState: initialSessionState,
  tasks: {},
  activePlanId: 'plan_init',
  decisions: [],
  speechEnvelope: null,
  freezeInfo: null,
  reconcileMetrics: {
    adopted: [],
    reused: [],
    invalidated: [],
    added: [],
    compensate: [],
    reuse_ratio: 0,
  },
  bargeIn: null,
  compensations: [],
  paused: false,
  checkpoints: [],
  wrongActionsCount: 0,
  staleCommitsCount: 0,
  lastEvent: null,
  eventsCount: 0,
};

export function eventReducer(state: UIState, event: Event): UIState {
  const nextTasks = { ...state.tasks };
  let nextSessionState = { ...state.sessionState };
  let nextDecisions = [...state.decisions];
  let nextWrongActions = state.wrongActionsCount;
  let nextStaleCommits = state.staleCommitsCount;
  let nextSpeechEnvelope = state.speechEnvelope;
  let nextFreezeInfo = state.freezeInfo;
  let nextReconcile = { ...state.reconcileMetrics };
  let nextBargeIn = state.bargeIn;
  const nextCompensations = [...state.compensations];
  let nextCheckpoints = [...state.checkpoints];
  let nextPaused = state.paused;

  switch (event.type) {
    case EventType.STATE_PATCH: {
      const patch = (event.payload.patch as Record<string, Record<string, unknown>>) || {};
      nextSessionState = {
        ...nextSessionState,
        version: event.state_version,
        slots: { ...nextSessionState.slots, ...(patch.slots || {}) },
        constraints: { ...nextSessionState.constraints, ...(patch.constraints || {}) },
        policy: { ...nextSessionState.policy, ...(patch.policy || {}) },
      };
      break;
    }

    case EventType.TASK_DISPATCH: {
      const p = event.payload as {
        task_id: string;
        call_id: string;
        tool: string;
        args: Record<string, unknown>;
        dispatch_fp: string;
        speculative: boolean;
        effect: Effect;
      };
      nextTasks[p.task_id] = {
        id: p.task_id,
        tool: p.tool,
        arg_spec: p.args,
        after: [],
        speculative: p.speculative ?? false,
        status: TaskStatus.RUNNING,
        call_id: p.call_id,
        dispatch_fp: p.dispatch_fp,
      };
      break;
    }

    case EventType.TASK_FREEZE: {
      const p = event.payload as {
        hypothesis: Hypothesis;
        frozen_tasks: string[];
        lead_time_ms: number;
      };
      p.frozen_tasks?.forEach((tid) => {
        if (nextTasks[tid]) {
          nextTasks[tid] = { ...nextTasks[tid], status: TaskStatus.FROZEN };
        }
      });
      nextFreezeInfo = {
        hypothesis: p.hypothesis,
        frozen_tasks: p.frozen_tasks || [],
        lead_time_ms: p.lead_time_ms || 0,
        at: event.t,
      };
      break;
    }

    case EventType.TASK_THAW: {
      const p = event.payload as { task_ids: string[] };
      p.task_ids?.forEach((tid) => {
        if (nextTasks[tid] && nextTasks[tid].status === TaskStatus.FROZEN) {
          nextTasks[tid] = { ...nextTasks[tid], status: TaskStatus.RUNNING };
        }
      });
      break;
    }

    case EventType.VERDICT: {
      const p = event.payload as {
        call_id: string;
        task_id: string;
        verdict: Verdict;
        reason: string;
      };
      nextDecisions = [
        ...nextDecisions,
        {
          call_id: p.call_id,
          task_id: p.task_id,
          verdict: p.verdict,
          reason: p.reason,
          t: event.t,
        },
      ];

      if (p.task_id && nextTasks[p.task_id]) {
        if (p.verdict === Verdict.COMMIT) {
          nextTasks[p.task_id] = { ...nextTasks[p.task_id], status: TaskStatus.DONE };
        } else if (p.verdict === Verdict.STALE || p.verdict === Verdict.CANCELLED) {
          nextTasks[p.task_id] = { ...nextTasks[p.task_id], status: TaskStatus.INVALIDATED };
        }
      }

      if (p.verdict === Verdict.STALE) {
        nextStaleCommits += 1;
      }
      break;
    }

    case EventType.RECONCILE: {
      const p = event.payload as {
        old_plan_id?: string;
        new_plan_id?: string;
        adopted?: string[];
        reused_from_cache?: string[];
        invalidated?: string[];
        added?: string[];
        compensate?: string[];
        reuse_ratio?: number;
      };
      nextReconcile = {
        adopted: p.adopted || [],
        reused: p.reused_from_cache || [],
        invalidated: p.invalidated || [],
        added: p.added || [],
        compensate: p.compensate || [],
        reuse_ratio: p.reuse_ratio ?? 0,
      };

      p.invalidated?.forEach((tid) => {
        if (nextTasks[tid]) {
          nextTasks[tid] = { ...nextTasks[tid], status: TaskStatus.INVALIDATED };
        }
      });
      break;
    }

    case EventType.SPEECH_ENVELOPE: {
      const p = event.payload as { start_t: number; end_t: number; text_partial?: string };
      nextSpeechEnvelope = {
        start_t: p.start_t,
        end_t: p.end_t,
        text_partial: p.text_partial,
        active: true,
      };
      break;
    }

    case EventType.BARGE_IN: {
      const p = event.payload as { latency_ms: number; trigger: string };
      nextBargeIn = {
        latency_ms: p.latency_ms,
        trigger: p.trigger,
      };
      break;
    }

    case EventType.COMPENSATING: {
      const p = event.payload as {
        task_id: string;
        action: string;
        reservation_id: string;
        reason: string;
      };
      nextCompensations.push({
        task_id: p.task_id,
        action: p.action,
        reservation_id: p.reservation_id,
        reason: p.reason,
        t: event.t,
      });
      break;
    }

    case EventType.CHECKPOINT: {
      const p = event.payload as { name: string; version: number };
      nextCheckpoints.push({
        name: p.name || `cp_${event.state_version}`,
        version: event.state_version,
        t: event.t,
      });
      break;
    }

    case EventType.RESTORE: {
      nextSessionState = {
        ...nextSessionState,
        version: event.state_version,
      };
      break;
    }

    case EventType.PAUSE:
      nextPaused = true;
      break;

    case EventType.RESUME:
      nextPaused = false;
      break;

    default:
      break;
  }

  return {
    ...state,
    version: event.state_version,
    sessionState: nextSessionState,
    tasks: nextTasks,
    decisions: nextDecisions,
    speechEnvelope: nextSpeechEnvelope,
    freezeInfo: nextFreezeInfo,
    reconcileMetrics: nextReconcile,
    bargeIn: nextBargeIn,
    compensations: nextCompensations,
    checkpoints: nextCheckpoints,
    paused: nextPaused,
    wrongActionsCount: nextWrongActions,
    staleCommitsCount: nextStaleCommits,
    lastEvent: event,
    eventsCount: state.eventsCount + 1,
  };
}

export function useEventStream(initialMode: 'fixture' | 'live' = 'fixture') {
  const [mode, setMode] = useState<'fixture' | 'live'>(initialMode);
  const [events, setEvents] = useState<Event[]>([]);
  const [cursor, setCursor] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [speed, setSpeed] = useState<number>(1.0);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);

  const fixtureEvents = signatureFixture as unknown as Event[];

  // Derive pure state from processed events
  const state: UIState = events.reduce(eventReducer, initialUIState);

  // Playback timer for fixture
  useEffect(() => {
    if (mode !== 'fixture' || !isPlaying) return;

    if (cursor >= fixtureEvents.length) {
      setIsPlaying(false);
      return;
    }

    const currentEvent = fixtureEvents[cursor];
    const prevEvent = cursor > 0 ? fixtureEvents[cursor - 1] : null;
    const delayMs = prevEvent
      ? Math.max(150, (currentEvent.t - prevEvent.t) * 1000) / speed
      : 200 / speed;

    const timer = setTimeout(() => {
      setEvents((prev) => [...prev, currentEvent]);
      setCursor((c) => c + 1);
    }, delayMs);

    return () => clearTimeout(timer);
  }, [mode, isPlaying, cursor, speed, fixtureEvents]);

  // WebSocket connection for live mode
  useEffect(() => {
    if (mode !== 'live') {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      return;
    }

    const ws = new WebSocket('ws://localhost:8000/events');
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
    };

    ws.onmessage = (msgEvent) => {
      try {
        const parsed = JSON.parse(msgEvent.data) as Event;
        setEvents((prev) => [...prev, parsed]);
        setCursor((c) => c + 1);
      } catch (err) {
        console.error('Failed to parse WebSocket event JSON:', err);
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
    };

    ws.onerror = (err) => {
      console.warn('WebSocket connection error:', err);
      setWsConnected(false);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [mode]);

  const play = useCallback(() => setIsPlaying(true), []);
  const pause = useCallback(() => setIsPlaying(false), []);
  const restart = useCallback(() => {
    setEvents([]);
    setCursor(0);
    setIsPlaying(true);
  }, []);

  const stepForward = useCallback(() => {
    if (mode === 'fixture' && cursor < fixtureEvents.length) {
      setEvents((prev) => [...prev, fixtureEvents[cursor]]);
      setCursor((c) => c + 1);
    }
  }, [mode, cursor, fixtureEvents]);

  const scrubToSeq = useCallback(
    (seq: number) => {
      if (mode === 'fixture') {
        const clamped = Math.max(0, Math.min(seq, fixtureEvents.length));
        setEvents(fixtureEvents.slice(0, clamped));
        setCursor(clamped);
      }
    },
    [mode, fixtureEvents]
  );

  const injectLateResult = useCallback(async () => {
    if (mode === 'live') {
      try {
        await fetch('http://localhost:8000/inject_late_result', { method: 'POST' });
      } catch (err) {
        console.error('Failed to inject late result to live server:', err);
      }
    } else {
      // In fixture mode, inject a late synthetic STALE verdict event
      const injectedEvent: Event = {
        seq: events.length + 1,
        t: (events[events.length - 1]?.t || 1.0) + 0.1,
        state_version: state.version,
        type: EventType.VERDICT,
        payload: {
          call_id: `c_injected_late_${Date.now()}`,
          task_id: 'task_delhi_search',
          verdict: Verdict.STALE,
          reason: `INJECTED ADVERSARIAL: dispatch fp fp_delhi_v1 != current fp_mumbai_v${state.version} (dispatched at v1, now v${state.version})`,
          dispatched_at_v: 1,
          current_v: state.version,
        },
        prev_hash: events[events.length - 1]?.hash || '0000000000000000',
        hash: 'deadbeefcafe0001',
      };
      setEvents((prev) => [...prev, injectedEvent]);
    }
  }, [mode, events, state.version]);

  return {
    events,
    state,
    mode,
    setMode,
    cursor,
    totalEvents: mode === 'fixture' ? fixtureEvents.length : events.length,
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
  };
}

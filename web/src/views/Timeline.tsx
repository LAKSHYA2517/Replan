import { useMemo, useState } from 'react';
import { scaleLinear } from 'd3-scale';
import { Event, EventType, Verdict, TaskStatus, Effect } from '../contract.ts';

interface TimelineProps {
  events: Event[];
}

interface SwimlaneTask {
  taskId: string;
  tool: string;
  effect: Effect;
  speculative: boolean;
  startT: number;
  endT: number;
  status: TaskStatus;
  dispatchFp?: string;
}

interface ResultPoint {
  taskId: string;
  callId: string;
  t: number;
  verdict: Verdict;
  reason: string;
  dispatchedAtV?: number;
  currentV?: number;
}

interface SpeechData {
  startT: number;
  endT: number;
  text?: string;
}

interface FreezeData {
  t: number;
  confidence: number;
  kind: string;
  leadTimeMs: number;
  endT: number;
}

interface VersionChange {
  t: number;
  fromV: number;
  toV: number;
  paths: string[];
}

interface CompensationLink {
  taskId: string;
  reserveT: number;
  releaseT: number;
  reservationId: string;
  reason: string;
}

export default function Timeline({ events }: TimelineProps) {
  const [hoveredResult, setHoveredResult] = useState<ResultPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  // Parse events into structured marks
  const {
    tasks,
    results,
    speechEnvelopes,
    freezes,
    versionChanges,
    compensations,
    maxT,
  } = useMemo(() => {
    const taskMap = new Map<string, SwimlaneTask>();
    const resultList: ResultPoint[] = [];
    const speeches: SpeechData[] = [];
    const freezeList: FreezeData[] = [];
    const vChanges: VersionChange[] = [];
    const compLinks: CompensationLink[] = [];
    let currentMaxT = 4.2; // default min domain

    let lastVersion = 1;

    events.forEach((ev) => {
      if (ev.t > currentMaxT) currentMaxT = ev.t;

      switch (ev.type) {
        case EventType.STATE_PATCH: {
          const changedPaths = (ev.payload.changed_paths as string[]) || [];
          if (ev.state_version > lastVersion) {
            vChanges.push({
              t: ev.t,
              fromV: lastVersion,
              toV: ev.state_version,
              paths: changedPaths,
            });
            lastVersion = ev.state_version;
          }
          break;
        }

        case EventType.TASK_DISPATCH: {
          const p = ev.payload as {
            task_id: string;
            tool: string;
            speculative: boolean;
            effect: Effect;
            dispatch_fp: string;
          };
          taskMap.set(p.task_id, {
            taskId: p.task_id,
            tool: p.tool,
            effect: p.effect || Effect.PURE,
            speculative: p.speculative ?? false,
            startT: ev.t,
            endT: ev.t + 1.2, // default stretch until result/reconcile
            status: TaskStatus.RUNNING,
            dispatchFp: p.dispatch_fp,
          });
          break;
        }

        case EventType.TASK_FREEZE: {
          const p = ev.payload as {
            hypothesis: { confidence: number; kind: string };
            frozen_tasks: string[];
            lead_time_ms: number;
          };
          const endT = ev.t + (p.lead_time_ms || 900) / 1000;
          freezeList.push({
            t: ev.t,
            confidence: p.hypothesis?.confidence ?? 0.88,
            kind: p.hypothesis?.kind ?? 'pivot',
            leadTimeMs: p.lead_time_ms ?? 900,
            endT,
          });
          p.frozen_tasks?.forEach((tid) => {
            const task = taskMap.get(tid);
            if (task && task.status === TaskStatus.RUNNING) {
              task.status = TaskStatus.FROZEN;
            }
          });
          break;
        }

        case EventType.SPEECH_ENVELOPE: {
          const p = ev.payload as { start_t: number; end_t: number; text_partial?: string };
          speeches.push({
            startT: p.start_t,
            endT: p.end_t,
            text: p.text_partial,
          });
          break;
        }

        case EventType.VERDICT: {
          const p = ev.payload as {
            call_id: string;
            task_id: string;
            verdict: Verdict;
            reason: string;
            dispatched_at_v?: number;
            current_v?: number;
          };
          resultList.push({
            taskId: p.task_id,
            callId: p.call_id,
            t: ev.t,
            verdict: p.verdict,
            reason: p.reason,
            dispatchedAtV: p.dispatched_at_v,
            currentV: p.current_v,
          });

          const task = taskMap.get(p.task_id);
          if (task) {
            task.endT = ev.t;
            if (p.verdict === Verdict.COMMIT) {
              task.status = TaskStatus.DONE;
            } else if (p.verdict === Verdict.STALE || p.verdict === Verdict.CANCELLED) {
              task.status = TaskStatus.INVALIDATED;
            }
          }
          break;
        }

        case EventType.RECONCILE: {
          const p = ev.payload as {
            invalidated?: string[];
            adopted?: string[];
          };
          p.invalidated?.forEach((tid) => {
            const task = taskMap.get(tid);
            if (task) {
              task.endT = ev.t;
              task.status = TaskStatus.INVALIDATED;
            }
          });
          break;
        }

        case EventType.COMPENSATING: {
          const p = ev.payload as {
            task_id: string;
            reservation_id: string;
            reason: string;
          };
          const task = taskMap.get(p.task_id);
          compLinks.push({
            taskId: p.task_id,
            reserveT: task?.startT ?? 0.6,
            releaseT: ev.t,
            reservationId: p.reservation_id,
            reason: p.reason,
          });
          break;
        }

        default:
          break;
      }
    });

    return {
      tasks: Array.from(taskMap.values()),
      results: resultList,
      speechEnvelopes: speeches,
      freezes: freezeList,
      versionChanges: vChanges,
      compensations: compLinks,
      maxT: currentMaxT + 0.5,
    };
  }, [events]);

  // Layout Dimensions
  const width = 960;
  const marginLeft = 180;
  const marginRight = 40;
  const speechLaneHeight = 46;
  const headerHeight = 70;
  const rowHeight = 36;
  const totalHeight = headerHeight + speechLaneHeight + Math.max(tasks.length, 5) * rowHeight + 50;

  // D3 Scale for Time Axis
  const xScale = useMemo(() => {
    return scaleLinear()
      .domain([0, Math.max(maxT, 4.0)])
      .range([marginLeft, width - marginRight]);
  }, [maxT, marginLeft, width, marginRight]);

  // Time ticks
  const timeTicks = useMemo(() => {
    const ticks = [];
    const maxVal = Math.max(maxT, 4.0);
    for (let t = 0; t <= maxVal; t += 0.5) {
      ticks.push(t);
    }
    return ticks;
  }, [maxT]);

  // Map task ID to vertical Y center
  const getTaskY = (taskId: string) => {
    const idx = tasks.findIndex((t) => t.taskId === taskId);
    const rowIdx = idx >= 0 ? idx : 0;
    return headerHeight + speechLaneHeight + rowIdx * rowHeight + rowHeight / 2;
  };

  return (
    <div className="w-full bg-slate-950/90 rounded-xl border border-slate-800/90 p-4 shadow-xl overflow-x-auto relative">
      {/* Top Title & Legend Bar */}
      <div className="flex items-center justify-between pb-3 mb-2 border-b border-slate-800 text-xs">
        <div className="flex items-center space-x-2">
          <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
          <h3 className="font-semibold text-white tracking-wide uppercase text-[11px]">
            Execution Swimlane Timeline (Wall-Clock Seconds)
          </h3>
        </div>

        {/* Legend */}
        <div className="flex items-center space-x-4 text-[11px] font-mono text-slate-300">
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block" />
            <span>COMMIT</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rotate-45 bg-red-500 inline-block shadow-sm shadow-red-500/50" />
            <span className="font-bold text-red-400">STALE (Blocked)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 bg-amber-500 inline-block" />
            <span>DUPLICATE</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 bg-purple-600/80 hatched-pattern inline-block border border-purple-400/50" />
            <span>FROZEN</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas */}
      <svg
        viewBox={`0 0 ${width} ${totalHeight}`}
        className="w-full h-auto select-none"
        style={{ minWidth: '780px' }}
      >
        <defs>
          {/* Hatched pattern for frozen task bars */}
          <pattern id="diagonalHatch" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="8" stroke="#a855f7" strokeWidth="3" strokeOpacity="0.8" />
            <line x1="4" y1="0" x2="4" y2="8" stroke="#6b21a8" strokeWidth="4" strokeOpacity="0.5" />
          </pattern>

          {/* Gradients */}
          <linearGradient id="speechGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0284c7" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.08" />
          </linearGradient>

          <linearGradient id="staleGlow" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ef4444" />
            <stop offset="100%" stopColor="#b91c1c" />
          </linearGradient>
        </defs>

        {/* 1. Background Grid & Time Axis Verticals */}
        {timeTicks.map((t) => (
          <g key={t}>
            <line
              x1={xScale(t)}
              y1={headerHeight}
              x2={xScale(t)}
              y2={totalHeight - 30}
              stroke="#1e293b"
              strokeWidth="1"
              strokeDasharray={t % 1.0 === 0 ? 'none' : '2,2'}
            />
            <text
              x={xScale(t)}
              y={totalHeight - 12}
              fill="#64748b"
              fontSize="10"
              fontFamily="monospace"
              textAnchor="middle"
            >
              {t.toFixed(1)}s
            </text>
          </g>
        ))}

        {/* 2. Version Change Verticals (v1 -> v2, etc.) */}
        {versionChanges.map((vc, idx) => (
          <g key={idx}>
            <line
              x1={xScale(vc.t)}
              y1={headerHeight - 10}
              x2={xScale(vc.t)}
              y2={totalHeight - 30}
              stroke="#06b6d4"
              strokeWidth="1.5"
              strokeDasharray="4,3"
              strokeOpacity="0.8"
            />
            {/* Version Flag Tag */}
            <rect
              x={xScale(vc.t) - 24}
              y={headerHeight - 24}
              width="48"
              height="16"
              rx="4"
              fill="#083344"
              stroke="#06b6d4"
              strokeWidth="1"
            />
            <text
              x={xScale(vc.t)}
              y={headerHeight - 12}
              fill="#22d3ee"
              fontSize="9"
              fontWeight="bold"
              fontFamily="monospace"
              textAnchor="middle"
            >
              v{vc.fromV}→v{vc.toV}
            </text>
          </g>
        ))}

        {/* 3. Top Lane: User Speech Envelope */}
        <g>
          {/* Lane Label */}
          <text
            x={marginLeft - 12}
            y={headerHeight + speechLaneHeight / 2 + 4}
            fill="#38bdf8"
            fontSize="11"
            fontWeight="600"
            fontFamily="monospace"
            textAnchor="end"
          >
            USER SPEECH
          </text>

          {/* Speech Track background */}
          <rect
            x={marginLeft}
            y={headerHeight}
            width={width - marginLeft - marginRight}
            height={speechLaneHeight}
            fill="#0f172a"
            rx="6"
            stroke="#1e293b"
            strokeWidth="1"
          />

          {/* Speech Audio Waveform Area */}
          {speechEnvelopes.map((sp, idx) => {
            const x1 = xScale(sp.startT);
            const x2 = xScale(sp.endT);
            const w = Math.max(x2 - x1, 40);
            return (
              <g key={idx}>
                <rect
                  x={x1}
                  y={headerHeight + 4}
                  width={w}
                  height={speechLaneHeight - 8}
                  fill="url(#speechGrad)"
                  stroke="#0284c7"
                  strokeWidth="1.5"
                  rx="4"
                />
                {/* Simulated Audio Wave lines inside speech bubble */}
                <path
                  d={`M ${x1 + 6} ${headerHeight + speechLaneHeight / 2} Q ${x1 + w / 4} ${
                    headerHeight + 8
                  }, ${x1 + w / 2} ${headerHeight + speechLaneHeight / 2} T ${x2 - 6} ${
                    headerHeight + speechLaneHeight / 2
                  }`}
                  fill="none"
                  stroke="#38bdf8"
                  strokeWidth="1.5"
                  strokeOpacity="0.6"
                />
                {sp.text && (
                  <text
                    x={x1 + 10}
                    y={headerHeight + speechLaneHeight / 2 + 3}
                    fill="#e0f2fe"
                    fontSize="10"
                    fontStyle="italic"
                  >
                    “{sp.text}”
                  </text>
                )}
              </g>
            );
          })}

          {/* 4. Freeze Marker & Lead-Time Bracket inside Speech Envelope */}
          {freezes.map((fz, idx) => {
            const fzX = xScale(fz.t);
            const endX = xScale(fz.endT);
            return (
              <g key={idx}>
                {/* Vertical Freeze Line */}
                <line
                  x1={fzX}
                  y1={headerHeight + 2}
                  x2={fzX}
                  y2={totalHeight - 30}
                  stroke="#c084fc"
                  strokeWidth="2"
                  strokeDasharray="3,3"
                />

                {/* Freeze Badge */}
                <rect
                  x={fzX - 32}
                  y={headerHeight + 6}
                  width="64"
                  height="16"
                  rx="3"
                  fill="#581c87"
                  stroke="#a855f7"
                  strokeWidth="1"
                />
                <text
                  x={fzX}
                  y={headerHeight + 17}
                  fill="#f3e8ff"
                  fontSize="8.5"
                  fontWeight="bold"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  ⚡ FREEZE {Math.round(fz.confidence * 100)}%
                </text>

                {/* Horizontal Lead-Time Bracket stretching to utterance end */}
                <path
                  d={`M ${fzX} ${headerHeight + speechLaneHeight - 6} H ${endX} M ${fzX} ${
                    headerHeight + speechLaneHeight - 10
                  } V ${headerHeight + speechLaneHeight - 2} M ${endX} ${
                    headerHeight + speechLaneHeight - 10
                  } V ${headerHeight + speechLaneHeight - 2}`}
                  fill="none"
                  stroke="#e879f9"
                  strokeWidth="1.5"
                />
                <text
                  x={(fzX + endX) / 2}
                  y={headerHeight + speechLaneHeight - 10}
                  fill="#f5d0fe"
                  fontSize="8.5"
                  fontWeight="bold"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  {fz.leadTimeMs} ms lead time
                </text>
              </g>
            );
          })}
        </g>

        {/* 5. Compensation Arcs (from reserve_room to release_room) */}
        {compensations.map((cmp, idx) => {
          const fromX = xScale(cmp.reserveT);
          const toX = xScale(cmp.releaseT);
          const fromY = getTaskY(cmp.taskId);
          const midX = (fromX + toX) / 2;
          const arcY = fromY - 24;

          return (
            <g key={idx}>
              <path
                d={`M ${fromX} ${fromY} Q ${midX} ${arcY}, ${toX} ${fromY}`}
                fill="none"
                stroke="#f97316"
                strokeWidth="2"
                strokeDasharray="4,2"
              />
              <circle cx={toX} cy={fromY} r="4" fill="#ea580c" stroke="#fff" strokeWidth="1" />
              {/* Arc Label */}
              <text
                x={midX}
                y={arcY - 3}
                fill="#fdba74"
                fontSize="8.5"
                fontWeight="bold"
                fontFamily="monospace"
                textAnchor="middle"
              >
                COMPENSATING: release({cmp.reservationId})
              </text>
            </g>
          );
        })}

        {/* 6. Task Swimlanes & Bars */}
        {tasks.map((task, idx) => {
          const rowY = headerHeight + speechLaneHeight + idx * rowHeight;
          const centerY = rowY + rowHeight / 2;
          const startX = xScale(task.startT);
          const endX = xScale(task.endT);
          const barWidth = Math.max(endX - startX, 16);

          return (
            <g key={task.taskId}>
              {/* Lane Row Line */}
              <line
                x1={marginLeft}
                y1={rowY + rowHeight}
                x2={width - marginRight}
                y2={rowY + rowHeight}
                stroke="#1e293b"
                strokeWidth="0.8"
              />

              {/* Task Label on Left */}
              <g>
                <text
                  x={marginLeft - 12}
                  y={centerY - 2}
                  fill="#f1f5f9"
                  fontSize="11"
                  fontWeight="600"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  {task.tool}
                </text>
                <text
                  x={marginLeft - 12}
                  y={centerY + 10}
                  fill="#64748b"
                  fontSize="8.5"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  {task.speculative ? 'SPEC · ' : ''}
                  {task.effect}
                </text>
              </g>

              {/* Task Execution Duration Bar */}
              {task.status === TaskStatus.FROZEN ? (
                <rect
                  x={startX}
                  y={centerY - 9}
                  width={barWidth}
                  height={18}
                  rx="3"
                  fill="url(#diagonalHatch)"
                  stroke="#a855f7"
                  strokeWidth="1.5"
                />
              ) : task.status === TaskStatus.DONE ? (
                <rect
                  x={startX}
                  y={centerY - 9}
                  width={barWidth}
                  height={18}
                  rx="3"
                  fill="#065f46"
                  stroke="#10b981"
                  strokeWidth="1.5"
                />
              ) : (
                <rect
                  x={startX}
                  y={centerY - 9}
                  width={barWidth}
                  height={18}
                  rx="3"
                  fill="#1e3a8a"
                  stroke="#3b82f6"
                  strokeWidth="1.5"
                />
              )}

              {/* Terminal Cross Mark if Invalidated/Cancelled */}
              {task.status === TaskStatus.INVALIDATED && (
                <g transform={`translate(${endX}, ${centerY})`}>
                  <line x1="-5" y1="-5" x2="5" y2="5" stroke="#ef4444" strokeWidth="2.5" />
                  <line x1="-5" y1="5" x2="5" y2="-5" stroke="#ef4444" strokeWidth="2.5" />
                </g>
              )}
            </g>
          );
        })}

        {/* 7. Result Landing Points (COMMIT, STALE, DUPLICATE) */}
        {results.map((res, idx) => {
          const cx = xScale(res.t);
          const cy = getTaskY(res.taskId);

          if (res.verdict === Verdict.STALE) {
            // THE MONEY SHOT: Large Prominent Red Diamond with Leader Line & Text Callout
            return (
              <g
                key={idx}
                className="cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredResult(res);
                  setTooltipPos({ x: e.clientX, y: e.clientY });
                }}
                onMouseLeave={() => setHoveredResult(null)}
              >
                {/* Glow circle behind diamond */}
                <circle cx={cx} cy={cy} r="16" fill="#ef4444" fillOpacity="0.25" className="animate-ping" />

                {/* Stale Leader Line upwards to Callout Box */}
                <path
                  d={`M ${cx} ${cy - 12} L ${cx + 15} ${cy - 28} H ${cx + 140}`}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth="2"
                />

                {/* Large Red Diamond Mark */}
                <polygon
                  points={`${cx},${cy - 11} ${cx + 11},${cy} ${cx},${cy + 11} ${cx - 11},${cy}`}
                  fill="url(#staleGlow)"
                  stroke="#fee2e2"
                  strokeWidth="2"
                  filter="drop-shadow(0px 0px 6px rgba(239, 68, 68, 0.8))"
                />
                <text
                  x={cx}
                  y={cy + 3.5}
                  fill="#ffffff"
                  fontSize="8"
                  fontWeight="900"
                  textAnchor="middle"
                >
                  !
                </text>

                {/* Leader Callout Box */}
                <rect
                  x={cx + 15}
                  y={cy - 44}
                  width="130"
                  height="18"
                  rx="3"
                  fill="#450a0a"
                  stroke="#ef4444"
                  strokeWidth="1.5"
                />
                <text
                  x={cx + 20}
                  y={cy - 32}
                  fill="#fecaca"
                  fontSize="8.5"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  STALE: FP MISMATCH (v1≠v2)
                </text>
              </g>
            );
          }

          if (res.verdict === Verdict.COMMIT) {
            return (
              <g
                key={idx}
                className="cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredResult(res);
                  setTooltipPos({ x: e.clientX, y: e.clientY });
                }}
                onMouseLeave={() => setHoveredResult(null)}
              >
                <circle
                  cx={cx}
                  cy={cy}
                  r="6.5"
                  fill="#10b981"
                  stroke="#ecfdf5"
                  strokeWidth="1.5"
                  filter="drop-shadow(0px 0px 4px rgba(16, 185, 129, 0.6))"
                />
                <polyline
                  points={`${cx - 3},${cy} ${cx - 1},${cy + 2.5} ${cx + 3},${cy - 2.5}`}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth="1.5"
                />
              </g>
            );
          }

          if (res.verdict === Verdict.DUPLICATE) {
            return (
              <g
                key={idx}
                className="cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredResult(res);
                  setTooltipPos({ x: e.clientX, y: e.clientY });
                }}
                onMouseLeave={() => setHoveredResult(null)}
              >
                <rect
                  x={cx - 5}
                  y={cy - 5}
                  width="10"
                  height="10"
                  rx="2"
                  fill="#f59e0b"
                  stroke="#fef3c7"
                  strokeWidth="1.2"
                />
                <text
                  x={cx}
                  y={cy + 3}
                  fill="#000"
                  fontSize="7"
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  2x
                </text>
              </g>
            );
          }

          return null;
        })}
      </svg>

      {/* Floating Tooltip for Hovered Result */}
      {hoveredResult && tooltipPos && (
        <div
          className="fixed z-50 pointer-events-none bg-slate-900 border border-slate-700 text-slate-100 p-3 rounded-lg shadow-2xl font-mono text-xs max-w-sm"
          style={{
            top: tooltipPos.y + 15,
            left: tooltipPos.x + 15,
          }}
        >
          <div className="flex items-center space-x-2 mb-1.5">
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                hoveredResult.verdict === Verdict.COMMIT
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-700'
                  : hoveredResult.verdict === Verdict.STALE
                  ? 'bg-red-950 text-red-400 border border-red-700'
                  : 'bg-amber-950 text-amber-400 border border-amber-700'
              }`}
            >
              {hoveredResult.verdict}
            </span>
            <span className="text-slate-400 text-[11px]">task: {hoveredResult.taskId}</span>
            <span className="text-slate-400 text-[11px]">t={hoveredResult.t.toFixed(2)}s</span>
          </div>
          <div className="text-[11px] text-slate-300 bg-slate-950 p-2 rounded border border-slate-800 break-words font-sans">
            {hoveredResult.reason}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">call_id: {hoveredResult.callId}</div>
        </div>
      )}
    </div>
  );
}

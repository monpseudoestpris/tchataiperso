"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { ChevronDown, ChevronUp, Minus, Plus, RotateCcw, Sliders } from "lucide-react";

type SidebarCreativityPotentiometerProps = {
  creativity: number | null;
  inheritedCreativity?: number | null;
  inheritedSkillName?: string | null;
  hasSamplingOverrides?: boolean;
  disabled?: boolean;
  onCommitCreativity: (nextCreativity: number | null) => void;
  onOpenDetails: () => void;
};

function getCreativityPalette(c: number) {
  const clamped = Math.max(0, Math.min(1, c));
  const hue = Math.round(138 * (1 - clamped));
  const lightness = Math.round(48 - clamped * 4);
  return {
    accent: `hsl(${hue}, 74%, ${lightness}%)`,
    bg: `hsla(${hue}, 70%, 50%, 0.1)`,
    border: `hsla(${hue}, 65%, 46%, 0.35)`,
  };
}

function getCreativityLevelLabel(c: number): string {
  if (c <= 0.05) return "Strict (sans souvenirs)";
  if (c <= 0.25) return "Précis & factuel";
  if (c <= 0.55) return "Équilibré";
  if (c <= 0.8) return "Créatif";
  return "Audacieux (souvenirs max)";
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

export function SidebarCreativityPotentiometer({
  creativity,
  inheritedCreativity = null,
  inheritedSkillName = null,
  hasSamplingOverrides = false,
  disabled = false,
  onCommitCreativity,
  onOpenDetails,
}: SidebarCreativityPotentiometerProps) {
  const effectiveSourceValue = creativity ?? inheritedCreativity ?? 0.2;
  const [expanded, setExpanded] = useState(false);
  const [dragValue, setDragValue] = useState<number | null>(null);
  const knobRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ latestVal: number } | null>(null);

  const isDragging = dragValue !== null;
  const displayVal = dragValue ?? effectiveSourceValue;
  const pct = Math.round(displayVal * 100);
  const palette = getCreativityPalette(displayVal);
  const currentAngle = -135 + displayVal * 270;

  const isCustom = creativity !== null;
  const isInherited = creativity === null && inheritedCreativity !== null;

  const summaryText = isCustom
    ? `${pct} %${hasSamplingOverrides ? "+" : ""}`
    : isInherited
      ? `${inheritedSkillName ? `${inheritedSkillName} · ` : ""}${pct} %`
      : `Auto · ${pct} %`;

  function clampStep(val: number): number {
    const clamped = Math.max(0, Math.min(1, val));
    return Number((Math.round(clamped * 20) / 20).toFixed(2));
  }

  function calculateValueFromPointer(clientX: number, clientY: number): number {
    if (!knobRef.current) return displayVal;
    const rect = knobRef.current.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = clientX - cx;
    const dy = clientY - cy;

    const rad = Math.atan2(dx, -dy);
    let deg = (rad * 180) / Math.PI;
    if (deg < -135) deg = -135;
    else if (deg > 135) deg = 135;

    return clampStep((deg + 135) / 270);
  }

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const nextVal = calculateValueFromPointer(e.clientX, e.clientY);
    dragRef.current = { latestVal: nextVal };
    setDragValue(nextVal);
  }

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!isDragging || !dragRef.current || disabled) return;
    const nextVal = calculateValueFromPointer(e.clientX, e.clientY);
    dragRef.current.latestVal = nextVal;
    setDragValue(nextVal);
  }

  function finishDrag(e: PointerEvent<HTMLDivElement>) {
    if (!isDragging || !dragRef.current) return;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    const finalVal = dragRef.current.latestVal;
    dragRef.current = null;
    setDragValue(null);
    onCommitCreativity(finalVal);
  }

  function handleWheel(e: WheelEvent<HTMLDivElement>) {
    if (disabled) return;
    e.preventDefault();
    const step = e.deltaY < 0 ? 0.05 : -0.05;
    onCommitCreativity(clampStep(displayVal + step));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    let next: number | null = null;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") next = clampStep(displayVal + 0.05);
    else if (e.key === "ArrowDown" || e.key === "ArrowLeft") next = clampStep(displayVal - 0.05);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = 1;
    if (next !== null) {
      e.preventDefault();
      onCommitCreativity(next);
    }
  }

  function nudge(delta: number) {
    if (disabled) return;
    onCommitCreativity(clampStep(displayVal + delta));
  }

  const bgArc = describeArc(37, 37, 30, -135, 135);
  const activeArc = displayVal > 0.01 ? describeArc(37, 37, 30, -135, currentAngle) : "";
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="sidebar-pot-compact-wrap">
      <button
        type="button"
        className={`sidebar-pot-compact ${expanded ? "is-open" : ""}`}
        aria-expanded={expanded}
        onClick={() => setExpanded((prev) => !prev)}
        title="Afficher ou masquer le potentiomètre de créativité"
      >
        <span className="sidebar-pot-compact-dot" style={{ backgroundColor: palette.accent }} aria-hidden="true" />
        <Sliders size={13} />
        <span className="sidebar-pot-compact-label">Créativité</span>
        <span className="sidebar-pot-compact-val">{summaryText}</span>
        {expanded ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
      </button>

      {expanded && (
        <div
          className="sidebar-creativity-potentiometer"
          title="Potentiomètre de créativité : tournez la molette au doigt/souris, ou utilisez les boutons +/-"
        >
          <div className="sidebar-pot-knob-wrapper">
            <div
              ref={knobRef}
              role="slider"
              tabIndex={disabled ? -1 : 0}
              aria-label="Potentiomètre rotatif de créativité"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              aria-valuetext={`${pct} % (${getCreativityLevelLabel(displayVal)})`}
              className={`sidebar-rotary-knob ${isDragging ? "is-turning" : ""} ${disabled ? "is-disabled" : ""}`}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={finishDrag}
              onPointerCancel={finishDrag}
              onWheel={handleWheel}
              onKeyDown={handleKeyDown}
            >
              <svg width="74" height="74" viewBox="0 0 74 74" aria-hidden="true">
                {ticks.map((t) => {
                  const ang = -135 + t * 270;
                  const p1 = polarToCartesian(37, 37, 33.5, ang);
                  const p2 = polarToCartesian(37, 37, 36.5, ang);
                  return (
                    <line
                      key={t}
                      x1={p1.x}
                      y1={p1.y}
                      x2={p2.x}
                      y2={p2.y}
                      stroke={t <= displayVal ? palette.accent : "var(--border-strong)"}
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  );
                })}

                <path
                  d={bgArc}
                  fill="none"
                  stroke="var(--border-subtle)"
                  strokeWidth="5"
                  strokeLinecap="round"
                />

                {activeArc && (
                  <path
                    d={activeArc}
                    fill="none"
                    stroke={palette.accent}
                    strokeWidth="5.5"
                    strokeLinecap="round"
                  />
                )}

                <circle
                  cx="37"
                  cy="37"
                  r="22"
                  fill="var(--bg-surface)"
                  stroke={palette.border}
                  strokeWidth="2"
                />
                <circle
                  cx="37"
                  cy="37"
                  r="18"
                  fill={palette.bg}
                  stroke="var(--border-subtle)"
                  strokeWidth="1"
                />

                <g transform={`rotate(${currentAngle} 37 37)`}>
                  <line
                    x1="37"
                    y1="37"
                    x2="37"
                    y2="20"
                    stroke={palette.accent}
                    strokeWidth="3.2"
                    strokeLinecap="round"
                  />
                  <circle cx="37" cy="22.5" r="2.8" fill={palette.accent} />
                  <circle cx="37" cy="37" r="4" fill={palette.accent} />
                </g>
              </svg>
            </div>

            <div className="sidebar-pot-quick-nudge">
              <button
                type="button"
                className="sidebar-pot-nudge-btn"
                disabled={disabled || displayVal <= 0}
                onClick={() => nudge(-0.05)}
                title="Diminuer la créativité (-5%)"
                aria-label="Diminuer la créativité"
              >
                <Minus size={11} />
              </button>
              <span className="sidebar-pot-nudge-pct">{pct}%</span>
              <button
                type="button"
                className="sidebar-pot-nudge-btn"
                disabled={disabled || displayVal >= 1}
                onClick={() => nudge(0.05)}
                title="Augmenter la créativité (+5%)"
                aria-label="Augmenter la créativité"
              >
                <Plus size={11} />
              </button>
            </div>
          </div>

          <div className="sidebar-pot-info">
            <div className="sidebar-pot-top-row">
              <strong className="sidebar-pot-name">Créativité</strong>
              <div className="sidebar-pot-actions">
                {isCustom && (
                  <button
                    type="button"
                    className="sidebar-pot-icon-btn"
                    disabled={disabled}
                    onClick={() => onCommitCreativity(null)}
                    title="Revenir au réglage Auto"
                    aria-label="Réinitialiser la créativité en mode Auto"
                  >
                    <RotateCcw size={12} />
                  </button>
                )}
                <button
                  type="button"
                  className="sidebar-pot-icon-btn"
                  onClick={onOpenDetails}
                  title="Réglages détaillés des 13 paramètres"
                  aria-label="Réglages détaillés de créativité"
                >
                  <Sliders size={12} />
                </button>
              </div>
            </div>

            <div className="sidebar-pot-status-row">
              <span className="sidebar-pot-value">{summaryText}</span>
            </div>

            <span className="sidebar-pot-hint">{getCreativityLevelLabel(displayVal)}</span>

            <div className="sidebar-pot-preset-chips">
              {[
                { label: "10%", val: 0.1, name: "Précis" },
                { label: "40%", val: 0.4, name: "Équilibré" },
                { label: "70%", val: 0.7, name: "Créatif" },
                { label: "95%", val: 0.95, name: "Audacieux" },
              ].map((p) => {
                const isSelected = isCustom && Math.abs(displayVal - p.val) < 0.04;
                return (
                  <button
                    key={p.label}
                    type="button"
                    className={`sidebar-pot-chip ${isSelected ? "is-selected" : ""}`}
                    disabled={disabled}
                    onClick={() => onCommitCreativity(p.val)}
                    title={`${p.name} (${p.label})`}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { RotateCcw, Sliders, Minus, Plus } from "lucide-react";

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
  const lightness = Math.round(52 - clamped * 4);
  return {
    accent: `hsl(${hue}, 84%, ${lightness}%)`,
    text: `hsl(${hue}, 80%, ${Math.round(28 + clamped * 12)}%)`,
    bg: `hsla(${hue}, 85%, 52%, 0.12)`,
    border: `hsla(${hue}, 80%, 46%, 0.45)`,
    glow: `hsla(${hue}, 90%, 50%, 0.35)`,
  };
}

function getCreativityLevelLabel(c: number): string {
  if (c <= 0.2) return "Précis & factuel";
  if (c <= 0.45) return "Équilibré";
  if (c <= 0.75) return "Créatif";
  return "Audacieux";
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
  const [draftValue, setDraftValue] = useState<number>(effectiveSourceValue);
  const [isDragging, setIsDragging] = useState(false);
  const knobRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ latestVal: number } | null>(null);

  useEffect(() => {
    if (!isDragging) {
      setDraftValue(creativity ?? inheritedCreativity ?? 0.2);
    }
  }, [creativity, inheritedCreativity, isDragging]);

  const displayVal = isDragging ? draftValue : effectiveSourceValue;
  const pct = Math.round(displayVal * 100);
  const palette = getCreativityPalette(displayVal);
  // Rotary sweep: -135 deg (0%) to +135 deg (100%)
  const currentAngle = -135 + displayVal * 270;

  const isCustom = creativity !== null;
  const isInherited = creativity === null && inheritedCreativity !== null;

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

    // Angle in degrees where 0 deg is North (top), 90 East, 180 South, -90 West
    const rad = Math.atan2(dx, -dy);
    let deg = (rad * 180) / Math.PI; // -180 to 180

    // Arc active from -135 deg to +135 deg. Dead zone is [-180, -135) and (135, 180] (bottom 90 degrees)
    if (deg < -135) {
      // In bottom-left dead zone: snap to 0% if closer to -135
      deg = -135;
    } else if (deg > 135) {
      // In bottom-right dead zone: snap to 100% if closer to 135
      deg = 135;
    }

    const ratio = (deg + 135) / 270;
    return clampStep(ratio);
  }

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const nextVal = calculateValueFromPointer(e.clientX, e.clientY);
    dragRef.current = { latestVal: nextVal };
    setIsDragging(true);
    setDraftValue(nextVal);
  }

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!isDragging || !dragRef.current || disabled) return;
    const nextVal = calculateValueFromPointer(e.clientX, e.clientY);
    dragRef.current.latestVal = nextVal;
    setDraftValue(nextVal);
  }

  function finishDrag(e: PointerEvent<HTMLDivElement>) {
    if (!isDragging || !dragRef.current) return;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    const finalVal = dragRef.current.latestVal;
    dragRef.current = null;
    setIsDragging(false);
    onCommitCreativity(finalVal);
  }

  function handleWheel(e: WheelEvent<HTMLDivElement>) {
    if (disabled) return;
    e.preventDefault();
    const step = e.deltaY < 0 ? 0.05 : -0.05;
    const next = clampStep(displayVal + step);
    setDraftValue(next);
    onCommitCreativity(next);
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
      setDraftValue(next);
      onCommitCreativity(next);
    }
  }

  function nudge(delta: number) {
    if (disabled) return;
    const next = clampStep(displayVal + delta);
    setDraftValue(next);
    onCommitCreativity(next);
  }

  // 74x74 viewBox, center (37, 37), radius 30
  const bgArc = describeArc(37, 37, 30, -135, 135);
  const activeArc = displayVal > 0.01 ? describeArc(37, 37, 30, -135, currentAngle) : "";
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div
      className="sidebar-creativity-potentiometer"
      style={{
        background: palette.bg,
        borderColor: palette.border,
      }}
      title="Potentiomètre de créativité : tournez directement la molette au doigt/souris, ou utilisez la molette et les boutons +/-"
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
            {/* Scale ticks */}
            {ticks.map(t => {
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
                  stroke={t <= displayVal ? palette.accent : "#cbd5e1"}
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              );
            })}

            {/* Inactive background track */}
            <path
              d={bgArc}
              fill="none"
              stroke="rgba(148, 163, 184, 0.3)"
              strokeWidth="5"
              strokeLinecap="round"
            />

            {/* Active colored arc */}
            {activeArc && (
              <path
                d={activeArc}
                fill="none"
                stroke={palette.accent}
                strokeWidth="5.5"
                strokeLinecap="round"
              />
            )}

            {/* Outer knob body */}
            <circle
              cx="37"
              cy="37"
              r="22"
              fill="#ffffff"
              stroke={palette.border}
              strokeWidth="2.2"
              style={{ filter: `drop-shadow(0 3px 8px ${palette.glow})` }}
            />
            {/* Metallic grooved inner circle */}
            <circle
              cx="37"
              cy="37"
              r="18"
              fill={palette.bg}
              stroke="rgba(255,255,255,0.9)"
              strokeWidth="1.2"
            />

            {/* Rotating needle pointer line + grip dot */}
            <g transform={`rotate(${currentAngle} 37 37)`}>
              <line
                x1="37"
                y1="37"
                x2="37"
                y2="20"
                stroke={palette.accent}
                strokeWidth="3.6"
                strokeLinecap="round"
              />
              <circle cx="37" cy="22.5" r="3" fill={palette.accent} />
              <circle cx="37" cy="37" r="4.2" fill={palette.accent} />
            </g>
          </svg>
        </div>

        {/* Quick step buttons underneath knob */}
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
          <span
            className="sidebar-pot-value"
            style={{
              color: palette.text,
              background: "#ffffff",
              borderColor: palette.border,
            }}
          >
            {isCustom
              ? `${pct} %${hasSamplingOverrides ? "+" : ""}`
              : isInherited
                ? `${inheritedSkillName ? `${inheritedSkillName} · ` : ""}${pct} %`
                : `Auto · ${pct} %`}
          </span>
        </div>

        <span className="sidebar-pot-hint" style={{ color: palette.text }}>
          {getCreativityLevelLabel(displayVal)}
        </span>

        {/* 4 Clickable quick presets */}
        <div className="sidebar-pot-preset-chips">
          {[
            { label: "10%", val: 0.1, name: "Précis" },
            { label: "40%", val: 0.4, name: "Équilibré" },
            { label: "70%", val: 0.7, name: "Créatif" },
            { label: "95%", val: 0.95, name: "Audacieux" },
          ].map(p => {
            const isSelected = isCustom && Math.abs(displayVal - p.val) < 0.04;
            return (
              <button
                key={p.label}
                type="button"
                className={`sidebar-pot-chip ${isSelected ? "is-selected" : ""}`}
                disabled={disabled}
                onClick={() => {
                  setDraftValue(p.val);
                  onCommitCreativity(p.val);
                }}
                title={`${p.name} (${p.label})`}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

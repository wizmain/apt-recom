"use client";

import { useState } from "react";
import {
  BUDGET_MAX_EOK,
  BUDGET_MIN_EOK,
  SLIDER_STEPS,
  applyBudgetChange,
  eokToSlider,
  isBudgetUnbounded,
  sliderToEok,
} from "./budgetScale";

const UNBOUNDED_PLACEHOLDER = "제한 없음";

/** 프리셋 = 상한(억) 바로가기. 하한은 제한 없음으로 되돌린다. */
const BUDGET_PRESETS_EOK = [3, 5, 7, 10, 15, 20, 30];

const SLIDER_CLASS =
  "pointer-events-none absolute inset-0 h-5 w-full appearance-none bg-transparent " +
  "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 " +
  "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full " +
  "[&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:ring-2 [&::-webkit-slider-thumb]:ring-white " +
  "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 " +
  "[&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-blue-600";

interface BudgetRangeProps {
  budgetMin: number;
  budgetMax: number;
  onChange: (range: { min: number; max: number }) => void;
}

/** 예산(억) 입력 — 숫자 입력 2개 + 이중 슬라이더 + 상한 프리셋. */
export default function BudgetRange({ budgetMin, budgetMax, onChange }: BudgetRangeProps) {
  // 입력 중인 원문(유효 범위 밖 중간 입력 "1"→"15" 허용). null = 편집 안 함.
  const [draft, setDraft] = useState<{ edge: "min" | "max"; text: string } | null>(null);
  const current = { min: budgetMin, max: budgetMax };

  /** 입력 중에는 draft 만 갱신하고, blur/Enter 에서만 반영한다(중간 키 입력이 상대 값을 밀지 않게). */
  const commitDraft = () => {
    if (draft === null) return;
    // 빈 입력 = 제한 없음(해당 끝 값).
    const isBlank = draft.text.trim() === "";
    const parsed = isBlank ? (draft.edge === "min" ? BUDGET_MIN_EOK : BUDGET_MAX_EOK) : Number(draft.text);
    const isValid =
      !Number.isNaN(parsed) &&
      parsed >= BUDGET_MIN_EOK &&
      parsed <= BUDGET_MAX_EOK;
    setDraft(null); // 유효하지 않으면 현재 확정 값으로 되돌린다.
    if (isValid) onChange(applyBudgetChange(draft.edge, parsed, current));
  };

  /** 끝 값(제한 없음)은 빈 칸 + placeholder 로 보여준다. */
  const inputValue = (edge: "min" | "max", value: number) => {
    if (draft?.edge === edge) return draft.text;
    return isBudgetUnbounded(edge, value) ? "" : String(value);
  };

  const numberInput = (edge: "min" | "max", value: number, label: string) => (
    <label className="flex items-center gap-1 text-sm text-gray-600">
      <span className="sr-only">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        aria-label={label}
        min={BUDGET_MIN_EOK}
        max={BUDGET_MAX_EOK}
        step={0.5}
        placeholder={UNBOUNDED_PLACEHOLDER}
        value={inputValue(edge, value)}
        onChange={(e) => setDraft({ edge, text: e.target.value })}
        onBlur={commitDraft}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitDraft();
        }}
        className="w-24 rounded-lg border border-gray-300 px-2 py-1 text-right text-sm"
      />
      억
    </label>
  );

  const slider = (edge: "min" | "max", value: number, label: string) => (
    <input
      type="range"
      aria-label={label}
      min={0}
      max={SLIDER_STEPS}
      step={1}
      value={Math.round(eokToSlider(value))}
      onChange={(e) => {
        setDraft(null);
        onChange(applyBudgetChange(edge, sliderToEok(Number(e.target.value)), current));
      }}
      className={SLIDER_CLASS}
    />
  );

  const leftPct = eokToSlider(budgetMin) / 10;
  const rightPct = eokToSlider(budgetMax) / 10;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {numberInput("min", budgetMin, "예산 하한(억)")}
        <span className="text-gray-400">~</span>
        {numberInput("max", budgetMax, "예산 상한(억)")}
      </div>
      <div className="relative mt-3 h-5">
        <div className="absolute left-0 right-0 top-2 h-1 rounded bg-gray-200" />
        <div
          className="absolute top-2 h-1 rounded bg-blue-500"
          style={{ left: `${leftPct}%`, right: `${100 - rightPct}%` }}
        />
        {slider("min", budgetMin, "예산 하한 슬라이더")}
        {slider("max", budgetMax, "예산 상한 슬라이더")}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {BUDGET_PRESETS_EOK.map((eok) => (
          <button
            key={eok}
            type="button"
            onClick={() => {
              setDraft(null);
              onChange({ min: BUDGET_MIN_EOK, max: eok });
            }}
            className={`rounded-full border px-2.5 py-1 text-xs ${
              budgetMax === eok
                ? "border-blue-600 bg-blue-600 text-white"
                : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            ~{eok}억
          </button>
        ))}
      </div>
    </div>
  );
}

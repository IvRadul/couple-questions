"use client";

import { useState } from "react";
import type { QuestionType, QuestionOptionOut } from "@/types";

interface Props {
  questionType: QuestionType;
  options: QuestionOptionOut[];
  disabled: boolean;
  onSubmitText: (text: string) => void;
  onSubmitOption: (optionId: number, text: string) => void;
  placeholder?: string;
}

export default function AnswerInput({
  questionType,
  options,
  disabled,
  onSubmitText,
  onSubmitOption,
  placeholder,
}: Props) {
  const [value, setValue] = useState("");

  function handleTextSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmitText(trimmed);
    setValue("");
  }

  if (questionType === "choice") {
    return (
      <div className="flex flex-col gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            onClick={() => onSubmitOption(option.id, option.text)}
            className="w-full text-left rounded-xl border border-gray-300 px-4 py-3 transition hover:border-primary hover:bg-primary-light/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {option.text}
          </button>
        ))}
      </div>
    );
  }

  return (
    <form onSubmit={handleTextSubmit} className="flex flex-col gap-3">
      <textarea
        className="input min-h-[100px] resize-none"
        placeholder={placeholder || "Введите ваш ответ..."}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
      />
      <button type="submit" className="btn-primary" disabled={disabled || !value.trim()}>
        Ответить
      </button>
    </form>
  );
}

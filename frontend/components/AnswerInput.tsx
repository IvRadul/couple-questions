"use client";

import { useState } from "react";

interface Props {
  disabled: boolean;
  onSubmit: (text: string) => void;
  placeholder?: string;
}

export default function AnswerInput({ disabled, onSubmit, placeholder }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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

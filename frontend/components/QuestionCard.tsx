interface Props {
  text: string;
  category: string;
  questionType: "open" | "choice";
}

export default function QuestionCard({ text, category, questionType }: Props) {
  return (
    <div className="card text-center">
      <div className="flex items-center justify-center gap-2 mb-2">
        <span className="inline-block text-xs uppercase tracking-wide text-primary font-semibold">
          {category}
        </span>
        <span className="inline-block text-xs uppercase tracking-wide text-gray-400">
          {questionType === "choice" ? "с вариантами" : "свободный ответ"}
        </span>
      </div>
      <p className="text-xl font-medium leading-snug">{text}</p>
    </div>
  );
}

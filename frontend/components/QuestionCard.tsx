interface Props {
  text: string;
  category: string;
}

export default function QuestionCard({ text, category }: Props) {
  return (
    <div className="card text-center">
      <span className="inline-block text-xs uppercase tracking-wide text-primary font-semibold mb-2">
        {category}
      </span>
      <p className="text-xl font-medium leading-snug">{text}</p>
    </div>
  );
}

interface Props {
  role: "answerer" | "guesser";
}

export default function RoleBanner({ role }: Props) {
  const isAnswerer = role === "answerer";
  return (
    <div
      className={`rounded-xl px-4 py-3 text-center text-white ${
        isAnswerer ? "bg-primary" : "bg-indigo-500"
      }`}
    >
      <p className="font-semibold">
        {isAnswerer ? "🎤 Ваша роль — отвечать за себя" : "🔍 Ваша роль — угадывать"}
      </p>
      <p className="text-xs opacity-90 mt-0.5">
        {isAnswerer
          ? "Отвечайте искренне, как есть на самом деле"
          : "Попробуйте угадать, что ответит партнёр"}
      </p>
    </div>
  );
}

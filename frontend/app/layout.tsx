import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Вопросы для пары",
  description: "Игра для двоих: узнайте, насколько хорошо вы знаете друг друга",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="min-h-screen text-gray-800">
        <main className="max-w-xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}

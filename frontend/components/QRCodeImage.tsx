"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

interface Props {
  value: string;
  size?: number;
}

export default function QRCodeImage({ value, size = 200 }: Props) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(value, { width: size, margin: 1 })
      .then((url) => {
        if (!cancelled) setDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [value, size]);

  if (error) {
    return null; // ссылка/код текстом всё равно показаны рядом — QR необязателен
  }

  if (!dataUrl) {
    return <div className="bg-gray-100 rounded-xl animate-pulse" style={{ width: size, height: size }} />;
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={dataUrl} alt="QR-код приглашения" width={size} height={size} className="rounded-xl mx-auto" />;
}

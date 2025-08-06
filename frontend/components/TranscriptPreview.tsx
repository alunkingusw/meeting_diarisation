'use client';

import { useEffect, useState } from "react";

export default function TranscriptPreview({ url }: { url: string }) {
  const [content, setContent] = useState<string>("Loading...");

  useEffect(() => {
    fetch(url)
      .then(res => res.text())
      .then(setContent)
      .catch(() => setContent("Failed to load transcript."));
  }, [url]);

  return <div>{content}</div>;
}

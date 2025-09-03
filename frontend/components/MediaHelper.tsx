/*
 * Copyright 2025 Alun King
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React from "react";

type MediaFile = {
  id: number;
  human_name?: string;
  url?: string;
};

type Meeting = {
  id: number;
  media_files?: MediaFile[];
};

const mediaStates = {
  noMedia: {
    text: "No media uploaded yet. Add audio or transcripts so the meeting content can be processed.",
    style: "border border-red-500 bg-red-100 text-red-800 p-3 rounded",
  },
  needsProcessing: {
    text: "Audio uploaded but not yet processed. Process the media to generate a transcript.",
    style: "border border-yellow-500 bg-yellow-100 text-yellow-800 p-3 rounded",
  },
  ready: {
    text: "Meeting has a transcript. The content is ready for use by the software.",
    style: "border border-green-500 bg-green-100 text-green-800 p-3 rounded",
  },
};

function getMediaStatus(meeting: Meeting) {
  if (!meeting || !meeting.media_files || meeting.media_files.length === 0) {
    return "noMedia";
  }

  const hasAudio = meeting.media_files.some((file) =>
    /\.(mp3|m4a|wav)$/i.test(file.human_name || file.url || "")
  );
  const hasTranscript = meeting.media_files.some((file) =>
    /\.(json|txt|vtt|srt)$/i.test(file.human_name || file.url || "")
  );

  if (hasTranscript) return "ready";
  if (hasAudio) return "needsProcessing";
  return "noMedia";
}

export default function MediaHelper({ meeting }: { meeting: Meeting }) {
  const status = getMediaStatus(meeting);
  const { text, style } = mediaStates[status];
  return <div className={style}>{text}</div>;
}

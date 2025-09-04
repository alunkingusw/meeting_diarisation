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

'use client';

import { useEffect, useState } from "react";
import { MediaFile } from '@/components/MediaHelper';
import Cookies from 'js-cookie';
import { FaTimes } from "react-icons/fa";
import { FaExpand } from "react-icons/fa";


export default function TranscriptPreview({
  groupId,
  meetingId,
  selectedMedia,
}: {
  groupId: number;
  meetingId: number;
  selectedMedia: MediaFile | null;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [isFullScreen, setIsFullScreen] = useState(false);

  useEffect(() => {
    const token = Cookies.get('token');
    
    if (!selectedMedia) {
      setContent("");
      return;
    }

    const fetchTranscript = async () => {
      if(!selectedMedia?.file_name){
        setContent("⚠️ Failed to load transcript.");
        return;
      }
      try {
        const url = `${process.env.NEXT_PUBLIC_API_URL}/files/media/${groupId}/${meetingId}/${encodeURIComponent(selectedMedia.file_name)}`;
        const response = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const text = await response.text();
        setContent(text);
      } catch (err) {
        console.error("Failed to fetch transcript", err);
        setContent("⚠️ Failed to load transcript.");
      }
    };

    fetchTranscript();
  }, [groupId, meetingId, selectedMedia]);

  if (!content) return <p className="text-sm text-gray-500 italic">Loading transcript...</p>;

  const transcriptBox = (
    <pre className="text-sm font-mono whitespace-pre-wrap">{content}</pre>
  );

  return (
    <>
      <div className="relative">
        <button
          onClick={() => setIsFullScreen(true)}
          className="absolute top-2 right-2 bg-blue-600 text-white px-2 py-1 text-xs rounded hover:bg-blue-700"
          aria-label="Enter fullscreen"
          role="dialog"
          aria-modal="true"
        >
          <FaExpand />
        </button>
        {transcriptBox}
      </div>

      {isFullScreen && (
        <div className="fixed inset-0 bg-black bg-opacity-80 z-50 flex flex-col">
          <div className="flex justify-between items-center p-4 bg-gray-900 text-white">
            <h2 className="text-lg font-semibold">{selectedMedia?.human_name}</h2>
            <button onClick={() => setIsFullScreen(false)} aria-label="Close fullscreen">
              <FaTimes/>
            </button>
          </div>
          <div className="flex-1 overflow-auto p-6 bg-white">
            {transcriptBox}
          </div>
        </div>
      )}
    </>
  );
}
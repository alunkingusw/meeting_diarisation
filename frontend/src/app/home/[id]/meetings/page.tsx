// app/home/[id]/meetings/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

export default function MeetingsPage() {
  const { id } = useParams();
  const [meetings, setMeetings] = useState<any[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<any>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => res.json())
      .then(setMeetings)
      .catch(console.error);
  }, [id]);

  return (
    <main className="p-6">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Meetings</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 🗓 Meeting List */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Meeting Dates</h2>
          <ul className="text-sm text-blue-600">
            {meetings.map(meeting => (
              <li key={meeting.id}>
                <button
                  onClick={() => setSelectedMeeting(meeting)}
                  className="hover:underline"
                >
                  {new Date(meeting.date).toLocaleDateString()}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* 📄 Meeting Info */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Meeting Info</h2>
          {selectedMeeting ? (
            <>
              <p><strong>Date:</strong> {new Date(selectedMeeting.date).toLocaleDateString()}</p>
              <p><strong>Time:</strong> {selectedMeeting.time}</p>
              <p className="mt-4 font-medium">Attendees:</p>
              <ul className="list-disc pl-5">
                {selectedMeeting.attendees?.map((a: any) => (
                  <li key={a.id}>{a.username}</li>
                ))}
              </ul>
            </>
          ) : (
            <p>Select a meeting to view details.</p>
          )}
        </div>

        {/* 🗂 Media */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Media</h2>
          {selectedMeeting?.media?.length ? (
            <ul className="list-disc pl-5">
              {selectedMeeting.media.map((m: any) => (
                <li key={m.id}>
                  <a href={m.url} target="_blank" className="text-blue-500 hover:underline">
                    {m.filename}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p>No media uploaded for this meeting.</p>
          )}
        </div>
      </div>
    </main>
  );
}

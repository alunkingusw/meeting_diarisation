// app/home/[id]/meetings/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';

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
      <Link href={`/home`} className="text-blue-500 hover:underline">
          back to groups
        </Link>
      {/* Tabs */}
      <ul className="mb-4 flex flex-wrap text-sm font-medium text-center text-gray-500 border-b border-gray-200 dark:border-gray-700 dark:text-gray-400">
        <li className="me-2">
        <Link href={`/home/${id}`}>
          <span className="text-blue-600 hover:underline inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300">Group Overview</span>
        </Link>
        </li>
        <li className="me-2">
        <Link href={`/home/${id}/meetings`}>
          <span className="text-blue-600 hover:underline inline-block p-4 text-blue-600 bg-gray-100 rounded-t-lg active dark:bg-gray-800 dark:text-blue-500">View Meetings</span>
        </Link>
        </li>
      </ul>
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

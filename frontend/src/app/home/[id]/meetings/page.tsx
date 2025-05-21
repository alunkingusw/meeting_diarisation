// app/home/[id]/meetings/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';

export default function MeetingsPage() {
  const { id } = useParams();
  const [meetings, setMeetings] = useState<any[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<any>(null);
  const [creating, setCreating] = useState(false);
  const [newMeetingDate, setNewMeetingDate] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [groupMembers, setGroupMembers] = useState<any[]>([]);

  const isAttending = (memberId: number) => {
    return selectedMeeting?.attendees?.some((a: any) => a.id === memberId);
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
     // Fetch group members
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/members`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    .then(res => res.json())
    .then(data => setGroupMembers(data))
    .catch(console.error);

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => res.json())
      .then(setMeetings)
      .catch(console.error);
  }, [id]);

  const handleSelectMeeting = async (meetingId: number) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings/${meetingId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
      console.error("Failed to fetch meeting details");
      return null;
    }

    const data = await res.json();
    
    setSelectedMeeting(data);
  };

  const handleAddGuest = async(e:React.FormEvent) => {

      e.preventDefault();
      const form = e.target as HTMLFormElement;
      const nameInput = form.elements.namedItem('guestName') as HTMLInputElement;
      const guestName = nameInput.value.trim();
      if (!guestName) return;

      const token = localStorage.getItem('token');
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings/${selectedMeeting.id}/attendees/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: guestName, guest: true }),
      });

      if (res.ok) {
        nameInput.value = '';
        handleSelectMeeting(selectedMeeting.id);
      } else {
        alert('Failed to add guest');
      }
    }

  const handleToggleAttendance = async (memberId: number, present: boolean) => {
  const token = localStorage.getItem('token');
  const url = `${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings/${selectedMeeting.id}/attendees/`;

  const res = await fetch(url, {
    method: present ? 'POST' : 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ member_id: memberId }),
  });

  if (!res.ok) {
    console.error('Failed to update attendance');
  } else {
    // Refresh or update selectedMeeting if needed
  }
};

  const handleCreateMeeting = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMeetingDate.trim()) return;

    const token = localStorage.getItem('token');
    setCreating(true);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ date: newMeetingDate }),
    });

    if (res.ok) {
      const createdMeeting = await res.json();
      setMeetings([...meetings, createdMeeting]);
      setNewMeetingDate('');
    } else {
      const errorText = await res.text(); // Capture the error message if available
      console.error("Failed to create meeting:", res.status, res.statusText, errorText);
      alert('Failed to create meeting');
    }

    setCreating(false);
  };
  const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const files = event.dataTransfer.files;
    if (files.length === 0) return;

    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${process.env.NEXT_PUBLIC_API_URL}/groups/${id}/meetings/${selectedMeeting.id}/upload`);

    xhr.setRequestHeader('Authorization', `Bearer ${localStorage.getItem('token')}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setUploading(false);
      setUploadProgress(null);
      if (xhr.status === 200) {
        alert('Upload successful!');
        //add file to list.
      } else {
        alert('Upload failed.');
      }
    };

    xhr.onerror = () => {
      setUploading(false);
      setUploadProgress(null);
      alert('Upload error.');
    };

    xhr.send(formData);
  };


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
        {/* Meeting List */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Meeting Dates</h2>
          {meetings && meetings.length > 0?(
         
          
          <ul className="text-sm text-blue-600">
            {meetings.map(meeting => (
              <li key={meeting.id}>
                <button
                  onClick={() => handleSelectMeeting(meeting.id)}
                  className="hover:underline"
                >
                  {new Date(meeting.date).toLocaleDateString()}
                </button>
              </li>
            ))}
          </ul>
          ):(
            <p className="text-sm text-gray-500 italic"> No meetings yet</p>
          )}
          {/* Meeting creation form */}
      <form onSubmit={handleCreateMeeting} className="mt-4">
        <label htmlFor="meetingDate" className="block text-sm font-medium text-gray-700 mb-1">
          Add a new meeting
        </label>
        <div className="flex gap-2">
          <input
            id="meetingDate"
            type="date"
            value={newMeetingDate}
            onChange={e => setNewMeetingDate(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 w-full"
            placeholder="Meeting date"
            disabled={creating}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={creating}
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
        </div>

        {/* Meeting Info */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Meeting Info</h2>
          {selectedMeeting ? (
            <>
              <p><strong>Date:</strong> {new Date(selectedMeeting.date).toLocaleDateString()}</p>
              <p><strong>Time:</strong> {selectedMeeting.time}</p>
              <p className="mt-4 font-medium">Attendees:</p>
              <ul className="divide-y">
  {groupMembers.map((member) => {
    const attending = isAttending(member.id);

    

    return (
      <li key={member.id} className="flex items-center justify-between py-2">
        <span>{member.name}</span>
        <label className="inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={attending}
            onChange={(e) => handleToggleAttendance(member.id, e.target.checked)}
          />
          <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-blue-600 transition-all"></div>
        </label>
      </li>
    );
  })}
</ul><div className="mt-6">
  <h3 className="font-semibold">Add Guest</h3>
  <form
    onSubmit={handleAddGuest} 
    className="mt-2 flex gap-2"
  >
    <input
      type="text"
      name="guestName"
      placeholder="Guest name"
      className="border px-3 py-1 rounded w-full"
    />
    <button
      type="submit"
      className="bg-blue-600 text-white px-4 py-1 rounded hover:bg-blue-700"
    >
      Add
    </button>
  </form>
</div>
            </>
          ) : (
            <p>Select a meeting to view details.</p>
          )}
        </div>
{/* Media */}
<div className="bg-white rounded-xl shadow p-4">
  <h2 className="font-semibold mb-2">Media</h2>

  {!selectedMeeting ? (
    <p>Select a meeting to view or upload media</p>
  ) : (
    <>
      {/* Media List */}
      {selectedMeeting.media_files?.length > 0 ? (
        <ul className="list-disc pl-5 mb-4">
          {selectedMeeting.media_files.map((m: any) => (
            <li key={m.id}>
              <a
                href={m.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                {m.human_name}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-gray-600 mb-4">No media currently available</p>
      )}

      {/* Upload Box */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="border-2 border-dashed border-gray-400 p-6 rounded-xl text-center"
      >
        <p className="text-gray-600">Drag and drop a file here to upload</p>

        {uploading && (
          <div className="mt-4 w-full bg-gray-200 rounded-full">
            <div
              className="bg-blue-600 text-xs leading-none py-1 text-center text-white rounded-full"
              style={{ width: `${uploadProgress}%` }}
            >
              {uploadProgress}%
            </div>
          </div>
        )}
      </div>
    </>
  )}
</div>
        
      </div>
    </main>
  );
}

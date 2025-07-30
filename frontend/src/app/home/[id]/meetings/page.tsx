// app/home/[id]/meetings/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { CiCircleInfo } from "react-icons/ci";

import Link from 'next/link';
import { useGroupManager, Person } from '@/hooks/groupManager';
import { useMeetingManager } from '@/hooks/meetingManager';
import {useMediaManager} from '@/hooks/mediaManager'
import Cookies from 'js-cookie';

export default function MeetingsPage() {
  const { id } = useParams();
  const [showHelp, setShowHelp] = useState(false);
  const {groupMembers, fetchGroupMembers, fetchGroupMeetings, meetings} = useGroupManager();
  const {handleAddGuest, handleSelectMeeting, newMeetingDate, setNewMeetingDate, creatingMeeting, selectedMeeting, handleToggleAttendance, isAttending, handleCreateMeeting} = useMeetingManager();
  const {isValidFile, uploading, uploadProgress, handleDrop} = useMediaManager();
  useEffect(() => {
    fetchGroupMembers(Number(id))
    fetchGroupMeetings(Number(id))
    
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
        <Link href={`/home/${id}/members`}>
          <span className="text-blue-600 hover:underline inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300">View Members</span>
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
                  onClick={() => handleSelectMeeting(Number(id), meeting.id)}
                  className={`hover:underline ${
        selectedMeeting?.id === meeting.id ? 'font-semibold text-blue-600' : 'text-blue-600'
      }`}>
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
          <input name="groupId" type="hidden" value={id}/>
          <input
            id="meetingDate"
            type="date"
            value={newMeetingDate}
            onChange={e => setNewMeetingDate(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 w-full"
            placeholder="Meeting date"
            disabled={creatingMeeting}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={creatingMeeting}
          >
            {creatingMeeting ? 'Creating...' : 'Create'}
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
              </ul>
              {/* Guests */}
              <div className="mt-6">
                <h3 className="font-semibold">Guests</h3>
                <ul className="divide-y">
                  {selectedMeeting.attendees
                    .filter((att:Person) => !groupMembers.some(member => member.id === att.id))
                    .map((guest:Person) => (
                      <li key={guest.id} className="flex items-center justify-between py-2">
                        <span>{guest.name || 'Unnamed Guest'}</span>
                        <label className="inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          className="sr-only peer"
                          checked={true}
                          onChange={(e) => handleToggleAttendance(guest.id, e.target.checked)}
                        />
                        <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-blue-600 transition-all"></div>
                      </label>
                      </li>
                    ))
                  }
                  {selectedMeeting.attendees.filter((att:Person) => !groupMembers.some(m => m.id === att.id)).length === 0 && (
                    <li className="text-sm text-gray-500 italic">No guests</li>
                  )}
                </ul>
              </div>

              <div className="mt-6">
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
<div className="bg-white rounded-xl shadow p-4 relative">
  <div className="flex items-center justify-between mb-2">
    <h2 className="font-semibold">Media</h2>
    <button
      onClick={() => setShowHelp(!showHelp)}
      className="text-gray-400 hover:text-gray-600"
      aria-label="Media help"
    >
      <CiCircleInfo size={20}/>
     
    </button>
  </div>

  {/* Help Box */}
  {showHelp && (
    <div className="mb-4 p-3 text-sm bg-blue-50 border border-blue-200 rounded">
      <p className="text-blue-700">
        You can upload audio and transcript files here for diarisation.<br/>Supported audio formats are MP3, M4A, and WAV.<br />Supported transcription formats are JSON*, VTT*, SRT*, and TXT. (*preferred).<br/><br />Uploading audio along with existing transcripts is helpful, as transcripts can be used to train the AI on the meeting participants and improve recognition of individuals.
      </p>
    </div>
  )}

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
        onDrop={(e) => {
          e.preventDefault();
          const files = Array.from(e.dataTransfer.files);
          const validFiles = files.filter(isValidFile);

          if (validFiles.length === 0) {
            alert("Unsupported file type. Please upload audio (.wav, .mp3, .m4a) or transcript (.json, .vtt, .srt, .txt) files. Click the info icon for help");
            return;
          }

          handleDrop(Number(id), selectedMeeting.id)(e); // Pass through if valid
        }}
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

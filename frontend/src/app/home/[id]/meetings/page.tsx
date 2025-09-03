// app/home/[id]/meetings/page.tsx
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

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { CiCircleInfo } from "react-icons/ci";
import { FaCog } from "react-icons/fa";

import Link from 'next/link';
import { useGroupManager, Person } from '@/hooks/groupManager';
import { useMeetingManager } from '@/hooks/meetingManager';
import { useMediaManager } from '@/hooks/mediaManager'
import NavigationTabs from '@/components/NavigationTabs';
import TranscriptPreview from '@/components/TranscriptPreview';
import MediaHelper from '@/components/MediaHelper';
import Cookies from 'js-cookie';


export default function MeetingsPage() {
  const { id } = useParams();
  const [showHelp, setShowHelp] = useState(false);
  const [openDropdownId, setOpenDropdownId] = useState<number | null>(null);
  const { groupMembers, fetchGroupMembers, fetchGroupMeetings, meetings, group, getGroup } = useGroupManager();
  const { handleAddGuest, handleSelectMeeting, newMeetingDate, setNewMeetingDate, creatingMeeting, selectedMeeting, handleToggleAttendance, isAttending, handleCreateMeeting, handleDeleteMeeting } = useMeetingManager();
  const { isValidMeetingFile, uploading, uploadProgress, handleDrop } = useMediaManager();
  const [selectedMedia, setSelectedMedia] = useState<any | null>(null);
  useEffect(() => {
    getGroup(Number(id))
    fetchGroupMembers(Number(id))
    fetchGroupMeetings(Number(id))
  }, [id]);

  // Show fallback if group wasn't loaded or access was denied
  if (!group) return <p>Group not found or access denied.</p>;


  return (
    <main className="p-6">
      <Link href={`/home`} className="text-blue-500 hover:underline">
        back to groups
      </Link>
      {/* Tabs */}
      <NavigationTabs groupId={Number(id)} />
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Meetings</h1>
      </div>

      {/* Main View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Meeting List & Info */}
        <div className="space-y-6">
          <div className="bg-white rounded-xl shadow p-4">
            <h2 className="font-semibold mb-2">Meeting Dates</h2>
            {meetings && meetings.length > 0 ? (


              <ul className="text-sm text-blue-600">
                {meetings.map(meeting => (
                  <li key={meeting.id}>
                    <div className="flex items-center justify-between">
                      <button
                        onClick={() => handleSelectMeeting(Number(id), meeting.id)}
                        className={`hover:underline ${selectedMeeting?.id === meeting.id ? 'font-semibold text-blue-600' : 'text-blue-600'
                          }`}>
                        {new Date(meeting.date).toLocaleDateString()}
                      </button>
                      <div className="relative ml-2">
                        <button
                          onClick={() =>
                            setOpenDropdownId(openDropdownId === meeting.id ? null : meeting.id)
                          }
                          className="text-gray-600 hover:text-gray-800">
                          <FaCog />

                        </button>
                        {openDropdownId === meeting.id && (
                          <div className="absolute right-0 mt-2 w-32 bg-white shadow-lg rounded border z-10">
                            <button
                              onClick={() => handleDeleteMeeting(group.id, meeting.id)}
                              className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-gray-100"
                            >
                              Delete Meeting
                            </button>
                          </div>
                        )}
                      </div></div>
                  </li>
                ))}
              </ul>
            ) : (
              <p> No meetings yet</p>
            )}
            {/* Meeting creation form */}
            <form onSubmit={handleCreateMeeting} className="mt-4">
              <label htmlFor="meetingDate" className="block text-sm font-medium text-gray-700 mb-1">
                Add a new meeting
              </label>
              <div className="flex gap-2">
                <input name="groupId" type="hidden" value={id} />
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
                      .filter((att: Person) => !groupMembers.some(member => member.id === att.id))
                      .map((guest: Person) => (
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
                    {selectedMeeting.attendees.filter((att: Person) => !groupMembers.some(m => m.id === att.id)).length === 0 && (
                      <li className="text-sm text-gray-500 italic">No guests</li>
                    )}
                  </ul>
                </div>

                <div className="mt-6">
                  <h3 className="font-semibold">Add Guest</h3>
                  <form onSubmit={handleAddGuest} className="mt-2 flex gap-2">
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
              <CiCircleInfo size={20} />

            </button>
          </div>

          {/* Help Box */}
          {showHelp && (
            <div className="mb-4 p-3 text-sm bg-blue-50 border border-blue-200 rounded">
              <p className="text-blue-700">
                You can upload audio and transcript files here for diarisation.<br />Supported audio formats are MP3, M4A, and WAV.<br />Supported transcription formats are JSON*, VTT*, SRT*, and TXT. (*preferred).<br /><br />Uploading audio along with existing transcripts is helpful, as transcripts can be used to train the AI on the meeting participants and improve recognition of individuals.
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
                      <button
                        onClick={() => setSelectedMedia(m)}
                        className="text-blue-600 hover:underline"
                      >
                        {m.human_name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No media currently available</p>
              )}

              {/* Media Helper */}
              {selectedMeeting && <MediaHelper meeting={selectedMeeting} />}

              {/* Upload Box */}
              <div
                onDrop={(e) => {
                  e.preventDefault();
                  const files = Array.from(e.dataTransfer.files);
                  const validFiles = files.filter(isValidMeetingFile);

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
        {/* Media Preview */}
        <div className="bg-white rounded-xl shadow p-4">
          <h2 className="font-semibold mb-2">Media Viewer</h2>
          {!selectedMedia ? (
    <p className="text-sm text-gray-600 italic">Select a media file to preview it here.</p>
  ) : (
    <div className="mt-2">
      <h3 className="font-medium mb-2">{selectedMedia.human_name}</h3>

      {/* Audio Player */}
      {selectedMedia?.url?.match(/\.(mp3|m4a|wav)$/i) && (
        <audio controls className="w-full">
          <source src={selectedMedia.url} />
          Your browser does not support the audio element.
        </audio>
      )}

      {/* Transcript Preview */}
      {selectedMedia?.url?.match(/\.(json|txt|vtt|srt)$/i) && (
        <div className="bg-gray-50 border border-gray-200 rounded p-3 max-h-60 overflow-auto text-sm font-mono whitespace-pre-wrap">
          <TranscriptPreview url={selectedMedia.url} />
        </div>
      )}
    </div>
  )}
        </div>
      </div>
    </main>
  );
}

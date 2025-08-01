// app/home/[id]/members/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { CiCircleInfo } from "react-icons/ci";

import Link from 'next/link';
import { useGroupManager, Person } from '@/hooks/groupManager';
import { useMeetingManager } from '@/hooks/meetingManager';
import {useMediaManager, EmbeddingAudioPlayer} from '@/hooks/mediaManager'
import Cookies from 'js-cookie'; 

export default function MembersPage() {
  const { id } = useParams();
  const [showHelp, setShowHelp] = useState(false);
  const {loading, getGroup, group, groupMembers, error, selectedMember, setSelectedMember, newMemberName, setNewMemberName, handleCreateMember, fetchGroupMembers} = useGroupManager();
  const {isValidMeetingFile, isValidAudioFile, uploading, uploadProgress, handleEmbeddingAudioDrop} = useMediaManager();
  useEffect(() => {
    if (!id) return;
    getGroup(Number(id));
    fetchGroupMembers(Number(id))
  
  if (selectedMember) {
    console.log("Selected member:", selectedMember);
  }
  }, [id, selectedMember]);

   // Show fallback if group wasn't loaded or access was denied
  if (!group) return <p>Group not found or access denied.</p>;
  


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
          <span className="text-blue-600 hover:underline inline-block p-4 text-blue-600 bg-gray-100 rounded-t-lg active dark:bg-gray-800 dark:text-blue-500">View Members</span>
        </Link>
        </li>
        <li className="me-2">
        <Link href={`/home/${id}/meetings`}>
          <span className="text-blue-600 hover:underline inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300">View Meetings</span>
        </Link>
        </li>
      </ul>
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Members</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Side: Members List and Add Form */}
        <div className="lg:col-span-1 space-y-4">
        {group.members && group.members.length > 0?(
          <ul className="text-sm list-disc pl-5">

            
            {group.members?.map((m: Person) => (
              <li key={m.id}>
                <button onClick={() => setSelectedMember(m)}
      className={`hover:underline ${
        selectedMember?.id === m.id ? 'font-semibold text-blue-600' : 'text-blue-600'
      }`}>{m.name}</button></li>
            ))}
          </ul>
          ):(
            <p className="text-sm text-gray-500 italic"> No members yet</p>
          )}

          {/* Add Member Form */}
  <form
    onSubmit={handleCreateMember}
    className="mt-4 space-y-2"
  >
    <label htmlFor="name" className="block text-sm font-medium text-gray-700">
      Add Member
    </label>
    <input
      type="text"
      name="name"
      id="name"
      value={newMemberName}
      onChange={e => setNewMemberName(e.target.value)}
      required
      className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
      placeholder="New member name"
    />
    <button
      type="submit"
      className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 text-sm"
    >
      Add Member
    </button>
  </form>
        </div>
        

        {/* Member Info */}
        <div className="bg-white rounded-xl shadow p-4 lg:col-span-1">
          <h2 className="font-semibold mb-2">Member Info</h2>
          {selectedMember ? (
            
  <div>
    <p><strong>Name:</strong> {selectedMember.name}</p>
    <p><strong>ID:</strong> {selectedMember.id}</p>
    {selectedMember?.embedding_audio_path ? (
  <EmbeddingAudioPlayer selectedMember={selectedMember} />
) : (
  <p className="text-sm text-gray-400 italic mt-4">No embedding audio available.</p>
)}
{/* Upload embedding section*/}
    <div className="mt-6">
  <h3 className="text-sm font-medium text-gray-700 mb-2">Upload embedding Audio</h3>
  <div
    onDrop={(e) => {
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files);
      const validFiles = files.filter(isValidAudioFile);

          if (validFiles.length === 0) {
            alert("Unsupported file type. Please upload audio (.wav, .mp3, .m4a) files. Click the info icon for help");
            return;
          }
      

      handleEmbeddingAudioDrop(group.id, selectedMember.id, validFiles[0]);
    }}
    onDragOver={(e) => e.preventDefault()}
    className="border-2 border-dashed border-gray-400 p-6 rounded-xl text-center"
  >
    <p className="text-gray-600">Drag and drop a reference audio file here</p>

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
</div>
  </div>
) : (
  <p className="text-sm text-gray-500 italic">Select a member to view details.</p>
)}
        </div>

        


  {/* Help Box */}
  {showHelp && (
    <div className="mb-4 p-3 text-sm bg-blue-50 border border-blue-200 rounded">
      <p className="text-blue-700">
        You can upload audio and transcript files here for diarisation.<br/>Supported audio formats are MP3, M4A, and WAV.<br />Supported transcription formats are JSON*, VTT*, SRT*, and TXT. (*preferred).<br/><br />Uploading audio along with existing transcripts is helpful, as transcripts can be used to train the AI on the meeting participants and improve recognition of individuals.
      </p>
    </div>
  )}

  

     </div>   

    </main>
  );
}

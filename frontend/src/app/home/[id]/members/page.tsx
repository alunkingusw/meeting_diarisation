// app/home/[id]/members/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { FaCog } from "react-icons/fa";

import Link from 'next/link';
import { useGroupManager, Person } from '@/hooks/groupManager';
import { useMediaManager, EmbeddingAudioPlayer } from '@/hooks/mediaManager'
import NavigationTabs from '@/components/NavigationTabs';
import Cookies from 'js-cookie';

export default function MembersPage() {
  const { id } = useParams();

  const [openDropdownId, setOpenDropdownId] = useState<number | null>(null);
  const { loading, getGroup, group, groupMembers, error, selectedMember, setSelectedMember, newMemberName, setNewMemberName, handleCreateMember, handleRemoveMember, fetchGroupMembers } = useGroupManager();
  const { isValidMeetingFile, isValidAudioFile, uploading, uploadProgress, handleEmbeddingAudioDrop } = useMediaManager();
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
      <NavigationTabs groupId={Number(id)} />
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Members</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Side: Members List and Add Form */}
        <div className="lg:col-span-1 space-y-4">
          {group.members && group.members.length > 0 ? (
            <ul className="text-sm list-disc pl-5">


              {group.members?.map((m: Person) => (
                <li key={m.id}>
                  <div className="flex items-center justify-between">
                    <button onClick={() => setSelectedMember(m)}
                      className={`hover:underline ${selectedMember?.id === m.id ? 'font-semibold text-blue-600' : 'text-blue-600'
                        }`}>{m.name}</button>
                    <div className="relative ml-2">
                      <button
                        onClick={() =>
                          setOpenDropdownId(openDropdownId === m.id ? null : m.id)
                        }
                        className="text-gray-600 hover:text-gray-800">
                        <FaCog />

                      </button>

                      {openDropdownId === m.id && (
                        <div className="absolute right-0 mt-2 w-32 bg-white shadow-lg rounded border z-10">
                          <button
                            onClick={() => handleRemoveMember(group.id, m.id)}
                            className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-gray-100"
                          >
                            Remove Member
                          </button>
                        </div>
                      )}
                    </div></div></li>
              ))}
            </ul>
          ) : (
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
                      alert("Unsupported file type. Please upload audio (.wav, .mp3, .m4a) files.");
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
      </div>

    </main>
  );
}

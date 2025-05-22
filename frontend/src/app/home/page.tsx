'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FaCog } from "react-icons/fa";
import Link from 'next/link';
import { useGroupManager } from '@/hooks/groupManager';
import Cookies from 'js-cookie';

export default function HomePage() {
  const {groups, loading, error, fetchAllGroups, newGroupName, setNewGroupName, creatingGroup, handleCreateGroup, handleDelete} = useGroupManager();
  
  const [openDropdownId, setOpenDropdownId] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    const token = Cookies.get('token');
    if (!token) {
      router.replace('/');
      return;
    }
    fetchAllGroups();
    if(error){
      router.replace('/');
    }
  }, []);

   
  

  return (
    <main className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Your Groups</h1>
        
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : groups.length === 0 ? (
        <p>You do not currently have any groups.</p>
      ) : (
        <ul className="list-disc pl-5 space-y-2">
      {groups.map(group => (
        <li key={group.id} className="flex items-center justify-between">
          <Link href={`/home/${group.id}`} className="text-blue-500 hover:underline">
            {group.name}
          </Link>
          <div className="relative">
            <button
              className="ml-2"
              onClick={() =>
                setOpenDropdownId(openDropdownId === group.id ? null : group.id)
              }
            >
              <span className="text-gray-600 hover:text-gray-800">
              <FaCog />
              </span>
            </button>

            {openDropdownId === group.id && (
              <div className="absolute right-0 mt-2 w-32 bg-white shadow-lg rounded border z-10">
                <button
                  onClick={() => handleDelete(group.id)}
                  className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-gray-100"
                >
                  Delete Group
                </button>
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
      )}
      {/* Group creation form */}
      <form onSubmit={handleCreateGroup} className="mt-4">
        <label htmlFor="groupName" className="block text-sm font-medium text-gray-700 mb-1">
          Add a new group
        </label>
        <div className="flex gap-2">
          <input
            id="groupName"
            type="text"
            value={newGroupName}
            onChange={e => setNewGroupName(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 w-full"
            placeholder="Group name"
            disabled={creatingGroup}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={creatingGroup}
          >
            {creatingGroup ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
    </main>
  );
}

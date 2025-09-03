// app/home/page.tsx

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
import { useRouter } from 'next/navigation';
import { FaCog } from "react-icons/fa";
import Link from 'next/link';
import { useGroupsManager } from '@/hooks/groupsManager';
import Cookies from 'js-cookie';

export default function HomePage() {
  const {groups, loading, error, fetchAllGroups, newGroupName, setNewGroupName, creatingGroup, handleCreateGroup, handleDeleteGroup} = useGroupsManager();
  
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
                  onClick={() => handleDeleteGroup(group.id)}
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

// app/home/[id]/meetings/page.tsx
'use client'; // Required for using client-side hooks like useEffect and useRouter
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useGroupManager } from '@/hooks/groupManager';
import Cookies from 'js-cookie';

export default function GroupPage() {
  const { id } = useParams(); // Extract the group ID from the URL (/home/[id])
  const router = useRouter(); // Used to navigate/redirect programmatically
const {loading, getGroup, group, error, newMemberName, setNewMemberName, handleCreateMember} = useGroupManager();

  useEffect(() => {
    // Check for JWT token in session storage
    const token = Cookies.get('token');
    if (!token) {
      // If no token is found, redirect to login page ("/")
      console.warn('No token found, redirecting to /');
      router.push('/');
      return;
    }
    
    getGroup(Number(id));
    if(error){
      router.replace('/home')
    }
  }, [id, router]); // Re-run if ID or router changes

  // Show loading state while fetching
  if (loading) return <p>Loading group...</p>;

  // Show fallback if group wasn't loaded or access was denied
  if (!group) return <p>Group not found or access denied.</p>;

  // Render group info if successfully fetched
  return (
     <main className="p-6">
      <Link href={`/home`} className="text-blue-500 hover:underline">
          back to groups
        </Link>
      {/* Tabs */}
      <ul className="mb-4 flex flex-wrap text-sm font-medium text-center text-gray-500 border-b border-gray-200 dark:border-gray-700 dark:text-gray-400">
        <li className="me-2">
        <Link href={`/home/${id}`}>
          <span className="text-blue-600 hover:underline inline-block p-4 text-blue-600 bg-gray-100 rounded-t-lg active dark:bg-gray-800 dark:text-blue-500">Group Overview</span>
        </Link>
        </li>
        <li className="me-2">
        <Link href={`/home/${id}/members`}>
          <span className="text-blue-600 hover:underline inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300">View Members</span>
        </Link>
        </li>
        <li className="me-2">
        <Link href={`/home/${id}/meetings`}>
          <span className="text-blue-600 hover:underline inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300">View Meetings</span>
        </Link>
        </li>
      </ul>

      {/* Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sidebar */}
        <div className="bg-white shadow rounded-xl p-4">
          <h2 className="text-xl font-semibold mb-2">Group Info</h2>
          <p className="text-sm text-gray-700 mb-4">Name: {group.name}</p>
          

          <h3 className="font-medium mb-2">Members</h3>
          {group.members && group.members.length > 0?(
          <ul className="text-sm list-disc pl-5">

            
            {group.members?.map((m: any) => (
              <li key={m.id}>{m.name}</li>
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

        {/* Data column */}
        <div className="lg:col-span-2 bg-white shadow rounded-xl p-4">
          <h2 className="text-xl font-semibold mb-4">Data</h2>
          <p className="text-gray-700 text-sm">Any group-level insights or summaries can go here.</p>
        </div>
      </div>
    </main>
  );
}

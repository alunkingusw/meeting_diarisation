// app/home/[id]/meetings/page.tsx
'use client'; // Required for using client-side hooks like useEffect and useRouter
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useGroupManager } from '@/hooks/groupManager';
import Cookies from 'js-cookie';
import NavigationTabs from '@/components/NavigationTabs';

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
      <NavigationTabs groupId={Number(id)} />

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
            <p className="text-sm text-gray-500 italic"> No members yet. Go to 'members' tab to manage members.</p>
          )}

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

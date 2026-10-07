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

'use client'; // Required for using client-side hooks like useEffect and useRouter
import Link from 'next/link';
import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useGroupManager } from '@/hooks/groupManager';
import NavigationTabs from '@/components/NavigationTabs';
import GroupLoadState from '@/components/GroupLoadState';

export default function GroupPage() {
  const { id } = useParams(); // Extract the group ID from the URL (/home/[id])
  const {loading, getGroup, group, error} = useGroupManager();

  useEffect(() => {
    const controller = new AbortController();
    getGroup(Number(id), controller.signal);
    return () => controller.abort();
  }, [id, getGroup]);

  if (loading || error || !group) return <GroupLoadState loading={loading} error={error} />;

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

            
            {group.members?.map(m => (
              <li key={m.id}>{m.name}</li>
            ))}
          </ul>
          ):(
            <p className="text-sm text-gray-500 italic"> No members yet. Go to the members tab to manage members.</p>
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

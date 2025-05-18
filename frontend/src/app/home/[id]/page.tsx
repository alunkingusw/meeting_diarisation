'use client'; // Required for using client-side hooks like useEffect and useRouter
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';

// Define the structure of a Group object
interface Group {
  id: number;
  name: string;
  // You can add other fields as needed, e.g., description, members, etc.
}

export default function GroupPage() {
  const { id } = useParams(); // Extract the group ID from the URL (/home/[id])
  const router = useRouter(); // Used to navigate/redirect programmatically

  const [group, setGroup] = useState<Group | null>(null); // Holds the group data
  const [loading, setLoading] = useState(true); // Track loading state
  const [showMeetings, setShowMeetings] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [showData, setShowData] = useState(true); // Data visible by default

  useEffect(() => {
    // Check for JWT token in session storage
    const token = localStorage.getItem('token');
    if (!token) {
      // If no token is found, redirect to login page ("/")
      console.warn('No token found, redirecting to /');
      router.push('/');
      return;
    }

    // Fetch the group from the backend using the token
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}`, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`, // Include token in Authorization header
      },
    })
      .then(async res => {
        // If user is unauthorized or forbidden, redirect to login
        if (res.status === 403 || res.status === 401) {
          console.warn('Unauthorized access, redirecting to /');
          router.push('/home');
          return null;
        }else if(res.status === 404){
          console.warn('Group not found, redirecting to /');
          router.push('/home');
          return null;
        }
        // Parse response JSON
        return res.json();
      })
      .then(data => {
        if (data) {
          setGroup(data); // Store group data in state
        }
      })
      .finally(() => setLoading(false)); // Mark loading complete
  }, [id, router]); // Re-run if ID or router changes

  // Show loading state while fetching
  if (loading) return <p>Loading group...</p>;

  // Show fallback if group wasn't loaded or access was denied
  if (!group) return <p>Group not found or access denied.</p>;

  // Render group info if successfully fetched
  return (
     <main className="p-6">
      {/* Tabs */}
      <div className="mb-4">
        <Link href={`/home/${id}/meetings`}>
          <span className="text-blue-600 hover:underline">View Meetings</span>
        </Link>
      </div>

      {/* Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sidebar */}
        <div className="bg-white shadow rounded-xl p-4">
          <h2 className="text-xl font-semibold mb-2">Group Info</h2>
          <p className="text-sm text-gray-700 mb-4">{group.description}</p>

          <h3 className="font-medium mb-2">Members</h3>
          <ul className="text-sm list-disc pl-5">
            {group.members?.map((m: any) => (
              <li key={m.id}>{m.username}</li>
            ))}
          </ul>
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

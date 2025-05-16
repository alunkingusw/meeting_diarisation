'use client'; // Required for using client-side hooks like useEffect and useRouter

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

  useEffect(() => {
    // Check for JWT token in session storage
    const token = sessionStorage.getItem('token');
    if (!token) {
      // If no token is found, redirect to login page ("/")
      router.push('/');
      return;
    }

    // Fetch the group from the backend using the token
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${id}`, {
      headers: {
        Authorization: `Bearer ${token}`, // Include token in Authorization header
      },
    })
      .then(async res => {
        // If user is unauthorized or forbidden, redirect to login
        if (res.status === 403 || res.status === 401) {
          router.push('/');
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
      <h1 className="text-2xl font-bold mb-4">{group.name}</h1>
      {/* Add more group details here if needed */}
    </main>
  );
}

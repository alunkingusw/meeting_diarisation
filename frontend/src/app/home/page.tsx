'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FaCog } from "react-icons/fa";
import Link from 'next/link';
interface Group {
  id: number;
  name: string;
}

export default function HomePage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [newGroupName, setNewGroupName] = useState('');
  const [creating, setCreating] = useState(false);
  const [openDropdownId, setOpenDropdownId] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.replace('/');
      return;
    }

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then(res => {
        if (!res.ok) {
          throw new Error("Unauthorized");
        }
        return res.json();
      })
      .then(data => {
        setGroups(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        localStorage.removeItem('token');
        router.replace('/');
      });
  }, []);

   const handleDelete = async (groupId: number) => {
    const confirmed = confirm("Are you sure you want to delete this group? This will delete all associated data!!");
    if (!confirmed) return;

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
      });

      if (res.ok) {
        // Update the group list
        setGroups(prev => prev.filter(group => group.id !== groupId));
      } else {
        alert("Failed to delete group");
      }
    } catch (error) {
      console.error("Error deleting group:", error);
    }
  };
  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;

    const token = localStorage.getItem('token');
    setCreating(true);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ name: newGroupName }),
    });

    if (res.ok) {
      const createdGroup = await res.json();
      setGroups([...groups, createdGroup]);
      setNewGroupName('');
    } else {
      const errorText = await res.text(); // Capture the error message if available
      console.error("Failed to create group:", res.status, res.statusText, errorText);
      alert('Failed to create group');
    }

    setCreating(false);
  };

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
            disabled={creating}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={creating}
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
    </main>
  );
}

'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

interface Group {
  id: number;
  name: string;
}

export default function HomePage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
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

  const handleLogout = () => {
    localStorage.removeItem('token');
    router.push('/');
  };

  return (
    <main className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Your Groups</h1>
        <button
          onClick={handleLogout}
          className="text-sm px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
        >
          Logout
        </button>
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : groups.length === 0 ? (
        <p>You do not currently have any groups.</p>
      ) : (
        <ul className="list-disc pl-5">
          {groups.map(group => (
            <li key={group.id}>
        <a href={`/home/${group.id}`} className="text-blue-500 hover:underline">
          {group.name}
        </a>
      </li>
          ))}
        </ul>
      )}
    </main>
  );
}

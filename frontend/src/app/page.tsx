'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

interface User {
  id: number;
  username: string;
}

export default function Home() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/users`)
      .then(res => res.json())
      .then(data => {
        setUsers(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch users:", err);
        setLoading(false);
      });
  }, []);
  // Login and navigate
  const handleUserSelect = async (userId: number) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/users/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId }),
      });

      if (!res.ok) throw new Error("Failed to authenticate");

      const data = await res.json();
      const token = data.token;

      // Save token for future use (you can use localStorage or cookie)
      localStorage.setItem('token', token);

      // Redirect to /home
      router.push('/home');
    } catch (err) {
      console.error("Login error:", err);
    }
  };

  return (
    
    <main style={{ padding: "2rem" }}>
      <div className="flex min-h-full flex-col justify-center px-6 py-12 lg:px-8">
  <div className="sm:mx-auto sm:w-full sm:max-w-sm">
    <h2 className="mt-10 text-center text-2xl/9 font-bold tracking-tight text-gray-900">Select your account</h2>
  </div>

  <div className="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
     
    {loading ? (
            <p>Loading users...</p>
          ) : users.length === 0 ? (
            <p>No users found.</p>
          ) : (
            <div>
              {users.map(user => (
                <button
                  key={user.id}
                  onClick={() => handleUserSelect(user.id)}
                  className="block w-full text-left text-blue-600 hover:underline my-2"
                >
                  {user.username}
                </button>
              ))}
            </div>
          )}

    <p className="mt-10 text-center text-sm/6 text-gray-500">
      Not a user?
      <a href="#" className="font-semibold text-indigo-600 hover:text-indigo-500">Sign up</a>
    </p>
  </div>
</div>
     
    </main>
  );
}
'use client';
import { useEffect, useState } from 'react';

interface User {
  id: number;
  username: string;
}

export default function Home() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUser, setSelectedUser] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/users`)
      .then(res => res.json())
      .then(setUsers);
  }, []);

  return (
    <main style={{ padding: "2rem" }}>
      <h1>Select a User</h1>
      <select onChange={(e) => setSelectedUser(Number(e.target.value))}>
        <option value="">-- Select --</option>
        {users.map(user => (
          <option key={user.id} value={user.id}>{user.username}</option>
        ))}
      </select>

      {selectedUser && (
        <p>Selected User: {users.find(u => u.id === selectedUser)?.username}</p>
      )}
    </main>
  );
}
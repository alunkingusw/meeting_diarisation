// components/Header.tsx — client component
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

export default function Header() {
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    setLoggedIn(!!token);
  }, []);

  return (
    <header className="bg-blue-600 text-white p-4 flex justify-between items-center">
      <Link href="/">Group Diarisation</Link>
      {loggedIn ? (
        <button
          onClick={() => {
            localStorage.removeItem('token');
            window.location.href = '/';
          }}
        >
          Logout
        </button>
      ) : (
        <Link href="/">Login</Link>
      )}
    </header>
  );
}

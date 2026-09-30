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
'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Cookies from 'js-cookie';

export default function Home() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    const formData = new URLSearchParams({ username, password });
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/users/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData.toString(),
      });
      if (!response.ok) throw new Error('Invalid username or password.');

      const data = await response.json();
      Cookies.set('token', data.access_token, {
        expires: 1 / 24,
        sameSite: 'strict',
        secure: window.location.protocol === 'https:',
      });
      router.push('/home');
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Unable to sign in.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-6 py-12">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-6 rounded-md bg-white p-8 shadow-sm">
        <h1 className="text-center text-2xl font-semibold text-slate-900">Sign in</h1>
        <label className="block space-y-2 text-sm font-medium text-slate-700">
          Username
          <input
            autoComplete="username"
            className="w-full rounded border border-slate-300 px-3 py-2 text-slate-900"
            onChange={event => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label className="block space-y-2 text-sm font-medium text-slate-700">
          Password
          <input
            autoComplete="current-password"
            className="w-full rounded border border-slate-300 px-3 py-2 text-slate-900"
            onChange={event => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button
          className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          disabled={submitting}
          type="submit"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
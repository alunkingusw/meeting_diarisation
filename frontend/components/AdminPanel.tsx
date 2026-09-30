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

import { useEffect, useState, type FormEvent } from 'react';
import { useAdminManager } from '@/hooks/adminManager';

export default function AdminPanel() {
  const {
    users,
    loadingUsers,
    creatingUser,
    creatingGroupForUser,
    adminError,
    fetchAllUsers,
    handleCreateUser,
    handleCreateGroupForUser,
  } = useAdminManager();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);

  const [groupName, setGroupName] = useState('');
  const [ownerUserId, setOwnerUserId] = useState('');

  useEffect(() => {
    fetchAllUsers();
  }, []);

  const submitCreateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!username.trim()) return;
    const created = await handleCreateUser({ username, password: password || undefined, email, isAdmin });
    if (created) {
      setUsername('');
      setPassword('');
      setEmail('');
      setIsAdmin(false);
    }
  };

  const submitCreateGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!groupName.trim() || !ownerUserId) return;
    const created = await handleCreateGroupForUser({ name: groupName, ownerUserId: Number(ownerUserId) });
    if (created) {
      setGroupName('');
      setOwnerUserId('');
    }
  };

  return (
    <section className="mt-10 border-t pt-6">
      <h2 className="text-xl font-bold mb-4">Administration</h2>
      {adminError && <p className="text-red-600 text-sm mb-4">{adminError}</p>}

      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <h3 className="font-semibold mb-2">Users</h3>
          {loadingUsers ? (
            <p>Loading users...</p>
          ) : (
            <ul className="list-disc pl-5 space-y-1 mb-4">
              {users.map(u => (
                <li key={u.id}>
                  {u.username} {u.is_admin && <span className="text-xs text-gray-500">(admin)</span>}
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={submitCreateUser} className="space-y-2">
            <p className="text-sm font-medium text-gray-700">Add a new user</p>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Username"
              className="border border-gray-300 rounded px-3 py-2 w-full"
              disabled={creatingUser}
              required
            />
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password (optional, min. 12 characters - most users won't need one)"
              className="border border-gray-300 rounded px-3 py-2 w-full"
              disabled={creatingUser}
              minLength={12}
            />
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="Email (optional)"
              className="border border-gray-300 rounded px-3 py-2 w-full"
              disabled={creatingUser}
            />
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={e => setIsAdmin(e.target.checked)}
                disabled={creatingUser}
              />
              Grant administrator permissions
            </label>
            <button
              type="submit"
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={creatingUser}
            >
              {creatingUser ? 'Creating...' : 'Add user'}
            </button>
          </form>
        </div>

        <div>
          <h3 className="font-semibold mb-2">Create a group for a user</h3>
          <form onSubmit={submitCreateGroup} className="space-y-2">
            <input
              type="text"
              value={groupName}
              onChange={e => setGroupName(e.target.value)}
              placeholder="Group name"
              className="border border-gray-300 rounded px-3 py-2 w-full"
              disabled={creatingGroupForUser}
              required
            />
            <select
              value={ownerUserId}
              onChange={e => setOwnerUserId(e.target.value)}
              className="border border-gray-300 rounded px-3 py-2 w-full"
              disabled={creatingGroupForUser}
              required
            >
              <option value="" disabled>
                Select owner
              </option>
              {users.map(u => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={creatingGroupForUser}
            >
              {creatingGroupForUser ? 'Creating...' : 'Create group'}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

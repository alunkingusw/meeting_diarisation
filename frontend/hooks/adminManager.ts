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

import { useState } from 'react';
import { User } from '@/types/user';
import Cookies from 'js-cookie';

export function useAdminManager() {
  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [creatingUser, setCreatingUser] = useState(false);
  const [creatingGroupForUser, setCreatingGroupForUser] = useState(false);
  const [adminError, setAdminError] = useState('');

  const authHeaders = () => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${Cookies.get('token')}`,
  });

  const fetchAllUsers = async () => {
    setLoadingUsers(true);
    setAdminError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/users/`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error('Failed to load users');
      setUsers(await res.json());
    } catch (err) {
      console.error(err);
      setAdminError('Unable to load users.');
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleCreateUser = async (params: {
    username: string;
    password: string;
    email?: string;
    isAdmin?: boolean;
  }) => {
    setCreatingUser(true);
    setAdminError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/users/`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          username: params.username,
          password: params.password,
          email: params.email || null,
          is_admin: params.isAdmin ?? false,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || 'Failed to create user');
      }
      const createdUser = await res.json();
      setUsers(prev => [...prev, createdUser]);
      return createdUser as User;
    } catch (err) {
      console.error(err);
      setAdminError(err instanceof Error ? err.message : 'Failed to create user');
      return null;
    } finally {
      setCreatingUser(false);
    }
  };

  const handleCreateGroupForUser = async (params: { name: string; ownerUserId: number }) => {
    setCreatingGroupForUser(true);
    setAdminError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ name: params.name, owner_user_id: params.ownerUserId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || 'Failed to create group');
      }
      return await res.json();
    } catch (err) {
      console.error(err);
      setAdminError(err instanceof Error ? err.message : 'Failed to create group');
      return null;
    } finally {
      setCreatingGroupForUser(false);
    }
  };

  return {
    users,
    loadingUsers,
    creatingUser,
    creatingGroupForUser,
    adminError,
    fetchAllUsers,
    handleCreateUser,
    handleCreateGroupForUser,
  };
}

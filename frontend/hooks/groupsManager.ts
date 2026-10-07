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

import { useCallback, useState } from 'react';
import { Group } from '@/types/group';
import { authenticatedFetch, SessionExpiredError } from '@/lib/auth';

export function useGroupsManager() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newGroupName, setNewGroupName] = useState('');
  const [creatingGroup, setCreatingGroup] = useState(false);

  const fetchAllGroups = useCallback(async (viewAll = false, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups${viewAll ? '?all_groups=true' : ''}`, { signal });
      if (!res.ok) throw new Error(`Unable to load groups (HTTP ${res.status}).`);
      setGroups(await res.json());
    } catch (err) {
      if (signal?.aborted) return;
      if (!(err instanceof SessionExpiredError)) console.error(err);
      setError(err instanceof Error ? err.message : 'Unable to load groups.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const handleDeleteGroup = async (groupId: number) => {
    const confirmed = confirm('Are you sure you want to delete this group? This will delete all associated data!!');
    if (!confirmed) return;
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Failed to delete group (HTTP ${res.status}).`);
      setGroups(prev => prev.filter(group => group.id !== groupId));
    } catch (err) {
      if (err instanceof SessionExpiredError) return;
      console.error('Error deleting group:', err);
      alert(err instanceof Error ? err.message : 'Failed to delete group');
    }
  };

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;
    setCreatingGroup(true);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newGroupName }),
      });
      if (!res.ok) throw new Error(`Failed to create group (HTTP ${res.status}).`);
      const createdGroup = await res.json();
      setGroups(prev => [...prev, createdGroup]);
      setNewGroupName('');
    } catch (err) {
      if (err instanceof SessionExpiredError) return;
      console.error('Error creating group:', err);
      alert(err instanceof Error ? err.message : 'Failed to create group');
    } finally {
      setCreatingGroup(false);
    }
  };

  return {
    loading, error, groups, fetchAllGroups, setGroups, newGroupName, setNewGroupName,
    creatingGroup, handleCreateGroup, handleDeleteGroup,
  };
}

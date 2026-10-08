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
import { Meeting } from '@/types/meeting';
import { authenticatedFetch, checkGroupResponse, SessionExpiredError } from '@/lib/auth';

export type Person = {
  id: number;
  name: string;
  email?: string | null;
  created: string;
  embedding_audio_path?: string | null;
};

export function useGroupManager() {
  const [groupMembers, setGroupMembers] = useState<Person[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [group, setGroup] = useState<Group | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedMember, setSelectedMember] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);
  const [newMemberName, setNewMemberName] = useState('');
  const [newMemberEmail, setNewMemberEmail] = useState('');

  const getGroup = useCallback(async (groupId: number, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    setGroup(null);
    setSelectedMember(null);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}`, { signal });
      checkGroupResponse(res, 'Unable to load group');
      setGroup(await res.json());
    } catch (err) {
      if (signal?.aborted) return;
      if (!(err instanceof SessionExpiredError)) console.error('Failed to load group:', err);
      setError(err instanceof Error ? err.message : 'Unable to load group.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const updateGroupNotify = useCallback(async (notify: boolean) => {
    if (!group) throw new Error('Group is not loaded.');
    const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${group.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: group.name,
        github_repo_url: group.github_repo_url ?? null,
        trello_board_id: group.trello_board_id ?? null,
        project_expiry: group.project_expiry ?? null,
        notify,
      }),
    });
    checkGroupResponse(res, 'Unable to update group notifications');
    setGroup(current => current ? { ...current, notify } : current);
  }, [group]);

  const updateGroupProjectExpiry = useCallback(async (projectExpiry: string | null) => {
    if (!group) throw new Error('Group is not loaded.');
    const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${group.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: group.name,
        github_repo_url: group.github_repo_url ?? null,
        trello_board_id: group.trello_board_id ?? null,
        project_expiry: projectExpiry,
        notify: group.notify,
      }),
    });
    checkGroupResponse(res, 'Unable to update project expiry');
    setGroup(current => current ? { ...current, project_expiry: projectExpiry } : current);
  }, [group]);

  const fetchGroupMeetings = useCallback(async (groupId: number, signal?: AbortSignal) => {
    setMeetings([]);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings`, { signal });
      checkGroupResponse(res, 'Unable to load meetings');
      setMeetings(await res.json());
    } catch (err) {
      if (signal?.aborted) return;
      if (!(err instanceof SessionExpiredError)) console.error('Failed to load meetings:', err);
      setError(err instanceof Error ? err.message : 'Unable to load meetings.');
    }
  }, []);

  const fetchGroupMembers = useCallback(async (groupId: number, signal?: AbortSignal) => {
    setGroupMembers([]);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/members`, { signal });
      checkGroupResponse(res, 'Unable to load members');
      setGroupMembers(await res.json());
    } catch (err) {
      if (signal?.aborted) return;
      if (!(err instanceof SessionExpiredError)) console.error('Failed to load members:', err);
      setError(err instanceof Error ? err.message : 'Unable to load members.');
    }
  }, []);

  const handleCreateMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;
    try {
      if (!group?.id) return;
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${group.id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newMemberName, email: newMemberEmail || null }),
      });
      checkGroupResponse(res, 'Failed to add member');
      const createdMember = await res.json();
      setGroup({ ...group, members: [...group.members, createdMember] });
      setNewMemberName('');
      setNewMemberEmail('');
    } catch (err) {
      if (err instanceof SessionExpiredError) return;
      console.error(err);
      alert(err instanceof Error ? err.message : 'Error adding member');
    }
  };

  const handleRemoveMember = async (groupId: number, memberId: number) => {
    const confirmed = confirm('Are you sure you want to remove this member? This will delete all associated data!!');
    if (!confirmed) return;
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/members/${memberId}`, {
        method: 'DELETE',
      });
      checkGroupResponse(res, 'Failed to remove member');
      setGroupMembers(prev => prev.filter(member => member.id !== memberId));
      setGroup(prev => prev ? { ...prev, members: prev.members.filter(member => member.id !== memberId) } : prev);
      if (selectedMember?.id === memberId) setSelectedMember(null);
    } catch (err) {
      if (err instanceof SessionExpiredError) return;
      console.error('Error removing member:', err);
      alert(err instanceof Error ? err.message : 'Failed to remove member');
    }
  };

  return {
    fetchGroupMembers, fetchGroupMeetings, handleCreateMember, handleRemoveMember,
    groupMembers, meetings, loading, getGroup, updateGroupNotify, group, error,
    updateGroupProjectExpiry,
    selectedMember, setSelectedMember, newMemberName, setNewMemberName,
    newMemberEmail, setNewMemberEmail,
  };
}

import {useState, useEffect} from 'react';
import {Group} from '@/types/group';
import Cookies from 'js-cookie';

export function useGroupManager(){
    const [groups, setGroups] = useState<Group[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [newGroupName, setNewGroupName] = useState('');
    const [creatingGroup, setCreatingGroup] = useState(false);
    const [groupMembers, setGroupMembers] = useState<any[]>([]);
    const [meetings, setMeetings] = useState<any[]>([]);


    const fetchAllGroups = async() =>{
      console.log('need token')
      const token = Cookies.get('token');
      console.log(token)
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
        Cookies.remove('token')
        setError(true);
        return;
      });
    }
    
    const handleDelete = async (groupId: number) => {

    const confirmed = confirm("Are you sure you want to delete this group? This will delete all associated data!!");
    if (!confirmed) return;
    const token = Cookies.get('token');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
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

    const token = Cookies.get('token');
    setCreatingGroup(true);

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

    setCreatingGroup(false);
  };
  const fetchGroupMeetings = async(groupId:number) =>{
    const token = Cookies.get('token');
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => res.json())
      .then(setMeetings)
      .catch(console.error);
  };
  const fetchGroupMembers = async(groupId: number) => {
    const token = Cookies.get('token');
    // Fetch group members
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/members`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    .then(res => res.json())
    .then(data => setGroupMembers(data))
    .catch(console.error);
  };
  return{
    loading, 
    error,
    groups, 
    fetchAllGroups,
    fetchGroupMembers,
    fetchGroupMeetings,
    setGroups,
    newGroupName, 
    setNewGroupName,
    groupMembers,
    meetings,
    creatingGroup, 
    handleCreateGroup, 
    handleDelete
  };
}


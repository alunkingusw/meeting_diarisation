import {useState, useEffect} from 'react';
import {Group} from '@/types/group';
import Cookies from 'js-cookie';

export function useGroupManager(){
    const [groupMembers, setGroupMembers] = useState<any[]>([]);
    const [meetings, setMeetings] = useState<any[]>([]);
    const [group, setGroup] = useState<Group | null>(null)
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(true); // Track loading state
    const [newMemberName, setNewMemberName] = useState('');

  /*
   * The functions below relate to actions within a group, hence groupManager, rather than groupsManager.
   */
  const getGroup = async(groupId:number) =>{
    const token = Cookies.get('token');

    // Fetch the group from the backend using the token
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}`, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`, // Include token in Authorization header
      },
    })
      .then(async res => {
        // If user is unauthorized or forbidden, redirect to login
        if (res.status === 403 || res.status === 401) {
          console.warn('Unauthorized access, redirecting to /');
          setError(true)
          return null;
        }else if(res.status === 404){
          console.warn('Group not found, redirecting to /');
          setError(true)
          return null;
        }
        // Parse response JSON
        return res.json();
      })
      .then(data => {
        if (data) {
          setGroup(data); // Store group data in state
        }
      })
      .finally(() => setLoading(false)); // Mark loading complete
  }
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

  const handleCreateMember = async (e: React.FormEvent) => {
      e.preventDefault();
      const token = Cookies.get('token');
      if (!newMemberName.trim()) return;

      try {
        //group id should be set, but just incase it is not...
        if (!group?.id) return;
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${group.id}/members`, {
          method: "POST",
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ name:newMemberName }),
        });

        if (!res.ok) {
          throw new Error("Failed to add member");
        }else{
          const createdMember = await res.json();
          //add the new member to the list
          if(group){
            setGroup({
              ...group, members:[...group.members, createdMember],
            });
          }
          
          setNewMemberName('');
    } 
      } catch (err) {
        console.error(err);
        alert("Error adding member");
      }
    }
  return{ 
    fetchGroupMembers,
    fetchGroupMeetings,
    handleCreateMember,
    groupMembers,
    meetings,
    loading,
    getGroup,
    group,
    error,
    newMemberName,
    setNewMemberName
  };
}


import { Meeting } from '@/types/meeting';
import {useState, useEffect} from 'react';
import Cookies from 'js-cookie';

export function useMeetingManager(){
    const [selectedMeeting, setSelectedMeeting] = useState<any>(null);
    const [newMeetingDate, setNewMeetingDate] = useState('');
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [creatingMeeting, setCreatingMeeting] = useState(false);
    
    const isAttending = (memberId: number) => {
        return selectedMeeting?.attendees?.some((a: any) => a.id === memberId);
    };
    const handleSelectMeeting = async (groupId:number, meetingId: number) => {
        const token = Cookies.get('token');
        const url = `${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings/${meetingId}`;
        console.log("Fetching selected meeting from:", url);
        const res = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          console.error("Failed to fetch meeting details");
        return null;
        }

        const data = await res.json();
        console.log("Fetched meeting data:", data);
        setSelectedMeeting(data);
    };
    const handleAddGuest = async(e:React.FormEvent) => {
        e.preventDefault();
        const form = e.target as HTMLFormElement;
        const nameInput = form.elements.namedItem('guestName') as HTMLInputElement;
        const guestName = nameInput.value.trim();
        if (!guestName) return;
        
        const token = Cookies.get('token');
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${selectedMeeting.group_id}/meetings/${selectedMeeting.id}/attendees/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ name: guestName, guest: 1 }),
        });

        if (res.ok) {
            nameInput.value = '';
            handleSelectMeeting(selectedMeeting.group_id, selectedMeeting.id);
        } else {
            alert('Failed to add guest');
        }
    }

    const handleToggleAttendance = async (memberId: number, present: boolean) => {
        console.log("selected meeting", selectedMeeting)
        const token = Cookies.get('token');

        const url = present
        ? `${process.env.NEXT_PUBLIC_API_URL}/groups/${selectedMeeting.group_id}/meetings/${selectedMeeting.id}/attendees/`
        : `${process.env.NEXT_PUBLIC_API_URL}/groups/${selectedMeeting.group_id}/meetings/${selectedMeeting.id}/attendees/${memberId}`;
        
        const res = await fetch(url, {
            method: present ? 'POST' : 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: present ? JSON.stringify({ member_id: memberId }) : undefined,
        });

        if (!res.ok) {
            console.error('Failed to update attendance');
        } else {
            // Refresh or update selectedMeeting if needed
            handleSelectMeeting(selectedMeeting.group_id, selectedMeeting.id);
        }
    };

    const handleCreateMeeting = async (e: React.FormEvent) => {
        e.preventDefault();
        const form = e.currentTarget as HTMLFormElement;
        const formData = new FormData(form);
        const groupId = formData.get('groupId') as string;
        const token = Cookies.get('token');
        if (!newMeetingDate.trim()) return;

        setCreatingMeeting(true);

        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ date: newMeetingDate }),
        });

        if (res.ok) {
            const createdMeeting = await res.json();
            setMeetings([...meetings, createdMeeting]);
            setNewMeetingDate('');
        } else {
            const errorText = await res.text(); // Capture the error message if available
            console.error("Failed to create meeting:", res.status, res.statusText, errorText);
            alert('Failed to create meeting');
        }

        setCreatingMeeting(false);
    };

    const handleDeleteMeeting = async (groupId: number, meetingId: number) => {

    const confirmed = confirm("Are you sure you want to delete this meeting? This will delete all associated data!!");
    if (!confirmed) return;
    const token = Cookies.get('token');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings/${meetingId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        // Update the group list
        setMeetings(prev => prev.filter(meeting => meeting.id !== meetingId));
        if (selectedMeeting?.id === meetingId) {
          setSelectedMeeting(null);
        }
      } else {
        alert("Failed to delete meeting");
      }
    } catch (error) {
      console.error("Error deleting meeting:", error);
    }
  };

    return{
        handleSelectMeeting, 
        handleCreateMeeting,
        handleDeleteMeeting,
        newMeetingDate, 
        setNewMeetingDate, 
        creatingMeeting, 
        selectedMeeting, 
        handleToggleAttendance, 
        isAttending,
        handleAddGuest
    }
}
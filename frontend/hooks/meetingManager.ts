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
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings/${meetingId}`, {
            headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          console.error("Failed to fetch meeting details");
        return null;
        }

        const data = await res.json();
    
        setSelectedMeeting(data);
    };
    const handleAddGuest = async(e:React.FormEvent) => {
        e.preventDefault();
        const form = e.target as HTMLFormElement;
        const nameInput = form.elements.namedItem('guestName') as HTMLInputElement;
        const guestName = nameInput.value.trim();
        if (!guestName) return;

        const token = Cookies.get('token');
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/groups/${selectedMeeting.groupId}/meetings/${selectedMeeting.id}/attendees/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ name: guestName, guest: true }),
        });

        if (res.ok) {
            nameInput.value = '';
            handleSelectMeeting(selectedMeeting.groupId, selectedMeeting.id);
        } else {
            alert('Failed to add guest');
        }
    }

    const handleToggleAttendance = async (memberId: number, present: boolean) => {
        const url = `${process.env.NEXT_PUBLIC_API_URL}/groups/${selectedMeeting.groupId}/meetings/${selectedMeeting.id}/attendees/`;
        const token = Cookies.get('token');
        const res = await fetch(url, {
            method: present ? 'POST' : 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ member_id: memberId }),
        });

        if (!res.ok) {
            console.error('Failed to update attendance');
        } else {
            // Refresh or update selectedMeeting if needed
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

    return{
        handleSelectMeeting, 
        handleCreateMeeting,
        newMeetingDate, 
        setNewMeetingDate, 
        creatingMeeting, 
        selectedMeeting, 
        handleToggleAttendance, 
        isAttending,
        handleAddGuest
    }
}
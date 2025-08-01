import {useState, useEffect} from 'react';
import Cookies from 'js-cookie';
import {Person} from '@/hooks/groupManager';
import { useGroupManager } from './groupManager';
export function useMediaManager() {
    const [uploadProgress, setUploadProgress] = useState<number | null>(null);
    const [uploading, setUploading] = useState(false);
    const allowedAudioExtensions = ['.wav', '.mp3', '.m4a'];
    const allowedFileExtensions = ['.json', '.vtt', '.srt', '.txt'];

    const isValidAudioFile = (file:File) => {
      const ext = file.name.split('.').pop()?.toLowerCase();
      return ext && allowedAudioExtensions.includes(`.${ext}`);
    }

    const isValidMeetingFile = (file: File) => {
      const ext = file.name.split('.').pop()?.toLowerCase();
      return ext && (allowedAudioExtensions.includes(`.${ext}`) || (allowedFileExtensions.includes(`.${ext}`) ));
    };
    const handleDrop = (groupId: number, meetingId: number) => async (
    event: React.DragEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    const token = Cookies.get('token');

    const files = event.dataTransfer.files;
    if (files.length === 0) return;

    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/meetings/${meetingId}/upload`);

    xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setUploading(false);
      setUploadProgress(null);
      if (xhr.status === 200) {
        //add file to list.
        return true;
      } else {
        alert('Upload failed.');
      }
    };

    xhr.onerror = () => {
      setUploading(false);
      setUploadProgress(null);
      alert('Upload error.');
    };

    xhr.send(formData);
  };

  const handleEmbeddingAudioDrop = async (groupId:number, memberId: number, file:File, overwrite=false) => {
    const token = Cookies.get("token");
    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);
    
    const xhr = new XMLHttpRequest();
    const url = `${process.env.NEXT_PUBLIC_API_URL}/groups/${groupId}/members/${memberId}/embedding${overwrite ? "?overwrite=true" : ""}`;
    xhr.open("POST", url);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setUploading(false);
      setUploadProgress(0);
      if (xhr.status === 200) {
        // TODO: refresh data
        alert("Upload successful.");
      } else if (xhr.status === 409 && !overwrite) {
      const confirmOverwrite = window.confirm(
        "Reference audio already exists. Overwrite?"
      );
      if (confirmOverwrite) {
        // Retry with overwrite=true
        handleEmbeddingAudioDrop(groupId, memberId, file, true);
      }
    } else {
      alert("Upload failed.");
    }
    };

    xhr.onerror = () => {
      setUploading(false);
      setUploadProgress(0);
      alert("Upload error.");
    };

    xhr.send(formData);
  };

    return{ 
        handleDrop,
        handleEmbeddingAudioDrop,
        uploadProgress, 
        uploading,
        isValidAudioFile,
        isValidMeetingFile,
    };
    
}

export function EmbeddingAudioPlayer({ selectedMember }: { selectedMember: Person | null }) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    const token = Cookies.get('token');

    const fetchAudio = async () => {
      // check if the user has audio to fetch
      if (!selectedMember?.embedding_audio_path) {
        setAudioUrl(null);
        return;
      }

      //perform audio fetch
      try {
        const url = `${process.env.NEXT_PUBLIC_API_URL}/files/embedding/${encodeURIComponent(selectedMember.embedding_audio_path)}`;
        console.log("Fetching audio from:", url);
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/files/embedding/${encodeURIComponent(selectedMember.embedding_audio_path)}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        setAudioUrl(objectUrl);
      } catch (err) {
        console.error("Failed to fetch audio", err);
        setAudioUrl(null);
      }
    };

    fetchAudio();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedMember]);

  if (!audioUrl) return null;

  return (
    <div className="mt-4">
      <p className="text-sm text-gray-600 mb-1">Reference Audio:</p>
      <audio key={audioUrl} controls className="w-full">
        <source src={audioUrl} type="audio/mpeg" />
        Your browser does not support the audio element.
      </audio>
    </div>
  );
}
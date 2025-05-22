import {useState, useEffect} from 'react';
import Cookies from 'js-cookie';
export function useMediaManager() {
    const [uploadProgress, setUploadProgress] = useState<number | null>(null);
    const [uploading, setUploading] = useState(false);
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

    return{ 
        handleDrop,
        uploadProgress, 
        uploading,
    };
    
}
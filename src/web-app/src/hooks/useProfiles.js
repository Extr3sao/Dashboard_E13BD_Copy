import { useEffect, useState } from 'react';
import axios from 'axios';

export default function useProfiles({
  apiBase,
  onDefaultProfile,
  preferredProfile,
}) {
  const [profiles, setProfiles] = useState([]);

  useEffect(() => {
    axios.get(`${apiBase}/profiles`)
      .then((res) => {
        const availableProfiles = Array.isArray(res.data.profiles) ? res.data.profiles : [];
        const requestedProfile = String(preferredProfile || '').trim().toUpperCase();
        const resolvedRequested = availableProfiles.find(
          (profile) => String(profile || '').trim().toUpperCase() === requestedProfile,
        );
        setProfiles(availableProfiles);
        onDefaultProfile(resolvedRequested || res.data.default || availableProfiles[0] || '');
      })
      .catch((err) => console.error('Error carregant perfils', err));
  }, [apiBase, onDefaultProfile, preferredProfile]);

  return {
    profiles,
    setProfiles,
  };
}

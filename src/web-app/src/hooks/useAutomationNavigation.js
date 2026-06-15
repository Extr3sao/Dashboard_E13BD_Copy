import { useEffect, useRef, useState } from 'react';
import { AUTOMATION_SCREENS, buildDefaultSectionState, SECTION_IDS } from '../config/automationViewConfig.js';

export function useAutomationNavigation() {
  const sectionRefs = useRef({});
  const [helpOpen, setHelpOpen] = useState(false);
  const [openSections, setOpenSections] = useState(buildDefaultSectionState);
  const [automationSection, setAutomationSectionState] = useState(() => localStorage.getItem('automationSection') || 'jobs');

  useEffect(() => {
    localStorage.setItem('automationSection', automationSection);
  }, [automationSection]);

  const setAutomationSection = (nextSection) => {
    setAutomationSectionState(nextSection);
    const screen = AUTOMATION_SCREENS.find((item) => item.id === nextSection);
    if (screen?.sections?.length) {
      setOpenSections((current) => ({
        ...current,
        ...Object.fromEntries(screen.sections.map((sectionId) => [sectionId, true])),
      }));
    }
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const toggleSection = (sectionId) => {
    setOpenSections((current) => ({ ...current, [sectionId]: !current[sectionId] }));
  };

  const setAllSectionsOpen = (open) => {
    setOpenSections(Object.fromEntries(SECTION_IDS.map((id) => [id, open])));
  };

  const registerSection = (sectionId) => (node) => {
    if (!node) {
      delete sectionRefs.current[sectionId];
      return;
    }
    sectionRefs.current[sectionId] = node;
  };

  return {
    automationSection,
    helpOpen,
    openSections,
    registerSection,
    sectionRefs,
    setAllSectionsOpen,
    setAutomationSection,
    setHelpOpen,
    setOpenSections,
    toggleSection,
  };
}

'use client';

import { useState, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";
import PreviewPane from "@/components/PreviewPane";

export default function Home() {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [currentFormId, setCurrentFormId] = useState<string | null>(null);
  
  // NEW: Real-time preview refresh counter
  const [previewRefreshKey, setPreviewRefreshKey] = useState(0);

  // Collapse states
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  useEffect(() => {
    if (!activeThreadId) {
      setCurrentFormId(null);
      return;
    }

    async function fetchThreadDetails() {
      try {
        const res = await fetch(`http://localhost:8000/api/threads`, { credentials: 'include' });
        if (res.ok) {
          const threads = await res.json();
          const current = threads.find((t: any) => t.thread_id === activeThreadId);
          if (current && current.google_form_id) {
            setCurrentFormId(current.google_form_id);
          } else {
            setCurrentFormId(null);
          }
        }
      } catch (err) {
        console.error("Failed to load thread details", err);
      }
    }
    fetchThreadDetails();
  }, [activeThreadId]);

  const handleThreadCreated = (newThreadId: string, formId?: string) => {
    setActiveThreadId(newThreadId);
    setRefreshTrigger(prev => prev + 1);
    if (formId) setCurrentFormId(formId);
  };

  const handleFormUpdated = () => {
    setPreviewRefreshKey(prev => prev + 1); // Increments key, forcing iframe to reload live data
  };

  return (
    <main className="flex h-full w-full overflow-hidden m-0 p-0 bg-white">
      <Sidebar 
        activeThreadId={activeThreadId} 
        onSelectThread={setActiveThreadId} 
        refreshTrigger={refreshTrigger}
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
      />
      
      <ChatWindow 
        activeThreadId={activeThreadId} 
        onThreadCreated={handleThreadCreated}
        onFormIdUpdate={setCurrentFormId}
        onFormUpdated={handleFormUpdated}
      />

      <PreviewPane 
        formId={currentFormId}
        isOpen={isPreviewOpen}
        onToggle={() => setIsPreviewOpen(!isPreviewOpen)}
        refreshKey={previewRefreshKey}
      />
    </main>
  );
}
'use client';

import { useState, useEffect } from 'react';

interface Thread {
  id: string;
  thread_id: string;
  title: string;
  updated_at: string;
}

interface SidebarProps {
  activeThreadId: string | null;
  onSelectThread: (threadId: string | null) => void;
  refreshTrigger: number;
  isOpen: boolean;
  onToggle: () => void;
}

export default function Sidebar({ activeThreadId, onSelectThread, refreshTrigger, isOpen, onToggle }: SidebarProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);

  // 1. Safely grab the backend URL
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  useEffect(() => {
    async function fetchThreads() {
      try {
        // 2. Inject the variable with backticks and ${}
        const response = await fetch(`${backendUrl}/api/threads`, {
          credentials: 'include'
        });
        if (response.ok) {
          const data = await response.json();
          // Group the threads by their unique thread_id, keeping only the most recent one
          const uniqueThreadsMap = new Map();
          
          data.forEach((thread: Thread) => {
            const existing = uniqueThreadsMap.get(thread.thread_id);
            // If it doesn't exist yet, OR if this new duplicate has a newer timestamp, keep it!
            if (!existing || new Date(thread.updated_at) > new Date(existing.updated_at)) {
              uniqueThreadsMap.set(thread.thread_id, thread);
            }
          });

          // Convert the Map back to an array and sort them so the newest chats stay at the top
          const uniqueThreads = Array.from(uniqueThreadsMap.values()).sort((a, b) => 
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
          );
          setThreads(uniqueThreads);
        }
      } catch (error) {
        console.error("Failed to fetch threads:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchThreads();
  }, [refreshTrigger, backendUrl]); // Added backendUrl to dependencies

  const handleDelete = async (threadIdToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this chat?")) return;

    try {
      // 3. Inject the variable with backticks and ${}
      const response = await fetch(`${backendUrl}/api/threads/${threadIdToDelete}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      
      if (response.ok) {
        setThreads(prev => prev.filter(t => t.thread_id !== threadIdToDelete));
        if (activeThreadId === threadIdToDelete) {
          onSelectThread(null);
        }
      }
    } catch (error) {
      console.error("Failed to delete thread:", error);
    }
  };

  return (
    <div className={`h-full bg-[#102C57] text-[#FEFAF6] flex flex-col border-r border-[#102C57] transition-all duration-300 relative shrink-0 ${
      isOpen ? 'w-64 p-3' : 'w-12 p-0'
    }`}>
      {/* Toggle Arrow Button */}
      <button 
        onClick={onToggle}
        className="absolute -right-3.5 top-5 bg-[#EADBC8] text-[#102C57] w-7 h-7 rounded-full flex items-center justify-center shadow-md z-20 text-xs font-bold transition-colors select-none focus:outline-none"
        title={isOpen ? "Collapse Sidebar" : "Expand Sidebar"}
      >
        {isOpen ? '❮' : '❯'}
      </button>

      {isOpen ? (
        <>
          <div 
            onClick={() => onSelectThread(null)}
            className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#102C57] hover:bg-[#FEFAF6] text-[#FEFAF6] hover:text-[#102C57] cursor-pointer transition-colors text-xs font-semibold shadow-xs shrink-0"
            title="Start a new chat"
          >
            <span>New chat</span>
            <span className="text-base font-bold">+</span>
          </div>
          
          <div className="mt-12 max-h-[55%] flex flex-col justify-start overflow-y-auto space-y-1">
            {loading ? (
              <p className="text-[#FEFAF6] opacity-70 text-xs px-2">Loading...</p>
            ) : threads.length === 0 ? (
              <p className="text-[#FEFAF6] opacity-70 text-xs px-2">No recent forms.</p>
            ) : (
              threads.map((thread) => (
                <div 
                  key={thread.id} 
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer select-none group ${
                    activeThreadId === thread.thread_id 
                      ? 'bg-[#EADBC8] text-[#102C57]' 
                      : 'bg-transparent hover:bg-[#4B5694] text-[#FEFAF6]'
                  }`}
                  onClick={() => onSelectThread(thread.thread_id)}
                >
                  <span className="truncate text-xs flex-1 pr-2">
                    {thread.title}
                  </span>
                  
                  <button
                    onClick={(e) => handleDelete(thread.thread_id, e)}
                    className="text-[#102C57] opacity-0 group-hover:opacity-100 hover:text-red-500 transition-opacity p-0.5"
                    title="Delete Chat"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        /* NEW: Clickable vertical label when collapsed */
        <div 
          onClick={onToggle}
          className="w-full h-full flex flex-col items-center justify-start p-6 cursor-pointer group hover:bg-[#4B5694]/20 transition-colors"
          title="Expand Sidebar"
        >
          <div className="flex-1 flex items-center justify-center cursor-pointer select-none" onClick={onToggle}>
          <span className="text-xs font-semibold text-[#FEFAF6] tracking-widest uppercase [writing-mode:vertical-lr] rotate-180">
            CHATS
          </span>
        </div>
        </div>
      )}
    </div>
  );
}
'use client';

import { useState, useEffect, useRef } from 'react';

// --- Typewriter / Streaming Text Component ---
function AnimatedText({ text, animate }: { text: string; animate: boolean }) {
  const [displayed, setDisplayed] = useState(animate ? '' : text);

  useEffect(() => {
    if (!animate) {
      setDisplayed(text);
      return;
    }
    
    let i = 0;
    setDisplayed(''); // Start empty for the animation
    
    const interval = setInterval(() => {
      setDisplayed(text.slice(0, i + 1));
      i++;
      if (i >= text.length) {
        clearInterval(interval);
      }
    }, 15); // 15ms per character gives that fast, smooth reveal
    
    return () => clearInterval(interval);
  }, [text, animate]);

  return <>{displayed}</>;
}

// --- UPDATED INTERFACE ---
interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  isTyping?: boolean; // Flag to trigger the typewriter only on new final messages
}

interface ChatWindowProps {
  activeThreadId: string | null;
  onThreadCreated: (newThreadId: string, formId: string) => void;
  onFormIdUpdate?: (formId: string) => void;
  onFormUpdated?: () => void;
}

export default function ChatWindow({ activeThreadId, onThreadCreated, onFormIdUpdate, onFormUpdated }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null); // Ref to target the actual text input

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!activeThreadId) {
      setMessages([]);
      return;
    }

    async function fetchHistory() {
      try {
        const response = await fetch(`process.env.NEXT_PUBLIC_API_URL/api/threads/${activeThreadId}/messages`, {
          credentials: 'include'
        });
        if (response.ok) {
          const data = await response.json();
          // Historical messages load instantly without typewriter effect
          setMessages(data.map((msg: any) => ({ ...msg, isTyping: false })));
        }
      } catch (error) {
        console.error("Failed to load history", error);
      }
    }
    fetchHistory();
  }, [activeThreadId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() && !selectedFile) return;

    setIsProcessing(true);
    let documentContext = "";

    // 1. Define backendUrl at the very top of the function
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    if (selectedFile) {
      const formData = new FormData();
      formData.append('file', selectedFile);
      try {
        // 2. Inject the variable with backticks and ${}
        const uploadRes = await fetch(`${backendUrl}/api/upload`, {
          method: 'POST',
          body: formData,
          credentials: 'include'
        });
        if (uploadRes.ok) {
          const uploadData = await uploadRes.json();
          documentContext = uploadData.extracted_text;
        }
      } catch (err) {
        console.error("File upload failed", err);
      }
    }

    const basePrompt = inputValue;
    let displayPrompt = basePrompt;
    if (documentContext) {
      displayPrompt = basePrompt ? `${basePrompt}\n\n[📎 Document Attached]` : "[📎 Document Attached]";
    }
    let agent_prompt = documentContext ? `Source Document Context:\n{document_context}\n\nUser Request: {base_prompt}`.replace('{document_context}', documentContext).replace('{base_prompt}', basePrompt) : basePrompt;

    const tempUserId = Date.now().toString();
    setMessages(prev => [...prev, { id: tempUserId, role: 'user', content: displayPrompt }]);
    setInputValue('');
    setSelectedFile(null);

    // 3. Keep your awesome WebSocket dynamic logic!
    const wsProtocol = backendUrl.startsWith('https') ? 'wss://' : 'ws://';
    const wsHost = backendUrl.replace('https://', '').replace('http://', '');

    const ws = new WebSocket(`${wsProtocol}${wsHost}/ws/generate-form`);

    const tempAiId = (Date.now() + 1).toString();
    
    // UPDATED: Softer initial loading state
    setMessages(prev => [...prev, { id: tempAiId, role: 'ai', content: '⚡ Thinking...' }]);

    ws.onopen = () => {
      ws.send(JSON.stringify({ 
        prompt: agent_prompt, 
        thread_id: activeThreadId,
        document_context: documentContext
      }));
    };

    // THIS LIVES SAFELY INSIDE handleSubmit (OUTSIDE OF RENDER/MAP LOOPS)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.thread_id && !activeThreadId) {
        onThreadCreated(data.thread_id, data.form_id);
      }

      if (data.status === 'complete' || data.form_id || data.status === 'info') {
        setIsProcessing(false);
        
        if (data.form_id && onFormIdUpdate) {
          onFormIdUpdate(data.form_id);
        }
        if (onFormUpdated) {
          onFormUpdated();
        }
      }

      setMessages(prev => 
        prev.map(msg => {
          if (msg.id === tempAiId) {
            // 1. Handle our new graceful Info/Guardrail messages (Triggers Typewriter)
            if (data.status === 'info') {
              return { ...msg, content: data.message, isTyping: true };
            }
            
            // 2. Handle actual system crashes (No Typewriter)
            if (data.status === 'error' || data.error) {
              return { ...msg, content: `❌ Error: ${data.error || data.status}`, isTyping: false };
            }
            
            // 3. Handle successful form generation (Triggers Typewriter for text portion)
            if (data.status === 'complete' || data.form_id) {
              const richContent = JSON.stringify({
                text: `✅ ${data.title || 'Form Ready'}`,
                form_id: data.form_id
              });
              return { ...msg, content: richContent, isTyping: true };
            }
            
            // 4. Handle streaming status updates (No Typewriter, snaps in)
            return { ...msg, content: `⚡ ${data.status || data.message || 'Processing...'}`, isTyping: false };
          }
          return msg;
        })
      );
    };

    ws.onerror = () => {
      setIsProcessing(false);
      setMessages(prev => prev.map(msg => msg.id === tempAiId ? { ...msg, content: '❌ WebSocket Connection Error' } : msg));
    };
  };

  const renderInputForm = (isCentered: boolean = false) => (
    <div className={`w-full max-w-3xl mx-auto px-4 ${isCentered ? '' : 'py-0'}`}>
      <form 
        onSubmit={handleSubmit} 
        onClick={() => inputRef.current?.focus()}
        className="flex flex-col rounded-3xl bg-[#102C57] border border-[#c4a991] shadow-sm focus-within:border-[#FEFAF6] focus-within:ring-1 focus-within:ring-[#FEFAF6] transition-all p-2.5 cursor-text"
      >
        {selectedFile && (
          <div className="flex items-center gap-2 mb-2 bg-[#4B5694] text-[#FEFAF6] px-3 py-1.5 rounded-lg text-xs font-medium w-max border border-[#c4a991] select-none">
            📄 {selectedFile.name}
            <button 
              type="button" 
              onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }} 
              className="text-[#FEFAF6] font-bold ml-1"
            >
              ✕
            </button>
          </div>
        )}

        <div className="flex items-center gap-3">
          <label className="cursor-pointer text-[#FEFAF6] opacity-70 hover:opacity-100 transition-colors p-1" onClick={(e) => e.stopPropagation()}>
            <input 
              type="file" 
              className="hidden" 
              accept=".pdf,.txt"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
            />
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path>
            </svg>
          </label>

          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask AgenticForms to build a form..."
            className="flex-1 bg-transparent outline-none text-[#FEFAF6] placeholder-[#FEFAF6]/60 text-sm md:text-base py-1"
            disabled={isProcessing}
          />
          
          <button 
            type="submit" 
            disabled={isProcessing || (!inputValue.trim() && !selectedFile)}
            onClick={(e) => e.stopPropagation()}
            className="bg-[#FEFAF6] hover:bg-[#102C57] text-[#102C57] hover:text-[#FEFAF6] p-2.5 rounded-xl font-medium disabled:opacity-80 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center justify-center cursor-pointer"
          >
            <svg className="w-4 h-4 rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19V5m0 0l-7 7m7-7l7 7" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  );

  return (
    <div className="flex-1 h-full w-full bg-[#FEFAF6] relative overflow-hidden">
      {messages.length === 0 ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-[#FEFAF6] select-none">
          <div className="space-y-2 mb-8">
            <h1 className="text-4xl font-semibold tracking-tight text-[#102C57]">
              What should we focus on?
            </h1>
            <p className="text-[#4B5694] opacity-70 text-sm">
              Generate intelligent Google Forms or quizzes instantly using AI.
            </p>
          </div>
          {renderInputForm(true)}
        </div>
      ) : (
        <div className="absolute inset-0 flex flex-col bg-[#FEFAF6] overflow-hidden">
          <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6 bg-[#FEFAF6]">
            <div className="max-w-3xl mx-auto w-full space-y-6">
              {messages.map((msg) => {
                let displayText = msg.content;
                let formId = null;
                
                if (msg.role === 'ai') {
                  try {
                    const parsed = JSON.parse(msg.content);
                    if (parsed.text && parsed.form_id) {
                      displayText = parsed.text;
                      formId = parsed.form_id;
                    }
                  } catch (e) {}
                }

                return (
                  <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] p-4 rounded-2xl shadow-sm text-sm leading-relaxed bg-[#102C57] text-[#FEFAF6] border border-[#c4a991] ${
                      msg.role === 'user' ? 'rounded-br-xs' : 'rounded-bl-xs'
                    }`}>
                      <div className="whitespace-pre-wrap font-medium select-text cursor-text">
                        {/* MAGIC REVEAL: Typewriter animation on AI text */}
                        {msg.role === 'ai' ? (
                          <AnimatedText text={displayText} animate={!!msg.isTyping} />
                        ) : (
                          displayText
                        )}
                      </div>
                      
                      {formId && (
                        <div className="mt-4 flex flex-row gap-2 border-t border-gray-200 pt-3 select-none">
                          <a 
                            href={`https://docs.google.com/forms/d/${formId}/edit`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-1 flex items-center justify-center gap-2 bg-[#FEFAF6] hover:bg-blue-50 text-blue-700 font-semibold py-2 px-3 rounded-xl transition-colors border border-blue-200 shadow-xs text-xs sm:text-sm"
                          >
                            ✏️ Edit Form (Admin)
                          </a>
                          <a 
                            href={`https://docs.google.com/forms/d/${formId}/viewform`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-1 flex items-center justify-center gap-2 bg-[#FEFAF6] hover:bg-green-50 text-green-700 font-semibold py-2 px-3 rounded-xl transition-colors border border-green-200 shadow-xs text-xs sm:text-sm"
                          >
                            👁️ View Live Form
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Sits completely flush at the absolute bottom floor */}
          <div className="bg-[#FEFAF6] pb-3 pt-1 shrink-0 border-t border-[#c4a991]/40">
            {renderInputForm(false)}
          </div>
        </div>
      )}
    </div>
  );
}
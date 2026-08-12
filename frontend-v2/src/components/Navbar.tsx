'use client';

import { useState, useEffect } from 'react';

export default function Navbar() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function checkAuth() {
      try {
        // Crucial: 'include' tells the browser to send the secure session cookie!
        const response = await fetch('http://localhost:8000/auth/status', {
          credentials: 'include', 
        });
        
        if (response.ok) {
          const data = await response.json();
          setIsAuthenticated(data.authenticated);
        }
      } catch (error) {
        console.error("Auth check failed:", error);
      } finally {
        setLoading(false);
      }
    }
    checkAuth();
  }, []);

  return (
    <nav className="w-full bg-[#FEFAF6] border-b border-[#c4a991] px-6 py-3 flex justify-between items-center shadow-sm shrink-0">
      <div className="font-bold text-xl text-[#102C57]">
        AgenticForms <span className="text-[#102C57]">⚡</span>
      </div>
      
      <div className="flex items-center gap-4">
        {loading ? (
          <span className="text-sm text-[#FEFAF6] opacity-80">Checking session...</span>
        ) : isAuthenticated ? (
          <>
            <span className="bg-[#DAC0A3] text-[#FEFAF6] text-xs font-bold px-3 py-1 rounded-full">
              Connected to Google
            </span>
            <a 
              href="http://localhost:8000/auth/logout" 
              className="bg-[#102C57] hover:bg-[#65082b] text-[#FEFAF6] text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              Logout
            </a>
          </>
        ) : (
          <>
            <span className="bg-[#102C57] text-[#FEFAF6] text-xs font-bold px-3 py-1 rounded-full">
              Not Authenticated
            </span>
            <a 
              href="http://localhost:8000/auth/login" 
              className="bg-[#102C57] hover:bg-[#3d1212] text-[#FEFAF6] text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              Login with Google
            </a>
          </>
        )}
      </div>
    </nav>
  );
}
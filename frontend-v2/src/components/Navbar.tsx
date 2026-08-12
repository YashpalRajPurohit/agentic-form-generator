'use client';

import { useState, useEffect } from 'react';

export default function Navbar() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  // Safely grab the backend URL
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  useEffect(() => {
    async function checkAuth() {
      try {
        // Crucial: 'include' tells the browser to send the secure session cookie!
        const response = await fetch(`${backendUrl}/auth/status`, {
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
  }, [backendUrl]);

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
            {/* Inject the variable using curly braces and backticks */}
            <a 
              href={`${backendUrl}/auth/logout`} 
              className="bg-[#102C57] hover:bg-[#4B5694] text-[#FEFAF6] text-sm font-semibold px-4 py-2 rounded-full transition-colors"
            >
              Logout
            </a>
          </>
        ) : (
          <>
            <span className="bg-[#FF8A8A] text-[#FEFAF6] text-xs font-bold px-3 py-1 rounded-full">
              Not Authenticated
            </span>
            {/* Inject the variable using curly braces and backticks */}
            <a 
              href={`${backendUrl}/auth/login`} 
              className="bg-[#102C57] hover:bg-[#4B5694] text-[#FEFAF6] text-sm font-semibold px-4 py-2 rounded-full transition-colors"
            >
              Login with Google
            </a>
          </>
        )}
      </div>
    </nav>
  );
}
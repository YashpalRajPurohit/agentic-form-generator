'use client';

interface PreviewPaneProps {
  formId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  refreshKey: number;
}

export default function PreviewPane({ formId, isOpen, onToggle, refreshKey }: PreviewPaneProps) {
  return (
    <div className={`h-full bg-[#F1E2D1] border-l border-[#c4a991] flex flex-col transition-all duration-300 relative shrink-0 ${
      isOpen ? 'w-[450px]' : 'w-12'
    }`}>
      {/* Toggle Button */}
      <button 
        onClick={onToggle}
        className="absolute -left-3.5 top-5 bg-[#102C57] text-[#F1E2D1] hover:bg-[#102C57] w-7 h-7 rounded-full flex items-center justify-center shadow-md z-20 text-xs font-bold transition-colors"
        title={isOpen ? "Collapse Preview" : "Expand Preview"}
      >
        {isOpen ? '❯' : '❮'}
      </button>

      {isOpen ? (
        <div className="flex flex-col h-full w-full">
          {/* Header */}
          <div className="px-4 py-3 bg-[#DCC3AA] border-b border-[#c4a991] flex justify-between items-center shrink-0">
            <span className="text-xs font-bold tracking-wider text-[#102C57] uppercase">Live Form Preview</span>
            {formId && (
              <a 
                href={`https://docs.google.com/forms/d/${formId}/viewform`} 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-xs text-[#102C57] hover:underline font-semibold"
              >
                Open in Tab ↗
              </a>
            )}
          </div>

          {/* Iframe Body */}
          <div className="flex-1 bg-white relative">
            {formId ? (
              <iframe 
                key={`${formId}-${refreshKey}`} // Forces iframe to reload whenever refreshKey increments!
                src={`https://docs.google.com/forms/d/${formId}/viewform?embedded=true`}
                className="w-full h-full border-0"
                title="Google Form Preview"
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full p-6 text-center text-[#102C57]/60 select-none">
                <span className="text-3xl mb-2">📋</span>
                <p className="text-xs font-medium">No form generated yet. Send a prompt to preview your live form here!</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center cursor-pointer select-none" onClick={onToggle}>
          <span className="text-xs font-semibold text-[#102C57] tracking-widest uppercase [writing-mode:vertical-lr] rotate-180">
            Preview
          </span>
        </div>
      )}
    </div>
  );
}
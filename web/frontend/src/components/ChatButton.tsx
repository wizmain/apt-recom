interface ChatButtonProps {
  onClick: () => void;
  isOpen?: boolean;
}

export default function ChatButton({ onClick, isOpen }: ChatButtonProps) {
  return (
    <div className="fixed bottom-6 right-6 z-20 flex items-center gap-2">
      {/* 안내 문구 */}
      {!isOpen && (
        <div className="bg-white/95 backdrop-blur-sm text-gray-700 text-sm font-medium
                        px-3 py-2 rounded-full shadow-md border border-gray-200
                        animate-bounce-slow hidden sm:block">
          🐿 <span className="text-amber-600 font-bold">집토리</span>에게 물어보세요!
        </div>
      )}

      {/* 버튼 */}
      <button
        onClick={onClick}
        className={`w-14 h-14 rounded-full shadow-lg
                    hover:scale-105 active:scale-95 transition-all duration-200
                    flex items-center justify-center
                    ${isOpen
                      ? 'bg-gray-700 text-white ring-2 ring-gray-400'
                      : 'bg-amber-500 text-white hover:bg-amber-600'
                    }`}
        aria-label={isOpen ? '채팅 닫기' : '집토리 열기'}
      >
        {isOpen ? (
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        ) : (
          <span className="text-2xl">🐿</span>
        )}
      </button>
    </div>
  );
}

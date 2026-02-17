"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import VoiceOrb from "../components/VoiceOrb";
import { useVoice } from "../hooks/useVoice";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatState {
  conversationId: string | null;
  facts: Record<string, string>;
  missingFields: string[];
  confidence: number | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatState, setChatState] = useState<ChatState>({
    conversationId: null,
    facts: {},
    missingFields: [],
    confidence: null,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingTranscriptRef = useRef<string>("");

  const handleTranscript = useCallback((text: string, isFinal: boolean) => {
    pendingTranscriptRef.current = text;
    setInput(text);

    if (isFinal && text.trim()) {
      // Auto-send on final transcript
      handleVoiceSend(text);
    }
  }, []);

  const {
    isListening,
    isSpeaking,
    isSupported,
    audioLevel,
    startListening,
    stopListening,
    speak,
    cancelSpeech,
  } = useVoice({
    onTranscript: handleTranscript,
    onError: (error) => {
      console.error("Voice error:", error);
      setIsVoiceMode(false);
    },
    continuous: false,
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Initial greeting
  useEffect(() => {
    setMessages([
      {
        id: "greeting",
        role: "assistant",
        content: `👋 Hi! I'm Owly, your mortgage eligibility assistant.

I'll help you find eligible lender programs based on your scenario. Just describe your loan scenario, and I'll guide you through the process.

**What I need to know:**
- Property location (state)
- Loan purpose (purchase, refi, cash-out)
- Occupancy type
- Property type
- Loan amount & LTV
- Borrower's FICO score
- Income documentation type

Go ahead and share your scenario!`,
      },
    ]);
  }, []);

  const sendMessageToAPI = async (messageText: string, speakResponse: boolean = false) => {
    if (!messageText.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setIsProcessing(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: messageText,
          conversation_id: chatState.conversationId,
        }),
      });

      if (!response.ok) throw new Error("Chat request failed");

      const data = await response.json();

      const assistantMessage: Message = {
        id: Date.now().toString() + "-assistant",
        role: "assistant",
        content: data.message,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setChatState({
        conversationId: data.conversation_id,
        facts: data.facts,
        missingFields: data.missing_fields,
        confidence: data.confidence,
      });

      // Speak the response if in voice mode
      if (speakResponse && isVoiceMode) {
        setIsProcessing(false);
        // Strip markdown for cleaner speech
        const cleanText = data.message
          .replace(/\*\*/g, "")
          .replace(/\*/g, "")
          .replace(/#{1,6}\s/g, "")
          .replace(/\n/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        
        await speak(cleanText);
        
        // Auto-restart listening after speaking
        if (isVoiceMode) {
          setTimeout(() => {
            startListening();
          }, 500);
        }
      }
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString() + "-error",
          role: "assistant",
          content: "Sorry, I encountered an error. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
      setIsProcessing(false);
    }
  };

  const sendMessage = () => sendMessageToAPI(input, false);

  const handleVoiceSend = (text: string) => {
    pendingTranscriptRef.current = "";
    sendMessageToAPI(text, true);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleFeedback = async (messageId: string, thumbs: "up" | "down") => {
    console.log("Feedback:", messageId, thumbs);
  };

  const activateVoiceMode = () => {
    setIsVoiceMode(true);
    startListening();
  };

  const deactivateVoiceMode = () => {
    setIsVoiceMode(false);
    stopListening();
    cancelSpeech();
    setInput("");
    pendingTranscriptRef.current = "";
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar - Facts Panel */}
      <aside className="w-80 bg-white border-r p-4 hidden lg:block overflow-y-auto">
        <div className="mb-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl">🦉</span>
            <span className="text-xl font-bold text-blue-600">Owly</span>
          </Link>
        </div>

        <div className="mb-6">
          <h3 className="font-semibold text-gray-700 mb-2">Scenario Facts</h3>
          <div className="space-y-2 text-sm">
            {Object.entries(chatState.facts).length > 0 ? (
              Object.entries(chatState.facts).map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-gray-500 capitalize">
                    {key.replace(/_/g, " ")}:
                  </span>
                  <span className="font-medium">{value}</span>
                </div>
              ))
            ) : (
              <p className="text-gray-400 italic">No facts collected yet</p>
            )}
          </div>
        </div>

        {chatState.missingFields.length > 0 && (
          <div className="mb-6">
            <h3 className="font-semibold text-gray-700 mb-2">Missing Fields</h3>
            <div className="space-y-1">
              {chatState.missingFields.map((field) => (
                <div
                  key={field}
                  className="text-sm text-orange-600 flex items-center gap-1"
                >
                  <span>⚠️</span>
                  <span className="capitalize">{field.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {chatState.confidence !== null && (
          <div className="mb-6">
            <h3 className="font-semibold text-gray-700 mb-2">Confidence</h3>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    chatState.confidence >= 85
                      ? "bg-green-500"
                      : chatState.confidence >= 70
                      ? "bg-yellow-500"
                      : "bg-red-500"
                  }`}
                  style={{ width: `${chatState.confidence}%` }}
                />
              </div>
              <span className="text-sm font-medium">{chatState.confidence}%</span>
            </div>
          </div>
        )}

        <div className="mt-auto pt-4 border-t">
          <Link
            href="/admin"
            className="text-sm text-gray-500 hover:text-blue-600"
          >
            Admin Dashboard →
          </Link>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 lg:hidden">
            <span className="text-xl">🦉</span>
            <span className="font-bold text-blue-600">Owly</span>
          </Link>

          {/* Voice mode indicator */}
          {isVoiceMode && (
            <div className="flex items-center gap-2 text-sm text-purple-600">
              <span className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" />
              Voice Mode Active
            </div>
          )}

          {/* Voice support badge */}
          {!isVoiceMode && isSupported && (
            <button
              onClick={activateVoiceMode}
              className="text-sm text-gray-500 hover:text-purple-600 flex items-center gap-1 transition"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                />
              </svg>
              Try Voice
            </button>
          )}
        </header>

        {/* Voice Mode Overlay */}
        {isVoiceMode && (
          <div className="absolute inset-0 z-50 bg-gradient-to-b from-gray-900/95 to-gray-800/95 flex flex-col items-center justify-center backdrop-blur-sm">
            {/* Close button */}
            <button
              onClick={deactivateVoiceMode}
              className="absolute top-4 right-4 text-white/60 hover:text-white transition p-2"
              aria-label="Close voice mode"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>

            {/* Logo */}
            <div className="absolute top-8 flex items-center gap-2">
              <span className="text-3xl">🦉</span>
              <span className="text-2xl font-bold text-white">Owly</span>
            </div>

            {/* Voice Orb */}
            <VoiceOrb
              isListening={isListening}
              isSpeaking={isSpeaking}
              isProcessing={isProcessing}
              audioLevel={audioLevel}
              onActivate={startListening}
              onDeactivate={stopListening}
            />

            {/* Transcript display */}
            {input && (
              <div className="mt-8 max-w-md text-center">
                <p className="text-white/80 text-lg">{input}</p>
              </div>
            )}

            {/* Last assistant message */}
            {messages.length > 0 && messages[messages.length - 1].role === "assistant" && (
              <div className="absolute bottom-8 left-8 right-8 max-h-32 overflow-y-auto">
                <p className="text-white/60 text-sm text-center line-clamp-3">
                  {messages[messages.length - 1].content
                    .replace(/\*\*/g, "")
                    .replace(/\*/g, "")
                    .replace(/#{1,6}\s/g, "")
                    .substring(0, 200)}
                  {messages[messages.length - 1].content.length > 200 && "..."}
                </p>
              </div>
            )}

            {/* Keyboard shortcut hint */}
            <div className="absolute bottom-4 text-white/30 text-xs">
              Press Escape to exit voice mode
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  message.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-white border shadow-sm"
                }`}
              >
                {message.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p>{message.content}</p>
                )}

                {/* Feedback buttons for assistant messages */}
                {message.role === "assistant" && message.id !== "greeting" && (
                  <div className="flex gap-2 mt-2 pt-2 border-t border-gray-100">
                    <button
                      onClick={() => handleFeedback(message.id, "up")}
                      className="text-gray-400 hover:text-green-500 transition"
                      title="Helpful"
                    >
                      👍
                    </button>
                    <button
                      onClick={() => handleFeedback(message.id, "down")}
                      className="text-gray-400 hover:text-red-500 transition"
                      title="Not helpful"
                    >
                      👎
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && !isVoiceMode && (
            <div className="flex justify-start">
              <div className="bg-white border shadow-sm rounded-lg px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <span
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: "0.1s" }}
                  />
                  <span
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: "0.2s" }}
                  />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t bg-white p-4">
          <div className="max-w-4xl mx-auto flex gap-2">
            {/* Voice button */}
            {isSupported && (
              <button
                onClick={activateVoiceMode}
                className="p-2 text-gray-500 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition"
                title="Start voice mode"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                  />
                </svg>
              </button>
            )}

            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Describe your loan scenario..."
              className="flex-1 resize-none border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={1}
              disabled={isLoading}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Send
            </button>
          </div>
        </div>
      </main>

      {/* Keyboard listener for voice mode */}
      <VoiceModeKeyboardHandler
        isActive={isVoiceMode}
        onEscape={deactivateVoiceMode}
      />
    </div>
  );
}

// Keyboard handler component
function VoiceModeKeyboardHandler({
  isActive,
  onEscape,
}: {
  isActive: boolean;
  onEscape: () => void;
}) {
  useEffect(() => {
    if (!isActive) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onEscape();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isActive, onEscape]);

  return null;
}

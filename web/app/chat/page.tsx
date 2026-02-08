"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";

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
  const [chatState, setChatState] = useState<ChatState>({
    conversationId: null,
    facts: {},
    missingFields: [],
    confidence: null,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
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
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleFeedback = async (messageId: string, thumbs: "up" | "down") => {
    // TODO: Implement feedback API call
    console.log("Feedback:", messageId, thumbs);
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
        <header className="bg-white border-b px-4 py-3 flex items-center justify-between lg:hidden">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl">🦉</span>
            <span className="font-bold text-blue-600">Owly</span>
          </Link>
        </header>

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

          {isLoading && (
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
    </div>
  );
}

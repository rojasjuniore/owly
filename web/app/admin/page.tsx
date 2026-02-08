"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Stats {
  total_conversations: number;
  total_messages: number;
  total_documents: number;
  total_rules: number;
  thumbs_up: number;
  thumbs_down: number;
  feedback_rate: number;
}

interface Document {
  id: string;
  filename: string;
  lender: string | null;
  program: string | null;
  archetype: string | null;
  status: string;
  chunks_count: number;
  rules_count: number;
  created_at: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "documents" | "rules">(
    "overview"
  );
  const [uploadingFile, setUploadingFile] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [statsRes, docsRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/stats`),
        fetch(`${API_URL}/api/admin/documents`),
      ]);

      if (statsRes.ok) {
        setStats(await statsRes.json());
      }
      if (docsRes.ok) {
        setDocuments(await docsRes.json());
      }
    } catch (error) {
      console.error("Failed to fetch admin data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingFile(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_URL}/api/admin/documents`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        await fetchData();
      } else {
        const error = await response.json();
        alert(error.detail || "Upload failed");
      }
    } catch (error) {
      console.error("Upload error:", error);
      alert("Upload failed");
    } finally {
      setUploadingFile(false);
      e.target.value = "";
    }
  };

  const handleDeleteDocument = async (id: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      const response = await fetch(`${API_URL}/api/admin/documents/${id}`, {
        method: "DELETE",
      });

      if (response.ok) {
        await fetchData();
      }
    } catch (error) {
      console.error("Delete error:", error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl">🦉</span>
              <span className="text-xl font-bold text-blue-600">Owly</span>
            </Link>
            <span className="text-gray-300">|</span>
            <span className="text-gray-600">Admin Dashboard</span>
          </div>
          <Link
            href="/chat"
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            ← Back to Chat
          </Link>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {/* Tabs */}
        <div className="flex gap-4 mb-8 border-b">
          {["overview", "documents", "rules"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as typeof activeTab)}
              className={`px-4 py-2 font-medium capitalize border-b-2 -mb-px transition ${
                activeTab === tab
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="text-center py-12 text-gray-500">Loading...</div>
        ) : (
          <>
            {/* Overview Tab */}
            {activeTab === "overview" && stats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  label="Conversations"
                  value={stats.total_conversations}
                  icon="💬"
                />
                <StatCard
                  label="Messages"
                  value={stats.total_messages}
                  icon="📝"
                />
                <StatCard
                  label="Documents"
                  value={stats.total_documents}
                  icon="📄"
                />
                <StatCard label="Rules" value={stats.total_rules} icon="📋" />
                <StatCard label="Thumbs Up" value={stats.thumbs_up} icon="👍" />
                <StatCard
                  label="Thumbs Down"
                  value={stats.thumbs_down}
                  icon="👎"
                />
                <StatCard
                  label="Satisfaction"
                  value={`${stats.feedback_rate}%`}
                  icon="📊"
                  className="col-span-2"
                />
              </div>
            )}

            {/* Documents Tab */}
            {activeTab === "documents" && (
              <div>
                {/* Upload Button */}
                <div className="mb-6">
                  <label className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-700 cursor-pointer transition">
                    {uploadingFile ? (
                      "Uploading..."
                    ) : (
                      <>
                        <span>📤</span> Upload PDF
                      </>
                    )}
                    <input
                      type="file"
                      accept=".pdf"
                      onChange={handleFileUpload}
                      disabled={uploadingFile}
                      className="hidden"
                    />
                  </label>
                </div>

                {/* Documents Table */}
                <div className="bg-white rounded-lg border overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Filename
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Lender
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Type
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Status
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Chunks
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                          Rules
                        </th>
                        <th className="px-4 py-3 text-right text-sm font-medium text-gray-600">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {documents.length === 0 ? (
                        <tr>
                          <td
                            colSpan={7}
                            className="px-4 py-8 text-center text-gray-500"
                          >
                            No documents uploaded yet
                          </td>
                        </tr>
                      ) : (
                        documents.map((doc) => (
                          <tr key={doc.id} className="hover:bg-gray-50">
                            <td className="px-4 py-3 text-sm font-medium">
                              {doc.filename}
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">
                              {doc.lender || "-"}
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">
                              {doc.archetype || "-"}
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                  doc.status === "active"
                                    ? "bg-green-100 text-green-700"
                                    : doc.status === "draft"
                                    ? "bg-yellow-100 text-yellow-700"
                                    : "bg-gray-100 text-gray-600"
                                }`}
                              >
                                {doc.status}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">
                              {doc.chunks_count}
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-600">
                              {doc.rules_count}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                onClick={() => handleDeleteDocument(doc.id)}
                                className="text-red-500 hover:text-red-700 text-sm"
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Rules Tab */}
            {activeTab === "rules" && (
              <div className="bg-white rounded-lg border p-8 text-center text-gray-500">
                <p>Rules management coming soon</p>
                <p className="text-sm mt-2">
                  Upload documents to auto-extract eligibility rules
                </p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  className = "",
}: {
  label: string;
  value: number | string;
  icon: string;
  className?: string;
}) {
  return (
    <div className={`bg-white rounded-lg border p-4 ${className}`}>
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-gray-500">{label}</p>
        </div>
      </div>
    </div>
  );
}

"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Mic, MicOff, Send, Volume2, VolumeX, X } from "lucide-react";
import { usePathname } from "next/navigation";

type QuantyMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type SpeechRecognitionEventLike = Event & {
  results: SpeechRecognitionResultList;
};

type SpeechRecognitionErrorLike = Event & {
  error?: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const starterMessage: QuantyMessage = {
  id: "welcome",
  role: "assistant",
  content: "Hi, I am Quanty. Ask me about the dashboard, portfolio, market moves, or say your question aloud."
};

function createId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cleanTranscript(results: SpeechRecognitionResultList) {
  return Array.from(results)
    .map((result) => result[0]?.transcript || "")
    .join(" ")
    .trim();
}

export function QuantyAssistant() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<QuantyMessage[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const transcriptSupported = useMemo(() => {
    if (typeof window === "undefined") return false;
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy, open]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      audioRef.current?.pause();
      if (audioRef.current?.src) URL.revokeObjectURL(audioRef.current.src);
    };
  }, []);

  async function speak(text: string) {
    if (!voiceEnabled || !text.trim()) return;

    try {
      const response = await fetch("/api/quanty/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });

      if (!response.ok) throw new Error("Voice output is not configured yet.");

      const blob = await response.blob();
      if (!blob.size) throw new Error("Voice output returned no audio.");

      audioRef.current?.pause();
      if (audioRef.current?.src) URL.revokeObjectURL(audioRef.current.src);

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      await audio.play();
    } catch {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
        return;
      }

      setNotice("Voice output needs smallest.ai keys on the server.");
    }
  }

  async function askQuanty(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;

    setNotice(null);
    setInput("");
    setBusy(true);

    const nextMessages: QuantyMessage[] = [...messages, { id: createId(), role: "user", content: trimmed }];
    setMessages(nextMessages);

    try {
      const response = await fetch("/api/quanty/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content }) => ({ role, content })),
          page: pathname
        })
      });

      const payload = (await response.json()) as { answer?: string; error?: string };
      if (!response.ok) throw new Error(payload.error || "Quanty could not answer right now.");

      const answer = payload.answer || "I could not form an answer for that yet.";
      setMessages((current) => [...current, { id: createId(), role: "assistant", content: answer }]);
      speak(answer);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Quanty is temporarily unavailable.");
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    askQuanty(input);
  }

  function toggleListening() {
    if (!transcriptSupported) {
      setNotice("Voice input is not supported by this browser.");
      return;
    }

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return;

    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      const transcript = cleanTranscript(event.results);
      setInput(transcript);
    };
    recognition.onerror = () => {
      setNotice("I could not hear that clearly. Please try again.");
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      setInput((current) => {
        if (current.trim()) askQuanty(current);
        return current;
      });
    };

    recognitionRef.current = recognition;
    setNotice(null);
    setListening(true);
    recognition.start();
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-3 sm:bottom-5 sm:right-5">
      {open && (
        <section className="w-[calc(100vw-2rem)] max-w-[390px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl">
          <header className="flex items-center justify-between border-b border-slate-200 bg-slate-950 px-4 py-3 text-white">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded bg-emerald-400 text-slate-950">
                <Bot className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold">Quanty</h2>
                <p className="truncate text-xs text-slate-300">Agentic AI voice chat</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="grid h-8 w-8 place-items-center rounded text-slate-300 hover:bg-white/10 hover:text-white"
              aria-label="Close Quanty"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="h-[380px] overflow-y-auto bg-slate-50 px-4 py-4">
            <div className="space-y-3">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[86%] rounded-lg px-3 py-2 text-sm leading-6 ${
                      message.role === "user"
                        ? "bg-slate-900 text-white"
                        : "border border-slate-200 bg-white text-slate-700"
                    }`}
                  >
                    {message.content}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="flex justify-start">
                  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-500">
                    Quanty is thinking...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {notice && <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800">{notice}</div>}

          <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white p-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={toggleListening}
                className={`grid h-10 w-10 shrink-0 place-items-center rounded border ${
                  listening
                    ? "border-red-200 bg-red-50 text-red-600"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
                aria-label={listening ? "Stop voice input" : "Start voice input"}
                title={listening ? "Stop voice input" : "Start voice input"}
              >
                {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={listening ? "Listening..." : "Ask Quanty"}
                className="h-10 min-w-0 flex-1 rounded border border-slate-200 px-3 text-sm text-slate-800 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
              />
              <button
                type="button"
                onClick={() => setVoiceEnabled((current) => !current)}
                className="grid h-10 w-10 shrink-0 place-items-center rounded border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                aria-label={voiceEnabled ? "Mute Quanty voice" : "Enable Quanty voice"}
                title={voiceEnabled ? "Mute Quanty voice" : "Enable Quanty voice"}
              >
                {voiceEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </button>
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="grid h-10 w-10 shrink-0 place-items-center rounded bg-emerald-500 text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Send message"
                title="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </form>
        </section>
      )}

      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="group relative grid h-14 w-14 place-items-center rounded-full bg-slate-950 text-white shadow-xl ring-1 ring-slate-900/10 transition hover:-translate-y-0.5 hover:bg-emerald-600"
        aria-label="Open Quanty voice chat"
      >
        <Bot className="h-6 w-6" />
        <span className="pointer-events-none absolute bottom-full right-0 mb-2 hidden w-max rounded bg-slate-950 px-3 py-2 text-xs font-semibold text-white shadow-lg group-hover:block">
          Quanty voice chat agent
        </span>
      </button>
    </div>
  );
}

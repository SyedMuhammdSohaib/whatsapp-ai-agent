"use client";

import { useState, useRef, useEffect } from "react";

const API = "http://127.0.0.1:8000";

export default function Home() {
  const [messages, setMessages] = useState([
    { role: "agent", text: "Assalam-o-alaikum! Main aapka WhatsApp AI agent hoon. Likho ya mic se bolo." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakOn, setSpeakOn] = useState(true);
  const [lang, setLang] = useState("en-US");
  const endRef = useRef(null);
  const recRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Realistic voice: backend /tts se mp3 le ke bajao
  async function speak(text) {
    if (!speakOn) return;
    try {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      const res = await fetch(`${API}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.play();
    } catch (e) {}
  }

  async function sendText(text) {
    const msg = (text ?? "").trim();
    if (!msg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, thread_id: "web-session" }),
      });
      const data = await res.json();
      setMessages((m) => [...m, { role: "agent", text: data.reply }]);
      speak(data.reply);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "agent", text: "⚠️ Backend se connect nahi ho paya. Check karo uvicorn chal raha hai (port 8000)." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function startListening() {
    const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
    if (!SR) {
      alert("Voice is browser me support nahi karta. Chrome use karo.");
      return;
    }
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = new SR();
    rec.lang = lang;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const t = e.results[0][0].transcript;
      setInput(t);
      setTimeout(() => sendText(t), 150);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  }

  return (
    <div className="app">
      <div className="blob blob1" />
      <div className="blob blob2" />
      <div className="blob blob3" />
      <div className="blob blob4" />

      <div className="chat">
        <header className="head">
          <div className="dot" />
          <div className="title">
            <h1>WhatsApp AI Agent</h1>
            <p>LangGraph · Groq · Voice</p>
          </div>
          <div className="controls">
            <select value={lang} onChange={(e) => setLang(e.target.value)} title="Mic language">
              <option value="en-US">EN</option>
              <option value="ur-PK">اردو</option>
            </select>
            <button
              className={`icon ${speakOn ? "on" : ""}`}
              onClick={() => { setSpeakOn(!speakOn); if (speakOn && audioRef.current) audioRef.current.pause(); }}
              title="Speaker on/off"
            >
              {speakOn ? "🔊" : "🔇"}
            </button>
          </div>
        </header>

        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`row ${m.role}`}>
              <div className={`bubble ${m.role}`}>{m.text}</div>
            </div>
          ))}
          {loading && (
            <div className="row agent">
              <div className="bubble agent typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="inputbar">
          <button className={`mic ${listening ? "listening" : ""}`} onClick={startListening} title="Bol ke message do">🎤</button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendText(input)}
            placeholder={listening ? "Sun raha hoon..." : "Message likho ya mic dabao..."}
          />
          <button className="send" onClick={() => sendText(input)} disabled={loading}>
            {loading ? "..." : "Send"}
          </button>
        </div>
      </div>

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .app {
          min-height: 100vh; width: 100%; display: flex; align-items: center; justify-content: center;
          padding: 16px; background: #0b0f1a; overflow: hidden; position: relative;
          font-family: system-ui, -apple-system, sans-serif;
        }
        .blob { position: fixed; border-radius: 50%; filter: blur(70px); opacity: 0.55; z-index: 0; }
        .blob1 { width: 420px; height: 420px; background: #7c3aed; top: -80px; left: -60px; animation: float1 14s ease-in-out infinite; }
        .blob2 { width: 380px; height: 380px; background: #ec4899; bottom: -90px; right: -70px; animation: float2 16s ease-in-out infinite; }
        .blob3 { width: 340px; height: 340px; background: #06b6d4; bottom: 40px; left: -80px; animation: float3 18s ease-in-out infinite; }
        .blob4 { width: 300px; height: 300px; background: #f59e0b; top: -40px; right: -40px; animation: float1 20s ease-in-out infinite; }
        @keyframes float1 { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(60px,80px) scale(1.15);} }
        @keyframes float2 { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(-70px,-50px) scale(1.1);} }
        @keyframes float3 { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(50px,-60px) scale(1.2);} }

        .chat {
          position: relative; z-index: 1; width: 100%; max-width: 460px; height: 85vh; max-height: 720px;
          display: flex; flex-direction: column; background: rgba(255,255,255,0.08);
          backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255,255,255,0.15); border-radius: 24px;
          box-shadow: 0 20px 60px rgba(0,0,0,0.4); overflow: hidden;
        }
        .head { display: flex; align-items: center; gap: 12px; padding: 16px 18px;
          background: rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.1); }
        .dot { width: 12px; height: 12px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 12px #22c55e; flex-shrink: 0; }
        .title { flex: 1; }
        .title h1 { color: #fff; font-size: 16px; font-weight: 700; }
        .title p { color: rgba(255,255,255,0.6); font-size: 11px; margin-top: 2px; }
        .controls { display: flex; align-items: center; gap: 8px; }
        .controls select { background: rgba(0,0,0,0.3); color: #fff; border: 1px solid rgba(255,255,255,0.15);
          border-radius: 10px; padding: 6px 8px; font-size: 13px; cursor: pointer; }
        .icon { background: rgba(255,255,255,0.1); border: none; border-radius: 10px; padding: 6px 9px; font-size: 15px; cursor: pointer; }
        .icon.on { background: rgba(124,58,237,0.5); }

        .messages { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
        .row { display: flex; }
        .row.user { justify-content: flex-end; }
        .row.agent { justify-content: flex-start; }
        .bubble { max-width: 80%; padding: 11px 15px; border-radius: 18px; font-size: 14.5px;
          line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
        .bubble.user { background: linear-gradient(135deg, #7c3aed, #ec4899); color: #fff; border-bottom-right-radius: 4px; }
        .bubble.agent { background: rgba(255,255,255,0.14); color: #f1f1f1; border-bottom-left-radius: 4px; }
        .typing { display: flex; gap: 5px; align-items: center; }
        .typing span { width: 7px; height: 7px; border-radius: 50%; background: rgba(255,255,255,0.7); animation: blink 1.2s infinite; }
        .typing span:nth-child(2){ animation-delay: .2s; }
        .typing span:nth-child(3){ animation-delay: .4s; }
        @keyframes blink { 0%,60%,100%{opacity:.3;} 30%{opacity:1;} }

        .inputbar { display: flex; gap: 8px; padding: 14px; align-items: center;
          background: rgba(255,255,255,0.06); border-top: 1px solid rgba(255,255,255,0.1); }
        .inputbar input { flex: 1; padding: 12px 16px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.15);
          background: rgba(0,0,0,0.25); color: #fff; font-size: 14.5px; outline: none; min-width: 0; }
        .inputbar input::placeholder { color: rgba(255,255,255,0.4); }
        .mic { flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; border: none;
          background: rgba(255,255,255,0.12); font-size: 18px; cursor: pointer; transition: transform .15s; }
        .mic:hover { transform: scale(1.08); }
        .mic.listening { background: #ef4444; animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.6);} 50%{box-shadow:0 0 0 10px rgba(239,68,68,0);} }
        .send { flex-shrink: 0; padding: 12px 20px; border-radius: 14px; border: none;
          background: linear-gradient(135deg, #7c3aed, #ec4899); color: #fff; font-weight: 600;
          font-size: 14.5px; cursor: pointer; transition: transform .15s, opacity .15s; }
        .send:hover { transform: scale(1.05); }
        .send:disabled { opacity: .5; cursor: default; transform: none; }

        @media (max-width: 520px) {
          .app { padding: 0; }
          .chat { height: 100vh; max-height: none; max-width: 100%; border-radius: 0; border: none; }
        }
      `}</style>
    </div>
  );
}

"use client";

import { useState, useRef, useEffect } from "react";

const API = "http://127.0.0.1:8000";
const SILENCE_MS = 4000; // itni der chup rehne par message chala jaye
const NO_SPEECH_MS = 10000; // kuch bola hi nahi to mic band
const SPEAKING_VOLUME = 20; // agent bol raha ho to video ki awaaz halki
const REMINDER_CHECK_MS = 20000;
const STATUS_CHECK_MS = 10000;
const SUGGESTIONS = [
  "Aaj ka briefing do",
  "Aaj kis kis ke message aaye?",
  "YouTube par koi naat chalao",
  "2 minute baad chai ka yaad dilana",
];

// Model **bold** likhta hai, baqi text waisa hi
function formatted(text) {
  return String(text).split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : part));
}

let youtubeApi;
function loadYouTubeApi() {
  youtubeApi ??= new Promise((resolve) => {
    window.onYouTubeIframeAPIReady = () => resolve(window.YT);
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.body.appendChild(script);
  });
  return youtubeApi;
}

export default function Home() {
  const [messages, setMessages] = useState([
    { role: "agent", text: "Assalam-o-alaikum! Main Jarvis hoon. Likho ya mic se bolo." },
  ]);
  const [online, setOnline] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakOn, setSpeakOn] = useState(true);
  const [lang, setLang] = useState("en-US");
  const endRef = useRef(null);
  const recRef = useRef(null);
  const audioRef = useRef(null);
  const [videoOn, setVideoOn] = useState(false);
  const playerRef = useRef(null);
  const videoRef = useRef(null);
  const queueRef = useRef([]);
  const speakRef = useRef(null);
  const shownRemindersRef = useRef(new Set());
  const briefingShownRef = useRef(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    async function checkReminders() {
      try {
        const res = await fetch(`${API}/reminders`);
        const due = (await res.json()).filter((r) => !shownRemindersRef.current.has(r.id));
        if (!due.length) return;
        due.forEach((r) => shownRemindersRef.current.add(r.id));
        setMessages((m) => [...m, ...due.map((r) => ({ role: "agent", text: r.text }))]);
        speakRef.current(due.map((r) => r.text).join("\n"));
        await fetch(`${API}/reminders/shown`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: due.map((r) => r.id) }),
        });
      } catch (e) {} // backend band hai to agle chakkar me
    }
    checkReminders();
    const timer = setInterval(checkReminders, REMINDER_CHECK_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    async function checkStatus() {
      try {
        const res = await fetch(API);
        setOnline((await res.json()).agent === "ready");
      } catch (e) {
        setOnline(false);
      }
    }
    checkStatus();
    const timer = setInterval(checkStatus, STATUS_CHECK_MS);
    return () => clearInterval(timer);
  }, []);

  // Din ka pehla app kholne par
  useEffect(() => {
    async function showBriefing() {
      try {
        const res = await fetch(`${API}/briefing`);
        const { text } = await res.json();
        if (!text || briefingShownRef.current) return;
        briefingShownRef.current = true;
        setMessages((m) => [...m, { role: "agent", text }]);
        speakRef.current(text);
        await fetch(`${API}/briefing/shown`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ shown: true }),
        });
      } catch (e) {}
    }
    showBriefing();
  }, []);

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
        body: JSON.stringify({ text: text.replaceAll("**", "") }),
      });
      if (!res.ok || res.status === 204) return;
      const blob = await res.blob();
      if (!blob.size) return; // khaali audio play karne par NotSupportedError aata hai
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      await audio.play(); // await taake play ka error neeche catch ho jaye
      const player = playerRef.current;
      if (player?.getVolume) {
        const volume = player.getVolume();
        player.setVolume(Math.min(volume, SPEAKING_VOLUME));
        audio.onended = audio.onpause = () => player.setVolume(volume);
      }
    } catch (e) {}
  }
  speakRef.current = speak; // timer ko speaker on/off ki taaza halat mile

  // Kuch videos embed nahi hoti, un par player error deta hai to agli chalao
  async function playNext() {
    const next = queueRef.current.shift();
    if (!next) {
      videoRef.current = null;
      setVideoOn(false);
      setMessages((m) => [...m, { role: "agent", text: "⚠️ Ye video yahan nahi chal saki. Koi aur try karo." }]);
      return;
    }
    videoRef.current = next;
    setVideoOn(true);
    const YT = await loadYouTubeApi();
    if (playerRef.current) {
      playerRef.current.loadVideoById(next.id);
      return;
    }
    playerRef.current = new YT.Player("yt-player", {
      videoId: next.id,
      playerVars: { autoplay: 1, playsinline: 1 },
      events: {
        onReady: (e) => e.target.playVideo(),
        onError: () => playNext(),
      },
    });
  }

  function runYoutube({ action, videos, seconds }) {
    if (action === "play") {
      queueRef.current = [...videos];
      playNext();
      return;
    }
    const player = playerRef.current;
    if (!player?.getCurrentTime) return;
    const now = player.getCurrentTime();
    if (action === "pause") player.pauseVideo();
    if (action === "resume") player.playVideo();
    if (action === "forward") player.seekTo(now + seconds, true);
    if (action === "backward") player.seekTo(Math.max(0, now - seconds), true);
    if (action === "seek_to") player.seekTo(seconds, true);
    if (action === "stop") {
      player.stopVideo();
      videoRef.current = null;
      setVideoOn(false);
    }
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
        body: JSON.stringify({
          message: msg,
          thread_id: "web-session",
          video_id: videoRef.current?.id ?? "",
          video_title: videoRef.current?.title ?? "",
          video_time: playerRef.current?.getCurrentTime?.() ?? 0,
        }),
      });
      const data = await res.json();
      setMessages((m) => [...m, { role: "agent", text: data.reply }]);
      data.youtube?.forEach(runYoutube);
      if (!data.youtube?.length) speak(data.reply); // gaane ke upar "chala di" na bole
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
    rec.continuous = true; // chhoti pause par band na ho
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let finalText = "";
    let interim = "";
    let done = false;
    let timer;
    const finish = () => {
      done = true;
      clearTimeout(timer);
      rec.stop();
    };
    const waitFor = (ms) => {
      clearTimeout(timer);
      timer = setTimeout(finish, ms);
    };

    rec.onresult = (e) => {
      interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript.trim();
        if (e.results[i].isFinal) finalText += t + " ";
        else interim += t + " ";
      }
      setInput((finalText + interim).trim());
      waitFor(SILENCE_MS);
    };
    rec.onend = () => {
      // Chrome khud bhi session band kar deta hai, user bol raha ho to dobara shuru karo
      if (!done) {
        rec.start();
        return;
      }
      setListening(false);
      playerRef.current?.unMute?.();
      const text = (finalText + interim).trim();
      if (text) sendText(text);
    };
    rec.onerror = (e) => {
      if (e.error !== "no-speech") {
        done = true;
        clearTimeout(timer);
      }
    };
    recRef.current = { stop: finish };
    setListening(true);
    playerRef.current?.mute?.(); // warna mic gaane ko bhi sun leta hai aur chup hona pata nahi chalta
    waitFor(NO_SPEECH_MS);
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
          <div className={`dot ${online ? "" : "off"}`} title={online ? "Backend chal raha hai" : "Backend se connection nahi"} />
          <div className="title">
            <h1>Jarvis</h1>
            <p>{online ? "WhatsApp · YouTube · Reminders · Voice" : "Backend se connection nahi"}</p>
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

        <div className={`player ${videoOn ? "" : "off"}`}>
          <div id="yt-player" />
        </div>

        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`row ${m.role}`}>
              <div className={`bubble ${m.role}`} dir="auto">{formatted(m.text)}</div>
            </div>
          ))}
          {!messages.some((m) => m.role === "user") && (
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => sendText(s)}>{s}</button>
              ))}
            </div>
          )}
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
          position: relative; z-index: 1; width: 100%; max-width: 520px; height: 85vh; max-height: 720px;
          display: flex; flex-direction: column; background: rgba(255,255,255,0.08);
          backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255,255,255,0.15); border-radius: 24px;
          box-shadow: 0 20px 60px rgba(0,0,0,0.4); overflow: hidden;
        }
        .head { display: flex; align-items: center; gap: 12px; padding: 16px 18px;
          background: rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.1); }
        .dot { width: 12px; height: 12px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 12px #22c55e; flex-shrink: 0; }
        .dot.off { background: #ef4444; box-shadow: 0 0 12px #ef4444; }
        .title { flex: 1; }
        .title h1 { color: #fff; font-size: 16px; font-weight: 700; }
        .title p { color: rgba(255,255,255,0.6); font-size: 11px; margin-top: 2px; }
        .controls { display: flex; align-items: center; gap: 8px; }
        .controls select { background: rgba(0,0,0,0.3); color: #fff; border: 1px solid rgba(255,255,255,0.15);
          border-radius: 10px; padding: 6px 8px; font-size: 13px; cursor: pointer; }
        .icon { background: rgba(255,255,255,0.1); border: none; border-radius: 10px; padding: 6px 9px; font-size: 15px; cursor: pointer; }
        .icon.on { background: rgba(124,58,237,0.5); }

        .player { flex-shrink: 0; aspect-ratio: 16 / 9; background: #000; }
        .player.off { display: none; }
        .player iframe { display: block; width: 100%; height: 100%; border: 0; }
        .messages { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
        .row { display: flex; }
        .row.user { justify-content: flex-end; }
        .row.agent { justify-content: flex-start; }
        .bubble { max-width: 80%; padding: 11px 15px; border-radius: 18px; font-size: 14.5px;
          line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
        .bubble.user { background: linear-gradient(135deg, #7c3aed, #ec4899); color: #fff; border-bottom-right-radius: 4px; }
        .bubble.agent { background: rgba(255,255,255,0.14); color: #f1f1f1; border-bottom-left-radius: 4px; }
        .suggestions { display: flex; flex-wrap: wrap; gap: 8px; }
        .suggestions button { padding: 8px 13px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.2);
          background: rgba(255,255,255,0.06); color: #f1f1f1; font-size: 13px; cursor: pointer; }
        .suggestions button:hover { background: rgba(124,58,237,0.4); }
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

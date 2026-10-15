// ============================================================
// UNICO punto da modificare quando cambiano gli indirizzi o i contratti
// dei tre componenti (BE, CHAT, VOICE). Il resto del sito non li cita.
// ============================================================
// Di default si usa lo stesso computer da cui si apre il sito (window.location.hostname),
// quindi in LAN basta aprire http://<IP>:8080. Per puntare a un'altra macchina
// scrivere qui l'indirizzo completo, es. "http://192.168.1.10:8000".
const host = window.location.hostname || "localhost";

window.CONFIG = {
  // --- BE (membro 1): menu, orari, informazioni ---
  be: {
    baseUrl: `http://${host}:8000`,
    menuPath: "/api/menu",   // GET -> [{category, name, description, price, allergens, is_vegetarian, is_vegan, is_gluten_free}]
    infoPath: "/api/info",   // GET -> {chiave: valore} (name, address, phone, email, opening_hours, parking, services, payment_methods)
    healthPath: "/api/health",
  },

  // --- CHAT (membro 2): servizio chat/api.py ---
  chat: {
    baseUrl: `http://${host}:8002`,
    sessionPath: "/chat/session",  // POST -> {session_id, reply, phase}
    messagePath: "/chat/message",  // POST {session_id, text} -> {reply, phase}
    timeoutMs: 120000,             // l'LLM locale può essere lento
  },

  // --- VOICE (membro 3): WebSocket di voice/ ---
  voice: {
    wsUrl: `ws://${host}:8003/ws/voice`,
    inputSampleRate: 16000,        // PCM16 mono inviato al server (deve coincidere con SAMPLE_RATE del voice)
    outputSampleRate: 22050,       // PCM16 mono ricevuto (TTS_SAMPLE_RATE del voice; se il server lo comunica nell'evento "ready" vale quello)
    frameMs: 20,
  },

  // Testi mostrati se il BE non risponde (il sito resta presentabile).
  fallbackInfo: {
    name: "Trattoria Bella Napoli",
    address: "Via Toledo 142, 80134 Napoli (NA)",
    phone: "+39 081 555 1234",
    email: "prenotazioni@trattoriabellanapoli.it",
    opening_hours: "Aperto dal Martedì alla Domenica. Pranzo 12:00 - 15:00, cena 19:30 - 23:30. Lunedì chiuso.",
    parking: "Convenzione con il Garage Toledo, a 50 metri dal locale.",
    services: "Aria condizionata, terrazza e giardino, WiFi gratuito, accesso per disabili, seggioloni. Animali ammessi.",
    payment_methods: "Contanti, carte, Bancomat, Apple Pay e Satispay.",
  },
};

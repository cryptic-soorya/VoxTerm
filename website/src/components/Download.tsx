import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Download as DownloadIcon } from 'lucide-react'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

const TABS = [
  {
    id: 'ollama',
    label: 'Option A — Offline with Ollama',
    note: 'Fully offline. Your commands never leave your Mac. Install Ollama from ollama.com first (free, one click).',
    link: 'https://ollama.com',
    code: [
      { type: 'comment', text: '# 1. Pull the model (~2 GB, one time)' },
      { type: 'cmd',     text: 'ollama pull llama3.2:3b' },
      { type: 'blank' },
      { type: 'comment', text: '# 2. Clone and install' },
      { type: 'cmd',     text: 'git clone https://github.com/yourusername/vocterm' },
      { type: 'cmd',     text: 'cd voxterm && brew install portaudio' },
      { type: 'cmd',     text: 'python3 -m venv venv && source venv/bin/activate' },
      { type: 'cmd',     text: 'pip install -r requirements.txt' },
      { type: 'blank' },
      { type: 'comment', text: '# 3. Run' },
      { type: 'cmd',     text: 'cp .env.example .env && ollama serve &' },
      { type: 'cmd',     text: 'python main.py' },
    ],
    footer: 'Grant microphone access to Terminal when prompted — one-time setup.',
  },
  {
    id: 'gemini',
    label: 'Option B — Free cloud with Gemini',
    note: 'No Ollama needed. Google Gemini 1.5 Flash free tier: 1500 requests/day, no credit card.',
    link: 'https://aistudio.google.com',
    code: [
      { type: 'comment', text: '# 1. Get a free key at aistudio.google.com' },
      { type: 'blank' },
      { type: 'comment', text: '# 2. Clone and install' },
      { type: 'cmd',     text: 'git clone https://github.com/yourusername/vocterm' },
      { type: 'cmd',     text: 'cd voxterm && brew install portaudio' },
      { type: 'cmd',     text: 'python3 -m venv venv && source venv/bin/activate' },
      { type: 'cmd',     text: 'pip install -r requirements.txt' },
      { type: 'blank' },
      { type: 'comment', text: '# 3. Add key and run' },
      { type: 'cmd',     text: 'cp .env.example .env' },
      { type: 'comment', text: '# edit .env → GEMINI_API_KEY=your_key' },
      { type: 'cmd',     text: 'python main.py' },
    ],
    footer: 'VoxTerm auto-detects the key. Switch between Ollama and Gemini any time.',
  },
]

export default function Download() {
  const [active, setActive] = useState('ollama')
  const tab = TABS.find(t => t.id === active)!

  return (
    <section id="download" className="py-32 px-6 text-center" style={{ background: 'linear-gradient(180deg, #07070f 0%, #0b0918 100%)' }}>
      <div className="max-w-[1040px] mx-auto">

        <motion.div variants={stagger(0.08)} initial="hidden" whileInView="visible" viewport={viewportOnce} className="mb-14">
          <motion.span variants={fadeUp} className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4">
            Download
          </motion.span>
          <motion.h2 variants={fadeUp} className="text-[clamp(36px,5vw,58px)] font-black tracking-[-2px] leading-[1.1] mb-5">
            Free. Forever.<br />No account needed.
          </motion.h2>
          <motion.p variants={fadeUp} className="text-[17px] text-muted max-w-[440px] mx-auto">
            Open source, MIT licence. Use it, modify it, ship it.
          </motion.p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={viewportOnce}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-[660px] mx-auto rounded-2xl overflow-hidden border border-white/[0.06]"
          style={{ background: 'rgba(18,18,31,0.9)' }}
        >
          {/* Top */}
          <div className="px-10 pt-10 pb-8 text-center">
            <motion.div
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-emerald/25 bg-emerald/8 text-emerald text-[11px] font-bold mb-6"
              animate={{ borderColor: ['rgba(52,211,153,0.25)', 'rgba(52,211,153,0.5)', 'rgba(52,211,153,0.25)'] }}
              transition={{ duration: 2.5, repeat: Infinity }}
            >
              <motion.span
                className="w-1.5 h-1.5 rounded-full bg-emerald"
                animate={{ scale: [1, 1.3, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
              Open source · MIT licence
            </motion.div>

            <h3 className="text-[32px] font-black tracking-[-1.5px] mb-3">VoxTerm for Mac</h3>
            <p className="text-[14px] text-muted mb-7">macOS 12+ · Apple Silicon &amp; Intel · Python 3.11+</p>

            <motion.a
              href="https://github.com/yourusername/vocterm/releases/latest"
              className="inline-flex items-center gap-2.5 px-8 py-3.5 bg-accent text-white text-[15px] font-bold rounded-xl mb-3"
              whileHover={{ scale: 1.04, backgroundColor: '#9d5cff', boxShadow: '0 12px 48px rgba(124,58,237,0.45)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 400, damping: 22 }}
            >
              <DownloadIcon size={16} />
              Download VoxTerm
            </motion.a>
            <p className="text-[12px] text-muted">v1.0.0 · Requires Ollama or free Gemini key</p>
          </div>

          {/* Tabs */}
          <div className="flex border-t border-white/[0.05]">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setActive(t.id)}
                className="flex-1 py-4 text-[12.5px] font-semibold transition-colors relative"
                style={{ color: active === t.id ? '#a78bfa' : '#6b6b8a' }}
              >
                {t.label}
                {active === t.id && (
                  <motion.div
                    layoutId="tab-indicator"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent-mid"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="px-10 py-8 text-left"
            >
              <p className="text-[13.5px] text-muted mb-5 leading-relaxed">{tab.note}</p>

              <div className="rounded-xl border border-white/[0.05] bg-surface p-5 font-mono text-[12.5px] leading-[1.85] mb-4 overflow-x-auto">
                {tab.code.map((line, i) => (
                  <div key={i}>
                    {line.type === 'blank'   && <br />}
                    {line.type === 'comment' && <span className="text-muted2">{line.text}</span>}
                    {line.type === 'cmd'     && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.04 }}
                        className="text-cyan"
                      >
                        {line.text}
                      </motion.div>
                    )}
                  </div>
                ))}
              </div>

              <p className="text-[12.5px] text-muted">{tab.footer}</p>
            </motion.div>
          </AnimatePresence>
        </motion.div>
      </div>
    </section>
  )
}

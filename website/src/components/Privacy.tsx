import { motion } from 'framer-motion'
import { Shield, Cpu, Database, WifiOff } from 'lucide-react'
import { fadeUp, slideLeft, slideRight, stagger, viewportOnce } from '../lib/animations'

const LOCAL = [
  { label: 'Voice → Whisper',    badge: 'local' },
  { label: 'Text → Ollama LLM',  badge: 'local' },
  { label: 'Command → Safety gate', badge: 'local' },
  { label: 'History → SQLite',   badge: 'local' },
]
const NEVER = [
  { label: 'Cloud transcription' },
  { label: 'Remote LLM API'      },
  { label: 'Telemetry or analytics' },
]

const POINTS = [
  { icon: <WifiOff size={18} />, title: 'No cloud transcription',   desc: 'faster-whisper runs the full Whisper model on your CPU. Your voice never hits a server.' },
  { icon: <Cpu size={18} />,     title: 'No cloud LLM',             desc: 'Ollama runs llama3.2 locally. Command translation happens in RAM, not on someone else\'s GPU.' },
  { icon: <Database size={18} />,title: 'No telemetry, ever',       desc: 'There is no analytics, crash reporting, or usage tracking. Open source — verify it yourself.' },
  { icon: <Shield size={18} />,  title: 'Gemini is opt-in only',    desc: 'The free Gemini fallback only activates if you set a key. Offline mode is the default.' },
]

export default function Privacy() {
  return (
    <section id="privacy" className="py-32 px-6" style={{ background: 'linear-gradient(135deg, #07071a, #0d0820)' }}>
      <div className="max-w-[1040px] mx-auto">

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-20 items-center">

          {/* Left */}
          <motion.div variants={stagger(0.1)} initial="hidden" whileInView="visible" viewport={viewportOnce}>
            <motion.span variants={fadeUp} className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4">
              Privacy
            </motion.span>
            <motion.h2 variants={fadeUp} className="text-[clamp(34px,4.5vw,52px)] font-black tracking-[-2px] leading-[1.1] mb-5">
              Nothing leaves<br />your machine.
            </motion.h2>
            <motion.p variants={fadeUp} className="text-[17px] text-muted leading-relaxed mb-10">
              Your terminal commands reveal your project structure, file names, credential paths, and work habits.
              That's not data we want — or anyone should have.
            </motion.p>

            <div className="flex flex-col gap-7">
              {POINTS.map((p, i) => (
                <motion.div
                  key={i}
                  variants={fadeUp}
                  custom={i}
                  className="flex gap-4"
                  whileHover={{ x: 4 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="w-8 h-8 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center text-accent-mid flex-shrink-0 mt-0.5">
                    {p.icon}
                  </div>
                  <div>
                    <div className="text-[15px] font-bold mb-1">{p.title}</div>
                    <div className="text-[13.5px] text-muted leading-relaxed">{p.desc}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Right — flow diagram */}
          <motion.div
            variants={slideRight}
            initial="hidden"
            whileInView="visible"
            viewport={viewportOnce}
            className="relative rounded-2xl border border-white/[0.06] p-8 overflow-hidden"
            style={{ background: 'rgba(18,18,31,0.8)' }}
          >
            {/* Corner glow */}
            <div className="absolute -top-16 -right-16 w-48 h-48 bg-gradient-radial from-accent/15 to-transparent pointer-events-none" />

            <div className="flex flex-col gap-3">
              {LOCAL.map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={viewportOnce}
                  transition={{ delay: i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  whileHover={{ borderColor: 'rgba(52,211,153,0.4)', x: 2 }}
                  className="flex items-center gap-3 px-4 py-3.5 rounded-xl border border-white/[0.06] bg-white/[0.02] transition-colors"
                >
                  <motion.div
                    className="w-2 h-2 rounded-full bg-emerald flex-shrink-0"
                    animate={{ boxShadow: ['0 0 0px #34d399', '0 0 8px #34d399', '0 0 0px #34d399'] }}
                    transition={{ duration: 2, repeat: Infinity, delay: i * 0.5 }}
                  />
                  <span className="text-[13px] font-medium flex-1">{item.label}</span>
                  <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-emerald/15 text-emerald">local</span>
                </motion.div>
              ))}

              <div className="border-t border-white/[0.04] my-1" />

              {NEVER.map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={viewportOnce}
                  transition={{ delay: 0.4 + i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className="flex items-center gap-3 px-4 py-3.5 rounded-xl border border-white/[0.04] bg-white/[0.01]"
                >
                  <div className="w-2 h-2 rounded-full bg-rose/60 flex-shrink-0" />
                  <span className="text-[13px] text-muted flex-1">{item.label}</span>
                  <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-rose/10 text-rose">never</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}

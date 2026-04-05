import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'
import { MouseEvent } from 'react'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

const FEATURES = [
  { icon: '⚡', title: 'Instant offline',       desc: 'Ollama + llama3.2 runs entirely on your Mac. No internet, no API, no latency from the wire. Works on a plane.' },
  { icon: '🔒', title: 'Private by design',     desc: 'Whisper transcribes locally. The LLM runs locally. Your commands never leave your machine — not even as metadata.' },
  { icon: '🛡️', title: 'Three-tier safety gate', desc: 'Low runs instantly. Medium asks Y/n. High requires typing "yes" in full. Hardcoded rules the LLM can never override.' },
  { icon: '↩️', title: 'One-word undo',          desc: 'Say "undo that." The inverse command is computed before anything runs, so reversing is always one confirmation away.' },
  { icon: '📚', title: 'Command history',        desc: 'Every run is logged locally to SQLite with its risk level and output. Yours to keep, searchable, never uploaded.' },
  { icon: '🔌', title: 'Plugins + aliases',      desc: 'Drop a .py file into plugins/ for zero-latency shortcuts. Aliases let you save any command — vocterm learns your patterns.' },
]

function FeatureCard({ icon, title, desc, delay }: { icon: string; title: string; desc: string; delay: number }) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const rotateX = useSpring(useTransform(y, [-60, 60], [6, -6]), { stiffness: 300, damping: 30 })
  const rotateY = useSpring(useTransform(x, [-60, 60], [-6, 6]), { stiffness: 300, damping: 30 })

  function onMouseMove(e: MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    x.set(e.clientX - rect.left - rect.width / 2)
    y.set(e.clientY - rect.top - rect.height / 2)
  }
  function onMouseLeave() { x.set(0); y.set(0) }

  return (
    <motion.div
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={viewportOnce}
      transition={{ delay, duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
      style={{ rotateX, rotateY, transformPerspective: 800, transformStyle: 'preserve-3d' }}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      whileHover={{ backgroundColor: 'rgba(20,20,42,1)' }}
      className="bg-surface2 p-8 cursor-default transition-colors"
    >
      <motion.span
        className="text-[28px] block mb-5"
        whileHover={{ scale: 1.15, rotate: [-5, 5, 0] }}
        transition={{ duration: 0.35 }}
      >
        {icon}
      </motion.span>
      <h3 className="text-[17px] font-bold tracking-tight mb-2.5">{title}</h3>
      <p className="text-[13.5px] text-muted leading-relaxed">{desc}</p>
    </motion.div>
  )
}

export default function Features() {
  return (
    <section className="py-32 px-6 bg-surface">
      <div className="max-w-[1040px] mx-auto">

        <motion.div variants={stagger(0.08)} initial="hidden" whileInView="visible" viewport={viewportOnce} className="mb-16">
          <motion.span variants={fadeUp} className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4">
            Features
          </motion.span>
          <motion.h2 variants={fadeUp} className="text-[clamp(36px,5vw,58px)] font-black tracking-[-2px] leading-[1.1]">
            Built for the way<br />developers actually work.
          </motion.h2>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-[2px] rounded-2xl overflow-hidden border border-white/[0.05]">
          {FEATURES.map((f, i) => (
            <FeatureCard key={i} {...f} delay={i * 0.07} />
          ))}
        </div>
      </div>
    </section>
  )
}

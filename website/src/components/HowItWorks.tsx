import { motion } from 'framer-motion'
import { Mic, FileText, Brain, ShieldCheck, CheckCircle2, LucideIcon } from 'lucide-react'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

const STEPS: { icon: LucideIcon; label: string; desc: string }[] = [
  { icon: Mic,          label: 'Speak',      desc: 'Plain English' },
  { icon: FileText,     label: 'Transcribe', desc: 'Whisper on-device' },
  { icon: Brain,        label: 'Translate',  desc: 'Local LLM' },
  { icon: ShieldCheck,  label: 'Review',     desc: 'You approve it' },
  { icon: CheckCircle2, label: 'Run',        desc: 'In your shell' },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-32 px-6 text-center">
      <div className="max-w-[1040px] mx-auto">

        <motion.div variants={stagger(0.08)} initial="hidden" whileInView="visible" viewport={viewportOnce}>
          <motion.span variants={fadeUp} className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4">
            How it works
          </motion.span>
          <motion.h2 variants={fadeUp} className="text-[clamp(36px,5vw,58px)] font-black tracking-[-2px] leading-[1.1] mb-4">
            Five steps.<br />Under four seconds.
          </motion.h2>
          <motion.p variants={fadeUp} className="text-[17px] text-muted max-w-[460px] mx-auto mb-20">
            The whole pipeline runs locally. Nothing waits on a network.
          </motion.p>
        </motion.div>

        {/* Step cards */}
        <div className="flex items-center justify-center flex-wrap gap-0">
          {STEPS.map((step, i) => (
            <div key={i} className="flex items-center">
              <motion.div
                initial={{ opacity: 0, y: 28 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={viewportOnce}
                transition={{ delay: i * 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                whileHover={{ y: -8 }}
                className="flex flex-col items-center gap-3 w-36 cursor-default"
              >
                <motion.div
                  className="w-16 h-16 rounded-[18px] border border-white/[0.06] bg-surface2 flex items-center justify-center shadow-card"
                  whileHover={{
                    borderColor: 'rgba(255,77,46,0.5)',
                    backgroundColor: 'rgba(255,77,46,0.1)',
                    boxShadow: '0 8px 32px rgba(255,77,46,0.25)',
                  }}
                  transition={{ duration: 0.2 }}
                >
                  <step.icon size={24} strokeWidth={1.75} className="text-accent-mid" />
                </motion.div>
                <div>
                  <div className="text-[13px] font-semibold text-white">{step.label}</div>
                  <div className="text-[11px] text-muted mt-0.5">{step.desc}</div>
                </div>
              </motion.div>

              {/* Arrow connector */}
              {i < STEPS.length - 1 && (
                <motion.div
                  initial={{ opacity: 0, scaleX: 0 }}
                  whileInView={{ opacity: 1, scaleX: 1 }}
                  viewport={viewportOnce}
                  transition={{ delay: i * 0.1 + 0.3, duration: 0.4 }}
                  className="text-muted2 text-xl mx-1 mb-6 hidden sm:block origin-left"
                >
                  ›
                </motion.div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

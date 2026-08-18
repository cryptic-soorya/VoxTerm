import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

function StatCard({ value, label, delay }: { value: string; label: string; delay: number }) {
  return (
    <motion.div
      variants={fadeUp}
      custom={delay}
      className="flex flex-col items-center p-8 bg-surface2 border-r border-white/[0.04] last:border-0"
    >
      <motion.span
        className="text-[44px] font-black tracking-[-2px] text-white/90 leading-none mb-2"
        initial={{ opacity: 0, scale: 0.8 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={viewportOnce}
        transition={{ delay, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        {value}
      </motion.span>
      <span className="text-[13px] text-muted">{label}</span>
    </motion.div>
  )
}

export default function Problem() {
  const words1 = ['You', 'google', 'the', 'flag,']
  const words2 = ['you', 'mistype', 'the', 'path,']
  const words3 = ['or', 'you', 'just', 'speak', 'it.']

  return (
    <section className="relative py-32 px-6" style={{ background: 'linear-gradient(180deg, #060605 0%, #0d0c0b 50%, #060605 100%)' }}>
      <div className="max-w-[1040px] mx-auto text-center">

        <motion.div
          variants={stagger(0.08)}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
        >
          <motion.span variants={fadeUp}
            className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4"
          >
            The problem
          </motion.span>
          <motion.h2 variants={fadeUp}
            className="text-[clamp(36px,5vw,58px)] font-black tracking-[-2px] leading-[1.1] mb-5"
          >
            Typing is the bottleneck.
          </motion.h2>
          <motion.p variants={fadeUp}
            className="text-[18px] text-muted leading-relaxed max-w-[520px] mx-auto mb-16"
          >
            The terminal is the most powerful tool on your computer.
            But it speaks a language you're constantly looking up.
          </motion.p>
        </motion.div>

        {/* Animated quote */}
        <div className="text-[clamp(28px,4.5vw,52px)] font-black tracking-[-1.5px] leading-[1.25] max-w-[760px] mx-auto mb-16 text-left">
          {[words1, words2, words3].map((words, lineIdx) => (
            <div key={lineIdx} className="flex flex-wrap gap-x-3">
              {words.map((word, i) => {
                const isStrike  = (lineIdx === 0 && i === 1) || (lineIdx === 1 && i === 1)
                const isHighlight = lineIdx === 2
                return (
                  <motion.span
                    key={i}
                    className={isStrike ? 'line-through text-muted2' : isHighlight ? 'text-gradient' : 'text-white'}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={viewportOnce}
                    transition={{
                      delay: lineIdx * 0.25 + i * 0.07,
                      duration: 0.55,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                  >
                    {word}
                  </motion.span>
                )
              })}
            </div>
          ))}
        </div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={viewportOnce}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="grid grid-cols-3 max-w-[620px] mx-auto rounded-xl overflow-hidden border border-white/[0.05]"
        >
          <StatCard value="~4s"  label="from voice to execution" delay={0}    />
          <StatCard value="$0"   label="cost per query, forever"  delay={0.1}  />
          <StatCard value="100%" label="runs on your machine"     delay={0.2}  />
        </motion.div>
      </div>
    </section>
  )
}

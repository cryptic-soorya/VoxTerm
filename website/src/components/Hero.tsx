import { motion, useScroll, useTransform } from 'framer-motion'
import { Download, Github } from 'lucide-react'
import { useRef } from 'react'
import TerminalMockup from './TerminalMockup'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

export default function Hero() {
  const ref = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] })
  const y       = useTransform(scrollYProgress, [0, 1], [0, 80])
  const opacity = useTransform(scrollYProgress, [0, 0.6], [1, 0])

  return (
    <section ref={ref} className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 overflow-hidden">

      {/* Radial glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] bg-gradient-radial from-accent/15 to-transparent pointer-events-none" />

      {/* Grid lines */}
      <div className="absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage: 'linear-gradient(rgba(167,139,250,1) 1px, transparent 1px), linear-gradient(90deg, rgba(167,139,250,1) 1px, transparent 1px)',
          backgroundSize: '80px 80px',
        }}
      />

      <motion.div
        style={{ y, opacity }}
        variants={stagger(0.12, 0.05)}
        initial="hidden"
        animate="visible"
        className="flex flex-col items-center gap-0 z-10"
      >
        {/* Badge */}
        <motion.div variants={fadeUp}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-accent/30 bg-accent/10 text-accent-mid text-[11px] font-bold uppercase tracking-wider mb-8"
        >
          <motion.span
            className="w-1.5 h-1.5 rounded-full bg-accent-mid"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          macOS · Apple Silicon · 100% free
        </motion.div>

        {/* Headline */}
        <motion.h1 variants={fadeUp}
          className="text-[clamp(52px,9vw,100px)] font-black tracking-[-4px] leading-[0.95] mb-6"
        >
          Your terminal,
          <br />
          <span className="text-gradient">voice&#8209;first.</span>
        </motion.h1>

        <motion.p variants={fadeUp}
          className="text-[clamp(16px,2vw,20px)] text-muted font-normal leading-relaxed max-w-[500px] mb-10"
        >
          Speak a command in plain English. See exactly what will run.
          Confirm it. Done — in under four seconds.
        </motion.p>

        {/* CTA buttons */}
        <motion.div variants={fadeUp} className="flex items-center gap-3 flex-wrap justify-center mb-16">
          <motion.a
            href="#download"
            className="flex items-center gap-2 px-7 py-3.5 bg-accent text-white text-[15px] font-bold rounded-xl"
            whileHover={{ scale: 1.04, backgroundColor: '#9d5cff', boxShadow: '0 8px 40px rgba(124,58,237,0.45)' }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 22 }}
          >
            <Download size={16} />
            Download for Mac
          </motion.a>
          <motion.a
            href="https://github.com/yourusername/voxterm"
            target="_blank"
            className="flex items-center gap-2 px-6 py-3.5 border border-white/[0.08] text-muted text-[15px] font-medium rounded-xl"
            whileHover={{ borderColor: 'rgba(255,255,255,0.2)', color: '#f0f0f8', scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 22 }}
          >
            <Github size={16} />
            View on GitHub
          </motion.a>
        </motion.div>

        {/* Terminal */}
        <motion.div variants={fadeUp} className="w-full flex justify-center">
          <TerminalMockup />
        </motion.div>
      </motion.div>
    </section>
  )
}

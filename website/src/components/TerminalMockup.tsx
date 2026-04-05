import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

type Stage = 'idle' | 'listening' | 'transcribed' | 'thinking' | 'command' | 'output'

const DEMOS = [
  {
    said: 'show me what\'s in downloads',
    cmd: 'ls -la ~/Downloads',
    expl: 'list files in Downloads',
    risk: 'low' as const,
    output: ['total 284', 'drwx------  12 soorya  staff   384', '-rw-r--r--   1 soorya  staff  2.1M  design-v3.fig', '-rw-r--r--   1 soorya  staff   840  notes.md', '-rw-r--r--   1 soorya  staff  14M   voxterm.dmg'],
  },
  {
    said: 'push my changes to github',
    cmd: 'git push origin main',
    expl: 'push commits to remote',
    risk: 'medium' as const,
    output: ['Enumerating objects: 5, done.', 'Writing objects: 100% (3/3)', 'To github.com:soorya/voxterm.git', '   a3f1c2b..d4e9f01  main → main'],
  },
  {
    said: 'find large files over 100MB',
    cmd: 'find . -size +100M -type f',
    expl: 'find files larger than 100MB',
    risk: 'low' as const,
    output: ['./node_modules/.cache/bundle.js', './dist/voxterm-bundle.js', './assets/demo-recording.mov'],
  },
]

const RISK_COLOR = { low: '#34d399', medium: '#fcd34d', high: '#f87171' }
const SPINNERS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
const WAVE_DELAYS = [0, 0.1, 0.2, 0.3, 0.15, 0.25, 0.05, 0.35]

export default function TerminalMockup() {
  const [stage, setStage] = useState<Stage>('idle')
  const [demoIdx, setDemoIdx] = useState(0)
  const [spinFrame, setSpinFrame] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const demo = DEMOS[demoIdx % DEMOS.length]

  // Spinner tick
  useEffect(() => {
    if (stage !== 'thinking') return
    const id = setInterval(() => setSpinFrame(f => f + 1), 80)
    return () => clearInterval(id)
  }, [stage])

  // State machine
  useEffect(() => {
    const go = (next: Stage, delay: number) => {
      timerRef.current = setTimeout(() => setStage(next), delay)
    }
    if (stage === 'idle')        go('listening',   800)
    if (stage === 'listening')   go('transcribed', 1800)
    if (stage === 'transcribed') go('thinking',    600)
    if (stage === 'thinking')    go('command',     1600)
    if (stage === 'command')     go('output',      demo.risk === 'low' ? 400 : 1000)
    if (stage === 'output') {
      timerRef.current = setTimeout(() => {
        setStage('idle')
        setDemoIdx(i => i + 1)
      }, 3200)
    }
    return () => clearTimeout(timerRef.current)
  }, [stage, demo.risk])

  return (
    <div className="w-full max-w-[640px] relative">
      {/* Glow behind terminal */}
      <div className="absolute inset-0 rounded-2xl bg-gradient-radial from-accent/20 to-transparent blur-2xl scale-110 -z-10" />

      {/* Border gradient */}
      <div className="absolute -inset-px rounded-2xl bg-gradient-to-br from-accent/40 via-cyan/10 to-transparent -z-[1]" />

      <motion.div
        className="relative rounded-2xl overflow-hidden border border-white/[0.06]"
        style={{ background: 'rgba(13,13,26,0.92)', backdropFilter: 'blur(20px)' }}
        whileHover={{ y: -2 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3.5 border-b border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.02)' }}>
          <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          <span className="flex-1 text-center text-[11px] text-muted font-medium mr-8">voxterm — zsh</span>
        </div>

        {/* Body */}
        <div className="p-6 font-mono text-[12.5px] leading-relaxed min-h-[240px] flex flex-col gap-1">
          {/* Static prompt */}
          <div className="text-muted">
            ~ <span className="text-accent-mid">$</span> <span className="text-white/60">vt</span>
          </div>

          <AnimatePresence mode="wait">

            {/* Listening */}
            {stage === 'listening' && (
              <motion.div key="listening"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex items-center gap-3 mt-1"
              >
                <div className="flex items-end gap-[3px] h-7">
                  {WAVE_DELAYS.map((d, i) => (
                    <motion.div
                      key={i}
                      className="w-[3px] rounded-sm bg-cyan"
                      animate={{ height: ['6px', '22px', '6px'] }}
                      transition={{ duration: 0.7, delay: d, repeat: Infinity, ease: 'easeInOut' }}
                    />
                  ))}
                </div>
                <span className="text-cyan font-semibold">listening</span>
              </motion.div>
            )}

            {/* Transcribed + thinking + command + output */}
            {(stage === 'transcribed' || stage === 'thinking' || stage === 'command' || stage === 'output') && (
              <motion.div key="content"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex flex-col gap-2 mt-1"
              >
                {/* You said */}
                <motion.div
                  initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.4 }}
                >
                  <span className="text-muted">you said: </span>
                  <span className="text-white font-semibold">"{demo.said}"</span>
                </motion.div>

                {/* Thinking */}
                {(stage === 'thinking') && (
                  <motion.div
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="text-accent-mid"
                  >
                    <span>{SPINNERS[spinFrame % SPINNERS.length]}</span>
                    <span className="ml-2">thinking...</span>
                  </motion.div>
                )}

                {/* Command panel */}
                {(stage === 'command' || stage === 'output') && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    className="rounded-lg border p-3 mt-1"
                    style={{
                      borderColor: RISK_COLOR[demo.risk] + '40',
                      background: RISK_COLOR[demo.risk] + '08',
                    }}
                  >
                    <div className="text-[10px] font-semibold mb-1.5 uppercase tracking-wider"
                      style={{ color: RISK_COLOR[demo.risk] }}>
                      {demo.risk} risk · command to run
                    </div>
                    <div style={{ color: '#67e8f9' }}>{demo.cmd}</div>
                    <div className="text-muted text-[11px] mt-1">{demo.expl}</div>

                    {/* Confirm prompt for medium */}
                    {demo.risk === 'medium' && stage === 'output' && (
                      <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                        className="mt-2 text-amber"
                      >
                        run this? [Y/n] <span className="opacity-50">y</span>
                      </motion.div>
                    )}
                  </motion.div>
                )}

                {/* Output */}
                {stage === 'output' && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: demo.risk === 'low' ? 0 : 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="rounded-lg border border-emerald/30 p-3"
                    style={{ background: 'rgba(52,211,153,0.05)' }}
                  >
                    <div className="text-[10px] font-semibold text-emerald mb-1.5 uppercase tracking-wider">output</div>
                    {demo.output.map((line, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.06 }}
                        className="text-muted text-[11px] leading-relaxed"
                      >
                        {line}
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}

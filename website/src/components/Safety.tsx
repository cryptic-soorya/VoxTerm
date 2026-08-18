import { motion } from 'framer-motion'
import { fadeUp, stagger, viewportOnce } from '../lib/animations'

const RISKS = [
  {
    level: 'low', color: '#2dd4a7', bg: 'rgba(45,212,167,0.05)', border: 'rgba(45,212,167,0.2)',
    title: 'Runs immediately',
    desc: 'Read-only commands run without prompting. You asked, it runs. Zero friction for safe operations.',
    examples: ['ls -la ~/Downloads', 'git status', 'cat README.md'],
    action: null,
  },
  {
    level: 'medium', color: '#fbbf24', bg: 'rgba(251,191,36,0.05)', border: 'rgba(251,191,36,0.2)',
    title: 'Shows command, asks Y/n',
    desc: 'File moves, installs, git pushes — shown in full with a plain-English explanation. One keypress.',
    examples: ['git push origin main', 'npm install lodash', 'mkdir -p src/components'],
    action: 'Y/n',
  },
  {
    level: 'high', color: '#fb7185', bg: 'rgba(251,113,133,0.05)', border: 'rgba(251,113,133,0.2)',
    title: 'Must type "yes" in full',
    desc: 'Deletions, sudo, chmod — full warning panel. Type the word "yes". No shortcuts, no enter key cheats.',
    examples: ['rm -rf node_modules/', 'sudo chmod 755 ./script', 'chown -R user:group .'],
    action: 'yes',
  },
]

export default function Safety() {
  return (
    <section id="safety" className="py-32 px-6 text-center">
      <div className="max-w-[1040px] mx-auto">

        <motion.div variants={stagger(0.08)} initial="hidden" whileInView="visible" viewport={viewportOnce} className="mb-16">
          <motion.span variants={fadeUp} className="inline-block text-[11px] font-bold uppercase tracking-[1.5px] text-accent-mid mb-4">
            Safety
          </motion.span>
          <motion.h2 variants={fadeUp} className="text-[clamp(36px,5vw,58px)] font-black tracking-[-2px] leading-[1.1] mb-5">
            It shows you everything<br />before it runs anything.
          </motion.h2>
          <motion.p variants={fadeUp} className="text-[17px] text-muted max-w-[500px] mx-auto">
            The LLM's risk assessment is a suggestion. Hardcoded rules are law.
            No prompt engineering can make VoxTerm silently delete your files.
          </motion.p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {RISKS.map((risk, i) => (
            <motion.div
              key={risk.level}
              initial={{ opacity: 0, y: 32 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={viewportOnce}
              transition={{ delay: i * 0.12, duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ y: -6, boxShadow: `0 20px 48px ${risk.color}18` }}
              className="rounded-2xl p-7 border text-left cursor-default transition-shadow shadow-card"
              style={{ background: risk.bg, borderColor: risk.border }}
            >
              <span
                className="inline-block text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full mb-5"
                style={{ background: `${risk.color}20`, color: risk.color }}
              >
                {risk.level} risk
              </span>

              <h3 className="text-[19px] font-bold tracking-tight mb-3">{risk.title}</h3>
              <p className="text-[13.5px] text-muted leading-relaxed mb-5">{risk.desc}</p>

              <div className="flex flex-col gap-2 mb-5">
                {risk.examples.map((ex, j) => (
                  <motion.div
                    key={j}
                    initial={{ opacity: 0, x: -8 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={viewportOnce}
                    transition={{ delay: i * 0.12 + j * 0.06 + 0.2 }}
                    className="font-mono text-[12px] px-3 py-2 rounded-lg"
                    style={{ background: `${risk.color}0d`, color: risk.color }}
                  >
                    {ex}
                  </motion.div>
                ))}
              </div>

              {risk.action && (
                <motion.div
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  viewport={viewportOnce}
                  transition={{ delay: i * 0.12 + 0.4 }}
                  className="font-mono text-[12px] px-3 py-2 rounded-lg border flex items-center gap-2"
                  style={{ borderColor: `${risk.color}30`, color: '#8a877f' }}
                >
                  <span style={{ color: risk.color }}>&rsaquo;</span>
                  {risk.level === 'medium' ? 'run this? [Y/n]' : 'type "yes" to confirm:'}
                  <motion.span
                    style={{ color: risk.color }}
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity }}
                  >
                    {risk.action}▌
                  </motion.span>
                </motion.div>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

// Frontend-only heuristics for the review composer preview and anomaly flag.
// The authoritative sentiment still comes from the backend (HF/VADER) on submit;
// this only powers instant UI feedback (matches the FirstFind Store mockup).

export function previewSentiment(text) {
  const t = (text || '').trim()
  if (!t) return null
  const s = t.toLowerCase()
  if (['bad', 'rude', 'dirty', 'overpriced', 'waste', 'never', 'disappointed', 'bakwaas'].some(w => s.includes(w)))
    return { key: 'neg', label: 'Negative', color: 'var(--sent-neg)' }
  if (isAnomalous(t))
    return { key: 'flag', label: 'Flagged · possibly fake', color: 'var(--sent-flag)' }
  if (['love', 'great', 'perfect', 'best', 'amazing', 'solid', 'worth', 'mast', 'vasool'].some(w => s.includes(w)))
    return { key: 'pos', label: 'Positive', color: 'var(--sent-pos)' }
  return { key: 'neutral', label: 'Neutral', color: 'var(--sent-neutral)' }
}

// Spam/fake heuristic: many exclamation marks or mostly ALL-CAPS.
export function isAnomalous(text) {
  const t = text || ''
  const bangs = (t.match(/!/g) || []).length
  const letters = t.replace(/[^A-Za-z]/g, '')
  const caps = letters.length > 10 && t.replace(/[^A-Z]/g, '').length / letters.length > 0.6
  return bangs >= 3 || caps
}

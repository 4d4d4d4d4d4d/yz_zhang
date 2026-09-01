// Spec 37 — iCalendar (RFC 5545) VEVENT builder for "add to calendar". Pure.
// Emits a single-event VCALENDAR with UTC timestamps, TEXT escaping, and
// 75-char line folding so Google/Outlook/Apple all import it cleanly.

function fmtUtc(ms) {
  const d = new Date(ms)
  const p = n => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `T${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`
}

// RFC 5545 §3.3.11: backslash, semicolon, comma and newlines are escaped.
export function escapeText(value) {
  return String(value ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n')
}

// RFC 5545 §3.1: lines longer than 75 chars fold onto continuation lines that
// begin with a single space. (Folded by character; ASCII content is octet-exact.)
export function foldLine(line) {
  if (line.length <= 75) return line
  const out = [line.slice(0, 75)]
  let rest = line.slice(75)
  while (rest.length > 74) {
    out.push(' ' + rest.slice(0, 74))
    rest = rest.slice(74)
  }
  if (rest.length) out.push(' ' + rest)
  return out.join('\r\n')
}

export function buildEvent({ title = '', start, end, description = '', location = '', uid = 'evt', now = Date.now() } = {}) {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//AdForge//Meeting Planner//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${fmtUtc(now)}`,
    `DTSTART:${fmtUtc(start)}`,
    `DTEND:${fmtUtc(end)}`,
    `SUMMARY:${escapeText(title)}`,
    description ? `DESCRIPTION:${escapeText(description)}` : null,
    location ? `LOCATION:${escapeText(location)}` : null,
    'END:VEVENT',
    'END:VCALENDAR'
  ].filter(Boolean)
  return lines.map(foldLine).join('\r\n')
}

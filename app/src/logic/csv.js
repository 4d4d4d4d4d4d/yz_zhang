// Spec 35 — RFC 4180 CSV serialization for table export. Pure. A field is
// quoted only when it contains a comma, quote, or newline; embedded quotes
// are doubled. Rows are CRLF-joined per the spec so Excel parses them cleanly.

export function csvCell(value) {
  const s = value === null || value === undefined ? '' : String(value)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

// columns: [{ key, label }]. Emits a header row followed by one row per record.
export function toCsv(rows, columns) {
  const cols = Array.isArray(columns) ? columns : []
  const header = cols.map(c => csvCell(c.label ?? c.key)).join(',')
  const body = (Array.isArray(rows) ? rows : [])
    .map(r => cols.map(c => csvCell(r?.[c.key])).join(','))
    .join('\r\n')
  return body ? `${header}\r\n${body}` : header
}

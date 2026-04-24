// Convierte un array de objetos en CSV y dispara descarga en el navegador.

function escapeCell(value) {
  if (value === null || value === undefined) return ''
  let str
  if (typeof value === 'object') {
    try {
      str = JSON.stringify(value)
    } catch {
      str = String(value)
    }
  } else {
    str = String(value)
  }
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function rowsToCsv(rows) {
  if (!rows || rows.length === 0) return ''
  const headers = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row || {}).forEach((k) => set.add(k))
      return set
    }, new Set())
  )
  const lines = [headers.join(',')]
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCell(row?.[h])).join(','))
  }
  return lines.join('\r\n')
}

export function downloadCsv(rows, filename = 'leads.csv') {
  const csv = rowsToCsv(rows)
  // BOM para que Excel detecte UTF-8 correctamente
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

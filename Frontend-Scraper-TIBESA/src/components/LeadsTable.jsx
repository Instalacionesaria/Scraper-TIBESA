// Tabla genérica para mostrar leads scrapeados.
// Detecta columnas automáticamente a partir de los campos primitivos del primer objeto.

function formatCell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (Array.isArray(value)) {
    if (value.length === 0) return '—'
    if (value.every((v) => typeof v !== 'object')) return value.join(', ')
    return `${value.length} items`
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return '[objeto]'
    }
  }
  return String(value)
}

function isLinkish(value) {
  return typeof value === 'string' && /^https?:\/\//i.test(value)
}

function isEmail(value) {
  return typeof value === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

function humanizeHeader(key) {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, (c) => c.toUpperCase())
}

function pickColumns(rows) {
  const counts = new Map()
  for (const row of rows) {
    for (const key of Object.keys(row || {})) {
      counts.set(key, (counts.get(key) || 0) + 1)
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => k)
}

export default function LeadsTable({ rows, title = 'Leads scrapeados', maxRows = 100 }) {
  if (!rows || rows.length === 0) return null

  const columns = pickColumns(rows)
  const visible = rows.slice(0, maxRows)
  const hidden = rows.length - visible.length

  return (
    <div className="mt-6 bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-800">{title}</h2>
        <span className="text-xs text-gray-500">
          {rows.length} {rows.length === 1 ? 'resultado' : 'resultados'}
        </span>
      </div>

      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200 text-gray-600">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="text-left font-medium px-3 py-2.5 whitespace-nowrap"
                >
                  {humanizeHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {visible.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-50">
                {columns.map((col) => {
                  const raw = row?.[col]
                  const text = formatCell(raw)
                  let content
                  if (isLinkish(raw)) {
                    content = (
                      <a
                        href={raw}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sky-600 hover:underline"
                      >
                        {text.length > 40 ? text.slice(0, 40) + '…' : text}
                      </a>
                    )
                  } else if (isEmail(raw)) {
                    content = (
                      <a href={`mailto:${raw}`} className="text-sky-600 hover:underline">
                        {text}
                      </a>
                    )
                  } else {
                    content = text.length > 60 ? text.slice(0, 60) + '…' : text
                  }
                  return (
                    <td
                      key={col}
                      className="px-3 py-2 text-gray-700 max-w-xs truncate"
                      title={typeof raw === 'string' ? raw : text}
                    >
                      {content}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hidden > 0 && (
        <p className="text-xs text-gray-500 mt-3">
          Mostrando {visible.length} de {rows.length}. Usa "Descargar CSV" para ver todos.
        </p>
      )}
    </div>
  )
}

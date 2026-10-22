import { useParams } from 'react-router-dom'

import { ErrorLine, Page, Panel, useLoad } from '../ui'

interface Cert {
  serial: string
  course: string
  title: { en: string; es: string }
  level: string
  score: string
  issued_at: string
  resident: string
  resident_code: string
}

/** Certificates a resident has earned. "Print" uses the browser's print dialog; only the certificates print. */
export default function Certificates() {
  const { id } = useParams()
  const { data, error } = useLoad<Cert[]>(`/staff/residents/${id}/certificates`)
  return (
    <Page title="Certificates">
      <style>{`@media print { body * { visibility: hidden } .print-area, .print-area * { visibility: visible } .print-area { position: absolute; inset: 0 } .no-print { display: none } .cert { page-break-after: always } }`}</style>
      <ErrorLine error={error} />
      <button
        type="button"
        className="no-print rounded border px-3 py-2"
        onClick={() => window.print()}
      >
        Print
      </button>
      {data?.length === 0 && <p>No certificates yet.</p>}
      <div className="print-area space-y-6">
        {(data ?? []).map((c) => (
          <Panel key={c.serial} data-testid={`certificate-${c.course}`}>
            <div className="cert border-4 border-double p-8 text-center">
              <p className="text-sm uppercase tracking-wide">Certificate of completion</p>
              <h2 className="mt-3 text-3xl font-bold">{c.title.en}</h2>
              {c.title.es !== c.title.en && <p className="text-lg italic">{c.title.es}</p>}
              <p className="mt-3 text-xl">{c.resident}</p>
              <p className="mt-1">Score {c.score}</p>
              <p>{new Date(c.issued_at).toLocaleDateString()}</p>
              <p className="mt-3 font-mono text-sm">{c.serial}</p>
            </div>
          </Panel>
        ))}
      </div>
    </Page>
  )
}

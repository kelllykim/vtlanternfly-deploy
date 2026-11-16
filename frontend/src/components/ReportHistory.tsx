import { useEffect, useRef, useState } from 'react'
import { getReportHistory, type ReportHistoryItem } from '../services/api'

const dateLabel = (value: string) => new Date(value).toLocaleString(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
})

function ReportCard({ report }: { report: ReportHistoryItem }) {
  const [photoFailed, setPhotoFailed] = useState(false)
  const located = report.latitude !== null && report.longitude !== null
  const status = report.status === 'approved' ? 'AI detected' : report.status === 'rejected'
    ? 'Not identified' : report.detectionStatus === 'unavailable' ? 'Identification unavailable' : 'Pending identification'

  return <article className="history-card">
    <div className="history-photo">
      {photoFailed ? <span>Photo unavailable</span> :
        <a href={report.photoUrl} target="_blank" rel="noreferrer" aria-label={`Open photo for report ${report.reportNumber}`}>
          <img src={report.photoUrl} alt={`Submitted sighting${report.lifeStage ? `: ${report.lifeStage}` : ''}`}
            loading="lazy" onError={() => setPhotoFailed(true)} />
        </a>}
    </div>
    <div className="history-content">
      <div className="history-heading"><strong>{report.lifeStage || 'Sighting report'}</strong><b>+{report.points} pts</b></div>
      <p className={`history-status history-status-${report.status}`}>{status}</p>
      <p><time dateTime={report.submittedAt}>{dateLabel(report.submittedAt)}</time></p>
      <p>{located ? `${report.latitude!.toFixed(5)}, ${report.longitude!.toFixed(5)}` : 'No photo location'}</p>
      <details>
        <summary>Report details</summary>
        <dl>
          <dt>Report in my history</dt><dd>#{report.reportNumber}</dd>
          <dt>Photo taken</dt><dd>{report.capturedAt ? dateLabel(report.capturedAt) : 'Not recorded'}</dd>
          <dt>Map visibility</dt><dd>{report.status === 'approved' && located ? 'Eligible for the sightings map' : report.status !== 'approved' ? 'Only approved sightings appear' : 'Location needed to appear'}</dd>
          {report.confidence !== null && <><dt>Model confidence</dt><dd>{(report.confidence * 100).toFixed(1)}% (not a guaranteed probability)</dd></>}
        </dl>
        <p>Points shown are report rewards. Goal and quiz bonuses are separate.</p>
      </details>
    </div>
  </article>
}

export default function ReportHistory({ userId }: { userId: number }) {
  const [reports, setReports] = useState<ReportHistoryItem[]>([])
  const [nextOffset, setNextOffset] = useState<number | null>(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const generation = useRef(0)
  const busy = useRef(false)

  const load = async (offset: number, version = generation.current) => {
    if (busy.current) return
    busy.current = true
    setLoading(true)
    setError(null)
    try {
      const page = await getReportHistory(offset)
      if (generation.current !== version) return
      setReports(previous => offset === 0 ? page.reports : [...previous, ...page.reports])
      setNextOffset(page.nextOffset)
    } catch (err) {
      if (generation.current === version) setError(err instanceof Error ? err.message : 'Could not load your reports.')
    } finally {
      if (generation.current === version) { busy.current = false; setLoading(false) }
    }
  }

  useEffect(() => {
    const version = ++generation.current
    busy.current = false
    setReports([])
    setNextOffset(0)
    void load(0, version)
    return () => { generation.current += 1 }
  }, [userId])

  return <section className="report-history" aria-label="Your report history" aria-busy={loading}>
    <p className="history-intro">Your submitted photos, newest first. Open a photo or expand its details to revisit a report.</p>
    {reports.map(report => <ReportCard key={report.id} report={report} />)}
    {!loading && !error && reports.length === 0 && <p className="history-empty">No reports yet. Report a lanternfly from the map to start your field log.</p>}
    {loading && <p role="status">Loading your reports…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && (error || nextOffset !== null) && <button type="button" className="secondary"
      onClick={() => void load(nextOffset ?? 0)}>{error ? 'Try again' : 'Load more reports'}</button>}
  </section>
}

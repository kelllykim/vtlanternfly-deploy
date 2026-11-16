import Header from '../components/Header'
import ReportHistory from '../components/ReportHistory'

export default function HistoryScreen({ userId, onBack }: { userId: number; onBack: () => void }) {
  return <main className="screen history-screen">
    <Header title="My History" eyebrow="MY FIELD LOG" onBack={onBack} />
    <ReportHistory userId={userId} />
  </main>
}

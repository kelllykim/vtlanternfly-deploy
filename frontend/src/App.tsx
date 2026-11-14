import { useEffect, useState } from 'react'
import type { Tab, View, Outcome } from './types'
import BottomNav from './components/BottomNav'
import MapScreen from './screens/MapScreen'
import CaptureScreen from './screens/CaptureScreen'
import VerifyingScreen from './screens/VerifyingScreen'
import ResultScreen from './screens/ResultScreen'
import LearnScreen from './screens/LearnScreen'
import TeamsScreen from './screens/TeamsScreen'
import ProfileScreen from './screens/ProfileScreen'
//import WireframePrototype from './screens/WireframePrototype'
import AuthScreen from './screens/AuthScreen'

import type { UserProfile, LeaderboardEntry } from './types'
import { getTeamGoal, type TeamGoal } from './services/api'
import { getUser, passLessonApi, updateSettings } from './services/api'

export default function App() {
  //const [wireframe, setWireframe] = useState(false)
  const [view, setView] = useState<View>('map')
  const [tab, setTabState] = useState<Tab>('map')
  const [outcome, setOutcome] = useState<Outcome>('confirmed')
  const [stage, setStage] = useState('Adult')
  const [pending, setPending] = useState(false)

  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [teamGoal, setTeamGoal] = useState<TeamGoal | null>(null)
  const [pointsAwarded, setPointsAwarded] = useState(0)


  // initialize leaderboard
  useEffect(() => {
      if (view != 'teams') return;
      getTeamGoal().then(setTeamGoal).catch(() => setTeamGoal(null));
  }, [])

  // auto-advance verifying screen after 2 seconds
  useEffect(() => {
    if (view !== 'verifying') return;
    const id = window.setTimeout(() => setView('result'), 2000);
    return () => clearTimeout(id);
  }, [view])

  const setTab = (t: Tab) => { setTabState(t); setView(t) }


  const passLesson = (lesson: number) => {
      if (!currentUser || currentUser.passedLessons.includes(lesson)) return
      passLessonApi(currentUser.id, lesson).then(setCurrentUser).catch(console.error)
  }

  const handleUpdateSettings = (key: string, val: boolean) => {
      if (!currentUser) return
      const previous = currentUser
      setCurrentUser({ ...currentUser, [key]: val })
      updateSettings(currentUser.id, { [key]: val }).then(setCurrentUser).catch(() => setCurrentUser(previous))
  }

  const done = () => { setTab('map') }
  const resultTeam = () => { setTab('teams') }
  const resultLearn = () => {
    setTabState('learn');
    setView('learn');
    setTimeout(()=>document.getElementById('lookalikes')?.scrollIntoView({behavior:'smooth'}), 100)
  }

  //if (wireframe) return <WireframePrototype onExit={() => setWireframe(false)} />

  // keep user logged in after page refresh
  useEffect(() => {
    try {
      const saved = localStorage.getItem('vtlanternfly.userId')
      if (saved) getUser(Number(saved)).then(setCurrentUser).catch(() => localStorage.removeItem('vtlanternfly.userId'))
    } catch { /* storage unavailable */ }
  }, [])

  // trap user in AuthScreen if not logged in
  if (!currentUser) {
    return (
        <div className="app-shell">
          <div className="web-container">
            <AuthScreen onLogin={(user) => {
              setCurrentUser(user)
              try { localStorage.setItem('vtlanternfly.userId', String(user.id)) } catch { /* ignore */ }
            }} />
          </div>
        </div>
    );
  }

  return (
      <div className="app-shell">
        <div className="web-container">

          {view === 'map' && <MapScreen onReport={()=> {setView('capture');}}/>}
          {view === 'capture' && <CaptureScreen
              userId={currentUser.id}
              onBack={()=>setTab('map')}
              onSuccess={(res) => {
                  if (res.user) setCurrentUser(res.user)
                  setPointsAwarded(res.points_awarded ?? 0)
                  if (res.verification_status === 'approved') {
                    setOutcome('confirmed')
                    setStage(res.life_stage || 'Adult')
                  } else {
                    setOutcome('uncertain')
                  }
                  setView('verifying')
              }}
          />}
            {view === 'verifying' && <VerifyingScreen onBack={()=>setView('capture')}/>}
            {view === 'result' && <ResultScreen outcome={outcome} stage={stage} points={pointsAwarded} onDone={done} onLearn={resultLearn} onTeam={resultTeam} onRetake={()=>setView('capture')}/>}
            {view === 'learn' && <LearnScreen passedLessons={currentUser.passedLessons} passLesson={passLesson}/>}
            {view === 'teams' && <TeamsScreen teamsData={leaderboard} teamGoal={teamGoal}/>}
            {view === 'me' && <ProfileScreen user={currentUser} onUpdateSettings={handleUpdateSettings}/>}

            {(['map','learn','teams','me'] as string[]).includes(view) && <BottomNav tab={tab} setTab={setTab}/>}
        </div>
      </div>
  )
}
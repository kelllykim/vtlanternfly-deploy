import { useEffect, useRef, useState } from 'react'
import type { Tab, View, Outcome } from './types'
import BottomNav from './components/BottomNav'
import { LogoutContext } from './components/AccountMenu'
import MapScreen from './screens/MapScreen'
import CaptureScreen from './screens/CaptureScreen'
import ResultScreen from './screens/ResultScreen'
import LearnScreen from './screens/LearnScreen'
import TeamsScreen from './screens/TeamsScreen'
import ProfileScreen from './screens/ProfileScreen'
import HistoryScreen from './screens/HistoryScreen'
//import WireframePrototype from './screens/WireframePrototype'
import AuthScreen from './screens/AuthScreen'

import type { UserProfile } from './types'
import { getUser, passLessonApi, updateSettings, logoutUser, claimGoalRewards } from './services/api'

export default function App() {
  //const [wireframe, setWireframe] = useState(false)
  const [view, setView] = useState<View>('map')
  const [tab, setTabState] = useState<Tab>('map')
  const [outcome, setOutcome] = useState<Outcome>('confirmed')
  const [stage, setStage] = useState('Adult')
  const [authLoading, setAuthLoading] = useState(true)
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const [duplicate, setDuplicate] = useState(false)

  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [pointsAwarded, setPointsAwarded] = useState(0)
  const [missingGps, setMissingGps] = useState(false)
  const [initiallyRegistering, setInitiallyRegistering] = useState(true)
  const sessionVersion = useRef(0)
  const activeSession = sessionVersion.current
  const clearSession = () => {
    sessionVersion.current += 1
    try { localStorage.removeItem('vtlanternfly.userId') } catch { /* storage unavailable */ }
    setInitiallyRegistering(false)
    setCurrentUser(null)
    setTabState('map')
    setView('map')
    setPointsAwarded(0)
    setDuplicate(false)
  }
  const logout = async () => {
    setLogoutError(null)
    try {
      await logoutUser()
      clearSession()
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Could not log out. Please try again.')
    }
  }


  // Refresh contributions and rank whenever the profile is opened.
  const currentUserId = currentUser?.id
  useEffect(() => {
    if (view !== 'me' || !currentUserId) return
    let cancelled = false
    getUser().then(user => {
      if (!cancelled) setCurrentUser(user)
    }).catch(console.error)
    return () => { cancelled = true }
  }, [view, currentUserId])

  const claimGoal = async (key: string, period: string) => {
    const version = sessionVersion.current
    const user = await claimGoalRewards(key, period)
    if (sessionVersion.current === version) setCurrentUser(user)
  }

  const setTab = (t: Tab) => { setTabState(t); setView(t) }


  const passLesson = (lesson: number) => {
      if (!currentUser || currentUser.passedLessons.includes(lesson)) return
      passLessonApi(lesson).then(user => { if (sessionVersion.current === activeSession) setCurrentUser(user) }).catch(console.error)
  }

  const handleUpdateSettings = (key: string, val: boolean) => {
      if (!currentUser) return
      const previous = currentUser
      setCurrentUser({ ...currentUser, [key]: val })
      updateSettings({ [key]: val }).then(user => { if (sessionVersion.current === activeSession) setCurrentUser(user) }).catch(() => { if (sessionVersion.current === activeSession) setCurrentUser(previous) })
  }

  const done = () => { setTab('map') }
  const resultTeam = () => { setTab('teams') }
  const resultLearn = () => {
    setTabState('learn');
    setView('learn');
    setTimeout(()=>document.getElementById('lookalikes')?.scrollIntoView({behavior:'smooth'}), 100)
  }

  //if (wireframe) return <WireframePrototype onExit={() => setWireframe(false)} />

  // Restore only a server-validated cookie session; old local IDs cannot log in.
  useEffect(() => {
    let cancelled = false
    try { localStorage.removeItem('vtlanternfly.userId') } catch { /* storage unavailable */ }
    getUser().then(user => {
      if (!cancelled) setCurrentUser(user)
    }).catch(() => {}).finally(() => { if (!cancelled) setAuthLoading(false) })
    const expired = () => { clearSession() }
    window.addEventListener('vtlanternfly:session-expired', expired)
    return () => {
      cancelled = true
      window.removeEventListener('vtlanternfly:session-expired', expired)
    }
  }, [])

  if (authLoading) return <div className="app-shell"><main className="screen web-container"><p role="status">Checking your session…</p></main></div>

  // trap user in AuthScreen if not logged in
  if (!currentUser) {
    return (
        <div className="app-shell">
          <div className="web-container">
            <AuthScreen initiallyRegistering={initiallyRegistering} onLogin={(user) => {
              setCurrentUser(user)
              setLogoutError(null)
            }} />
          </div>
        </div>
    );
  }

  return (
      <LogoutContext.Provider value={logout}>
      <div className="app-shell">
        <div className="web-container">

          {logoutError && <p role="alert" style={{ padding: '16px', color: '#b91c1c' }}>{logoutError}</p>}
          {view === 'map' && <MapScreen onReport={()=> {setView('capture');}}/>}
          {view === 'capture' && <CaptureScreen
              onBack={()=>setTab('map')}
              onSuccess={(res) => {
                  if (sessionVersion.current !== activeSession) return
                  if (res.user) setCurrentUser(res.user)
                  setPointsAwarded(res.points_awarded ?? 0)
                  setDuplicate(res.duplicate)
                  setMissingGps(res.metadata.latitude == null || res.metadata.longitude == null)
                  if (res.verification_status === 'approved') {
                    setOutcome('confirmed')
                    setStage(res.life_stage || 'Adult')
                  } else {
                    setOutcome('uncertain')
                  }
                  setView('result')
              }}
          />}
            {view === 'result' && <ResultScreen outcome={outcome} stage={stage} points={pointsAwarded} missingGps={missingGps} duplicate={duplicate} onDone={done} onLearn={resultLearn} onTeam={resultTeam} onRetake={()=>setView('capture')}/>}
            {view === 'learn' && <LearnScreen passedLessons={currentUser.passedLessons} passLesson={passLesson}/>}
            {view === 'teams' && <TeamsScreen userId={currentUser.id}/>}
            {view === 'me' && <ProfileScreen user={currentUser} onUpdateSettings={handleUpdateSettings} onClaimGoal={claimGoal} onHistory={() => { setView('history'); window.scrollTo(0, 0) }}/>}
            {view === 'history' && <HistoryScreen userId={currentUser.id} onBack={() => { setTab('me'); window.scrollTo(0, 0) }}/>}

            {(['map','learn','teams','me'] as string[]).includes(view) && <BottomNav tab={tab} setTab={setTab}/>}
        </div>
      </div>
      </LogoutContext.Provider>
  )
}

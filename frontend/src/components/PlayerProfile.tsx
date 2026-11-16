import { useEffect, useState } from 'react'
import Header from './Header'
import Icon from './Icon'
import { getPublicProfile, type PublicProfile } from '../services/api'

export default function PlayerProfile({ userId, onBack }: { userId: number; onBack: () => void }) {
    const [profile, setProfile] = useState<PublicProfile | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [attempt, setAttempt] = useState(0)
    useEffect(() => {
        let cancelled = false
        setError(null)
        getPublicProfile(userId).then(value => { if (!cancelled) setProfile(value) })
            .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load profile') })
        return () => { cancelled = true }
    }, [userId, attempt])
    return <main className="screen profile-screen">
        <Header title="Player profile" eyebrow="LEADERBOARD" onBack={onBack} />
        {error ? <div role="alert"><p>{error}</p><button className="secondary" onClick={() => setAttempt(value => value + 1)}>Try again</button></div>
            : !profile ? <p role="status">Loading profile…</p> : <>
                <section className="profile-hero">
                    <div className="avatar">{profile.displayName.split(' ').map(word => word[0]).join('').slice(0, 2).toUpperCase()}</div>
                    <h2>{profile.displayName}</h2>
                    <p>{profile.major || 'Virginia Tech Student'}</p>
                    <div className="profile-stats">
                        <div><b>{profile.points}</b><span>Points</span></div>
                        <div><b>{profile.streak}</b><span>Day streak</span></div>
                    </div>
                </section>
                <div className="section-title"><div><small>ACHIEVEMENTS</small><h2>Unlocked badges</h2></div>{!profile.badgesPrivate && <span>{profile.badges.length} earned</span>}</div>
                {profile.badgesPrivate ? <p>This player’s badges are private.</p> : profile.badges.length ? <div className="badge-grid">{profile.badges.map(badge => <article className={`earned${badge === 'On a Roll' ? ` streak-badge tier-${profile.streakBadgeTier}` : ''}`} key={badge}>
                    <div><Icon name={badge === 'Major Mate' ? 'users' : badge === 'On a Roll' ? 'flame' : badge === 'First Squash' ? 'check' : 'trophy'} /></div>
                    <b>{badge}</b><small>{badge === 'On a Roll' ? `${profile.streakBadgeTier}-day streak` : 'Earned'}</small>
                </article>)}</div> : <p>No badges unlocked yet.</p>}
            </>}
    </main>
}

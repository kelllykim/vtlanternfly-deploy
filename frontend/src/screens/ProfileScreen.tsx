import Header from '../components/Header';
import { useState } from 'react';
import Icon from '../components/Icon';
import type { UserProfile } from '../types.tsx';
import '../styles/features.css';

export default function ProfileScreen({ user, onUpdateSettings, onHistory, onClaimGoal }: { user: UserProfile; onUpdateSettings: (key: string, val: boolean) => void; onHistory: () => void; onClaimGoal: (key: string, period: string) => Promise<void> }) {
    const [claiming, setClaiming] = useState<string | null>(null)
    const [claimError, setClaimError] = useState<string | null>(null)
    const [claimMessage, setClaimMessage] = useState<string | null>(null)
    const claim = async (goal: UserProfile['goals'][number]) => {
        if (claiming) return
        setClaiming(goal.key)
        setClaimError(null)
        setClaimMessage(null)
        try {
            await onClaimGoal(goal.key, goal.period)
            setClaimMessage(`Claimed +${goal.points} points for ${goal.label}.`)
        } catch (err) {
            setClaimError(err instanceof Error ? err.message : 'Could not claim points. Please try again.')
        } finally { setClaiming(null) }
    }
    const hasBadge = user.passedLessons.length === 3
    const badgeList: [string, string, boolean][] = [
        ['Field Expert', 'trophy', hasBadge || user.badges.includes('Field Expert')],
        ['First Squash', 'check', user.reportsTotal > 0 || user.badges.includes('First Squash')],
        ['Major Mate', 'users', user.badges.includes('Major Mate')],
        ['On a Roll', 'flame', user.badges.includes('On a Roll')],
    ]
    const earnedCount = badgeList.filter(([, , on]) => on).length

    const initials = user.displayName.split(' ').map(n => n[0]).join('').toUpperCase().substring(0,2);

    return <main className="screen profile-screen">
        <Header title="My field log" eyebrow="PROFILE" />
        <section className="profile-hero">
            <div className="avatar">
                {initials}
                <span>
                    {user.streak}
                </span>
            </div>
            <h2>{user.anonymous ? 'Anonymous Hokie' : user.displayName}</h2>
            <p>{user.major ? user.major : 'Virginia Tech Student'}</p>

            <div className="profile-stats">
                <div><b>#{user.rank}</b>
                    <span>Campus rank</span>
                </div>
                <div><b>{user.points}</b>
                    <span>Points</span>
                </div>
                <div>
                    <b><Icon name="flame" size={17}/>{user.streak}</b><span>Day streak</span>
                </div>
            </div>
        </section>
        <p className="streak-explanation">Upload an AI-detected lanternfly each day to grow your streak. Any life stage counts, once per day. Missing a full day resets it to 0. Days follow Virginia Tech local time.</p>
        <div className="section-title">
            <div>
                <small>ACHIEVEMENTS</small>
                <h2>Badges</h2></div><span>{earnedCount} of {badgeList.length}</span></div>
        <div className="badge-grid">{badgeList.map(([n,ic,on]) => <article className={on ? 'earned':'locked'} key={String(n)}><div><Icon name={String(ic)}/></div><b>{n}</b><small>{on ? 'Earned' : 'Locked'}</small>{n === 'Field Expert' && <small>Pass all three field guide quizzes.</small>}{n === 'First Squash' && <small>Submit your first approved lanternfly sighting.</small>}{n === 'On a Roll' && <small>Upload an approved lanternfly sighting on three consecutive days.</small>}{n === 'Major Mate' && <small>Add one friend in your major. Their request must be accepted.</small>}</article>)}</div>
        <section className="learn-progress-card">
            <div>
                <small>LEARN PROGRESS</small>
                <b>{user.passedLessons.length}/3 quizzes passed</b>
            </div>

            <div className="bar">
                <i style={{width: `${user.passedLessons.length / 3 * 100}%`}} />
            </div>
            <p>{hasBadge ? 'Field Expert earned' : 'Pass all three to earn Field Expert'}</p>
        </section>
        <div className="section-title">
            <div>
                <small>CONTRIBUTIONS</small>
                <h2>My reports</h2></div>
            <span>{user.reportsTotal} verified</span>
        </div>
        <section className="report-summary">
            <div>
                <span>◆</span><b>{user.reportsByStage.adult}</b><small>Adults</small>
            </div>
            <div><span>✣</span><b>{user.reportsByStage.nymph}</b><small>Nymphs</small></div>
            <div><span>≋</span><b>{user.reportsByStage.eggMass}</b><small>Egg masses</small></div>
        </section>
        <button type="button" className="history-link" onClick={onHistory}>
            <span><strong>My History</strong><small>Press to view my history</small></span>
            <span aria-hidden="true">→</span>
        </button>
        <div className="section-title">
            <div><small>EARN 10 POINTS EACH</small>
                <h2>Goals</h2>
            </div>
        </div>
        <section className="personal-goals">{user.goals.map(goal =>
            <div key={goal.key} className={goal.completed ? 'complete' : ''}>
                <span>{goal.completed ? <Icon name="check" size={16}/> : ''}</span>
                <b>{goal.label}</b>
                <div className="goal-reward">
                    <small>{goal.current}/{goal.target} · {goal.rewarded ? `+${goal.points} claimed` : `+${goal.points} pts`}</small>
                    {goal.completed && !goal.rewarded && <button type="button" className="goal-claim"
                        disabled={claiming !== null} onClick={() => void claim(goal)}
                        aria-label={`Claim ${goal.points} points for ${goal.label}`}>
                        {claiming === goal.key ? 'Claiming…' : `Claim +${goal.points} points`}
                    </button>}
                </div>
            </div>)}
        </section>
        {claimError && <p role="alert" className="goal-feedback">{claimError}</p>}
        {claimMessage && <p role="status" className="goal-feedback">{claimMessage}</p>}

        <div className="section-title">
            <div><small>SETTINGS</small><h2>Privacy</h2></div></div>
        <section className="settings"><label><div><b>Appear anonymous</b>
            <small>On public leaderboards</small></div><input type="checkbox" checked={user.anonymous} onChange={e=>onUpdateSettings('anonymous', e.target.checked)}/><i/></label><label>
            <div>
                <b>Share data with VT researchers</b><small>Helps improve campus response</small>
            </div><input type="checkbox" checked={user.shareWithResearchers} onChange={e=>onUpdateSettings('shareWithResearchers', e.target.checked)}/><i/></label>
        </section>
    </main>
}

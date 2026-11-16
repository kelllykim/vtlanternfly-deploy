import {useEffect, useState} from "react";
import Header from '../components/Header';
import PlayerProfile from '../components/PlayerProfile';
import Icon from '../components/Icon';
import '../styles/features.css';
import type { LeaderboardEntry, LeaderboardSegment } from '../types';
import { getLeaderboard, getTeamGoal, getFriendRequests, sendFriendRequest, respondToFriendRequest, type FriendRequest, type TeamGoal } from '../services/api';

export default function Teams({ userId }: { userId: number }) {
    const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null)
    const [segment, setSegment] = useState<LeaderboardSegment>('Campus')
    const [teamsData, setTeamsData] = useState<LeaderboardEntry[]>([])
    const [teamGoal, setTeamGoal] = useState<TeamGoal | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [refresh, setRefresh] = useState(0)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        setTeamsData([])
        setTeamGoal(null)
        Promise.all([getLeaderboard(segment), getTeamGoal()])
            .then(([entries, goal]) => {
                if (cancelled) return
                setTeamsData(entries)
                setTeamGoal(goal)
            }).catch(err => {
                if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to load rankings')
            }).finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [userId, segment, refresh])

    const [requests, setRequests] = useState<FriendRequest[]>([])
    const [requestsLoading, setRequestsLoading] = useState(true)
    const [friendError, setFriendError] = useState<string | null>(null)
    const [friendMessage, setFriendMessage] = useState<string | null>(null)
    const [showFriendForm, setShowFriendForm] = useState(false)
    const [friendEmail, setFriendEmail] = useState('')
    const [friendBusy, setFriendBusy] = useState(false)

    useEffect(() => {
        let cancelled = false
        const load = () => getFriendRequests().then(items => {
            if (!cancelled) { setRequests(items); setRequestsLoading(false) }
        }).catch(err => {
            if (!cancelled) {
                setFriendError(err instanceof Error ? err.message : 'Failed to load friend requests')
                setRequestsLoading(false)
            }
        })
        load()
        const timer = window.setInterval(load, 15000)
        window.addEventListener('focus', load)
        return () => {
            cancelled = true
            window.clearInterval(timer)
            window.removeEventListener('focus', load)
        }
    }, [userId, refresh])

    const sendRequest = async (event: React.FormEvent) => {
        event.preventDefault()
        if (friendBusy) return
        setFriendBusy(true)
        setFriendError(null)
        setFriendMessage(null)
        try {
            const result = await sendFriendRequest(friendEmail.trim())
            setFriendMessage(result.message)
            setFriendEmail('')
            setShowFriendForm(false)
        } catch (err) {
            setFriendError(err instanceof Error ? err.message : 'Failed to send request')
        } finally { setFriendBusy(false) }
    }

    const respond = async (requesterId: number, action: 'accept' | 'decline') => {
        if (friendBusy) return
        setFriendBusy(true)
        setFriendError(null)
        setFriendMessage(null)
        try {
            const result = await respondToFriendRequest(requesterId, action)
            setFriendMessage(result.message)
            setRequests(items => items.filter(item => item.requesterId !== requesterId))
            setRefresh(value => value + 1)
        } catch (err) {
            setFriendError(err instanceof Error ? err.message : 'Failed to respond to request')
        } finally { setFriendBusy(false) }
    }

    const target = teamGoal?.target ?? 50
    const found = teamGoal?.found ?? 0

    if (selectedPlayer !== null) return <PlayerProfile key={selectedPlayer} userId={selectedPlayer} onBack={() => setSelectedPlayer(null)} />

    return <main className="screen teams-screen">
        <Header title="Leaderboard" eyebrow="TOGETHER, WE SPOT MORE" />
        <div className="segments">
            {(['Friends','Teams','Majors','Campus'] as const).map(x => <button className={segment === x ? 'active':''} onClick={() => setSegment(x)} key={x}>{x}</button>)}
        </div>

        {teamGoal && <section className="goal-card">
            <div className="goal-top">
                <div><small>CAMPUS GOAL</small><h3>{teamGoal?.title ?? 'Loading team goal…'}</h3></div>
                <div className="goal-icon"><Icon name="trophy"/></div>
            </div>
            <div className="bar"><i style={{width: `${Math.min(found / target, 1) * 100}%`}}/></div>
            <p><b>{found}/{target} found</b><span>{Math.max(target - found, 0)} to go</span></p>
        </section>}
        <button className="secondary" onClick={() => setRefresh(value => value + 1)} disabled={loading}>Refresh rankings</button>
        {loading && <p role="status">Loading rankings…</p>}
        {error && <p role="alert">{error}</p>}
        <div className="rank-heading"><span>RANK</span><span>{segment === 'Teams' ? 'TEAM' : segment === 'Majors' ? 'MAJOR' : 'PLAYER'}</span><span title="Approved sightings">SIGHTINGS</span><span>POINTS</span></div>
        <div className="rank-list">
            {!loading && !error && teamsData.length === 0 && <p style={{ textAlign: 'center', color: 'var(--muted)', padding: '24px 0' }}>No rankings yet for this group.</p>}
            {teamsData.map((team, i) => (
                <article className={team.isCurrentUser ? 'is-me' : ''} key={team.id}>
                    <span className={`rank rank-${i}`}>{team.rank}</span>
                    <div className="rank-identity">{segment === 'Friends' || segment === 'Campus' ?
                        <button type="button" className="team-avatar player-profile-button" aria-label={`View ${team.name}'s profile`}
                            onClick={() => { setSelectedPlayer(Number(team.id)); window.scrollTo(0, 0) }}>{team.name[0]}</button>
                        : <span className="team-avatar">{team.name[0]}</span>}
                    <div>
                        <span className="leaderboard-name"><b>{team.name}</b>
                            {(segment === 'Friends' || segment === 'Campus') && team.streak !== undefined &&
                                <span className={`leaderboard-streak${team.streak === 0 ? ' inactive' : ''}`}
                                    title={`${team.streak}-day upload streak`} aria-label={`${team.streak}-day upload streak`}>
                                    <Icon name="flame" size={13}/>{team.streak}
                                </span>}
                        </span>
                        <small>{team.major?.trim() || (team.isCurrentUser ? (segment === 'Teams' ? 'Your team' : segment === 'Majors' ? 'Your major' : 'You') : (segment === 'Teams' ? 'Campus team' : segment === 'Majors' ? 'Major' : 'Campus member'))}</small>
                    </div>
                    </div>
                    <strong aria-label={`${team.sightings} verified sightings`}>{team.sightings}</strong>
                    <strong>{team.points}</strong>
                </article>
            ))}
        </div>
        <div className="team-actions"><button className="primary"><Icon name="share"/> Invite friends</button><button className="secondary">Create team</button><button type="button" className="secondary" style={{ backgroundColor: '#E5751F', color: 'white', borderColor: '#E5751F' }} aria-expanded={showFriendForm} aria-controls="add-friend-form" onClick={() => { setShowFriendForm(value => !value); setFriendError(null); setFriendMessage(null) }}>Add friend</button></div>
        {showFriendForm && <form id="add-friend-form" className="friend-form" onSubmit={sendRequest}>
            <label htmlFor="friend-email">Friend’s email address</label>
            <input id="friend-email" type="email" autoComplete="email" required autoFocus
                value={friendEmail} onChange={event => setFriendEmail(event.target.value)} placeholder="friend@vt.edu" />
            <button className="primary" type="submit" disabled={friendBusy}>{friendBusy ? 'Sending…' : 'Send friend request'}</button>
        </form>}
        {friendMessage && <p role="status" className="friend-feedback">{friendMessage}</p>}
        {friendError && <p role="alert" className="friend-feedback friend-error">{friendError}</p>}
        <section className="friend-requests" aria-labelledby="friend-requests-title">
            <h2 id="friend-requests-title">Friend requests {requests.length > 0 && <span>({requests.length})</span>}</h2>
            {requestsLoading ? <p role="status">Loading friend requests…</p> : requests.length === 0 ? <p>No pending requests.</p> :
                requests.map(request => <article key={request.requesterId}>
                    <p><b>{request.name}</b> wants to be your friend.</p>
                    <div className="friend-request-actions">
                        <button className="primary" type="button" disabled={friendBusy} onClick={() => respond(request.requesterId, 'accept')}>Accept</button>
                        <button className="secondary" type="button" disabled={friendBusy} onClick={() => respond(request.requesterId, 'decline')}>Decline</button>
                    </div>
                </article>)}
        </section>
    </main>
}

import Header from '../components/Header'
import Icon from '../components/Icon'
import type { Outcome } from '../types'
import '../styles/capture.css'

export default function Result({ outcome, stage, points, missingGps, duplicate, onDone, onLearn, onTeam, onRetake }: { outcome: Outcome; stage: string; points: number; missingGps: boolean; duplicate: boolean; onDone: () => void; onLearn: () => void; onTeam: () => void; onRetake: () => void }) {
    const locationNotice = missingGps ? <section className="missing-gps-notice" role="status">
        <strong>This photo won’t update the map</strong>
        <p>No GPS coordinates were found. Enable location permissions for your camera and turn on photo location tags, then take and upload a new photo. Changing permissions won’t add GPS to this existing image. Only approved sightings with GPS appear on the map.</p>
    </section> : null

    if (duplicate) return <main className="screen result-screen">
        <Header title="Photo already submitted" onBack={onDone} eyebrow="UPLOAD RESULT" />
        <div className="result-icon uncertain"><Icon name="camera" size={36}/></div>
        <h2>This photo has already been submitted.</h2>
        <p className="result-copy">No additional points were awarded. The existing report stays with its original account. Upload a different photo to make a new contribution.</p>
        <button className="primary" onClick={onRetake}>Choose another photo</button>
        <button className="secondary" onClick={onDone}>Done</button>
    </main>

    if (outcome === 'confirmed') return <main className="screen result-screen"><Header title="Report complete" onBack={onDone} eyebrow="VERIFICATION RESULT" />
        {locationNotice}
        <div className="result-icon confirmed"><Icon name="check" size={36}/></div><p className="status confirmed-text">CONFIRMED</p><h2>Spotted Lanternfly<br/>— {stage}</h2>
        <div className="points-pill">+{points} points <span>Accurate report</span></div>        <section className="learn-card"><div className="mini-bug"><i/><i/><b/></div><div><small>KNOW WHAT YOU FOUND</small><h3>{stage}</h3><p>Adults have gray spotted wings and a flash of red underneath. They are active from July through December.</p></div></section>
        <button className="primary" onClick={onTeam}>See team progress</button><button className="secondary" onClick={onDone}>Done</button>
    </main>
    if (outcome === 'native') return <main className="screen result-screen"><Header title="Report complete" onBack={onDone} eyebrow="VERIFICATION RESULT" />
        {locationNotice}
        <div className="result-icon native"><Icon name="leaf" size={36}/></div><p className="status native-text">NATIVE INSECT</p><h2>Thanks for checking first.</h2>
        <p className="result-copy">This looks like a native insect. Please leave it alone — native species keep our ecosystem healthy.</p><div className="points-pill">+2 points <span>Careful identification</span></div>
        <button className="primary" onClick={onLearn}>Compare look-alikes</button><button className="secondary" onClick={onDone}>Done</button>
    </main>
    return <main className="screen result-screen"><Header title="Needs another look" onBack={onDone} eyebrow="VERIFICATION RESULT" />
        {locationNotice}
        <div className="result-icon uncertain">?</div><p className="status uncertain-text">LOW CONFIDENCE</p><h2>We couldn't tell for sure.</h2><p className="result-copy">Automatic identification could not confirm a lanternfly. Try a closer photo in brighter light.</p>
        <button className="primary" onClick={onRetake}><Icon name="camera"/> Retake photo</button><button className="secondary" onClick={onDone}>Done</button>
    </main>
}

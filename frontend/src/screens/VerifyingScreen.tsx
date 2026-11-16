import Header from '../components/Header.tsx'

export default function Verifying() {
    return <main className="screen verifying" aria-busy="true"><Header title="Checking your photo" eyebrow="REPORT IN PROGRESS" />
        <div className="scan-visual"><div className="scan-insect"><i/><i/><b/></div><span className="scan-line"/></div><div className="progress"><i/><i/><i/></div>
        <h2 role="status">Uploading and checking<br/>your photo...</h2><p>We’re checking wing pattern and body color. This usually takes a few seconds.</p>
        <section className="fact-card"><small>DID YOU KNOW?</small><h3>Lanternflies are drawn to the Tree of Heaven.</h3><p>Look for smooth gray bark and large compound leaves with smooth edges.</p></section>
    </main>
}

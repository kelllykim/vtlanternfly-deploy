import {useEffect, useRef, useState} from "react";
import {uploadPhoto, UploadResponse} from "@/services/api.ts";
import Icon from '../components/Icon';
import VerifyingScreen from './VerifyingScreen';
import '../styles/capture.css';

export default function Capture({ onBack, onSuccess }: { onBack: () => void; onSuccess: (res: UploadResponse) => void }) {
    const [photo, setPhoto] = useState<File | null>(null)
    const [preview, setPreview] = useState<string | null>(null)
    const [uploading, setUploading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [result, setResult] = useState<UploadResponse | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (!photo) { setPreview(null); return }
        const url = URL.createObjectURL(photo)
        setPreview(url)
        return () => URL.revokeObjectURL(url)
    }, [photo])

    const submit = async () => {
        if (!photo || uploading) return
        setUploading(true)
        setError(null)
        setResult(null)
        try {
            const res = await uploadPhoto(photo)
            setResult(res)
            onSuccess(res)
        }
        catch (err) { setError(err instanceof Error ? err.message : 'Upload failed') }
        finally { setUploading(false) }
    }

    const retryPhoto = () => {
        setPhoto(null)
        setResult(null)
        setError(null)
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
            fileInputRef.current.click()
        }
    }

    if (uploading) return <VerifyingScreen />

    return <main className="capture-screen">
        <div className="camera-top">
            <button onClick={onBack} aria-label="Back">
                <Icon name="arrow" />
            </button><strong>Photograph sighting</strong><span />
        </div>
        <input ref={fileInputRef} id="photo-upload" type="file" hidden aria-label="Select a lanternfly photo"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif,.mpo" disabled={uploading}
            onChange={e=>{if (e.target.files?.[0]) {setPhoto(e.target.files[0]);setResult(null);setError(null)}}} />
        <div className={`viewfinder${photo ? '' : ' photo-picker-empty'}`}>
            {preview ? <>
                <img src={preview} alt="Selected sighting" style={{width:'100%',height:'100%',objectFit:'contain'}} />
            </> : <button type="button" className="photo-picker" onClick={() => fileInputRef.current?.click()}>
                <span className="photo-picker-icon" aria-hidden="true"><Icon name="camera" size={32}/></span>
                <strong>Choose a photo</strong>
                <span>Tap to open your photos or camera</span>
                <small>JPG, PNG, WebP, HEIC or MPO · Up to 15 MB</small>
            </button>}
        </div>
        <div className="capture-panel">
            {photo && <div className="selected-photo">
                <p role="status"><strong>Photo selected</strong><span>{photo.name}</span></p>
                <button type="button" className="change-photo" disabled={uploading}
                    onClick={() => fileInputRef.current?.click()}>Change photo</button>
            </div>}
            <div className="safety"><strong>!</strong><p><b>Stay safe</b><br/>Stay on sidewalks. Never climb or step into roads.</p></div>
            <button className="capture-button" disabled={!photo || uploading} onClick={submit}><span><Icon name="camera" /></span>{uploading ? 'Uploading...' : 'Upload & check photo'}</button>
            {error && <p role="alert" style={{color:'#b91c1c',marginTop:12}}>{error}</p>}
            {result && <section aria-live="polite" style={{background:'#fff',borderRadius:14,padding:16,marginTop:16,color:'#1f3329'}}>
                <strong>Photo received — metadata and detection results</strong>
                <p style={{fontSize:13,marginTop:8}}>Approved detections earn points and appear on the map when the photo has GPS coordinates.</p>
                <div style={{marginTop:12,padding:12,background:'#f0f7f0',borderRadius:8}}>
                    <strong>AI lanternfly detection</strong>
                    {result.detection.status === 'detected' ? <>
                        <p>Possible lanternfly detected ({result.detection.detection_count} bounding box{result.detection.detection_count === 1 ? '' : 'es'}).</p>
                        {result.detection.detections.map((d, i) => <p key={i} style={{fontSize:13}}>{d.label}: {(d.confidence * 100).toFixed(1)}% model confidence</p>)}
                    </> : result.detection.status === 'not_detected' ?
                        <div role="status" style={{marginTop:12,padding:14,background:'#fffbeb',border:'1px solid #fcd34d',borderRadius:10}}>
                            <strong style={{color:'#92400e'}}>Unable to Identify a Lanternfly</strong>
                            <p style={{marginTop:8,fontSize:14,color:'#92400e'}}>
                                We couldn't clearly identify a spotted lanternfly in your photo.
                                Try taking another picture with better lighting, keeping the lanternfly in focus and clearly visible.
                            </p>
                            <p style={{marginTop:8,fontSize:12,color:'#92400e'}}>
                                This doesn't mean your photo has no lanternfly—the AI may have missed it.
                            </p>
                            <button type="button" onClick={retryPhoto} style={{marginTop:12,padding:'10px 16px',background:'#b45309',color:'#fff',border:0,borderRadius:8,cursor:'pointer',fontWeight:600}}>
                                Try Another Photo
                            </button>
                        </div> :
                        <p role="status">Detector unavailable. Metadata was still extracted. Check the backend logs.</p>}
                    <p style={{fontSize:12}}>Identification is automatic. Detected lanternflies are approved; other photos receive no points.</p>
                </div>
                <p style={{marginTop:8}}>File: {result.metadata.file_name}</p>
                <p>Captured: {result.metadata.timestamp ?? 'Not available in EXIF'}</p>
                <p>Location: {result.metadata.latitude !== null && result.metadata.longitude !== null ? `${result.metadata.latitude}, ${result.metadata.longitude} (${result.metadata.location_source})` : 'No GPS coordinates in photo'}</p>
                <p>Camera: {[result.metadata.camera_make,result.metadata.camera_model].filter(Boolean).join(' ') || 'Unknown'}</p>
                <p>Resolution: {result.metadata.width} × {result.metadata.height}</p>
                <p style={{fontSize:12,marginTop:8}}>Reports are saved to your account. Only approved sightings with GPS coordinates appear on the map.</p>
            </section>}
            <p className="gps-note">⌖ Reads existing photo EXIF metadata; no browser location requested.</p>
        </div>
    </main>
}

import type { UserProfile } from '../types';

// FastAPI sends `detail` as a string for HTTPException, but as a list of
// { loc, msg } objects for validation (422) errors. Turn either into readable text.
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = d.loc?.[d.loc.length - 1];
          return field ? `${String(field).replace('_', ' ')}: ${d.msg}` : d.msg;
        })
        .join('; ');
    }
  } catch { /* response was not JSON */ }
  return `${fallback} (${response.status})`;
}

async function postJson<T>(url: string, data: unknown, fallback: string): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await errorMessage(response, fallback));
  return response.json() as Promise<T>;
}

export function registerUser(data: { email: string; password: string; display_name: string; major: string }) {
  return postJson<UserProfile>('/api/auth/register', data, 'Failed to register');
}

export function loginUser(data: { email: string; password: string }) {
  return postJson<UserProfile>('/api/auth/login', data, 'Failed to log in');
}

export type SightingMetadata = {
  photo_id: string
  file_name: string | null
  timestamp: string | null
  latitude: number | null
  longitude: number | null
  location_source: string | null
  camera_make: string | null
  camera_model: string | null
  image_format: string | null
  width: number | null
  height: number | null
}
export type LanternflyDetection = {
  class_id: number
  label: string
  confidence: number
  bbox_xyxy: number[]
}
export type DetectionResult = {
  status: 'detected' | 'not_detected' | 'unavailable'
  model: string
  detection_count: number
  detections: LanternflyDetection[]
  confidence_threshold?: number
  image_width?: number
  image_height?: number
  message?: string
}
export type UploadResponse = {
  message: string
  report_id: number | null
  photo_id: string
  metadata: SightingMetadata
  detection: DetectionResult
  verification_status: 'approved' | 'pending_review'
  life_stage: string | null
  points_awarded: number
  user: UserProfile | null
}

export async function uploadPhoto(photo: File, userId?: number): Promise<UploadResponse> {
  const data = new FormData()
  data.append('photo', photo)
  if (userId !== undefined) data.append('user_id', String(userId))
  const response = await fetch('/api/sightings', { method: 'POST', body: data })
  if (!response.ok) throw new Error(await errorMessage(response, 'Upload failed'))
  return response.json() as Promise<UploadResponse>
}

export type TeamGoal = { title: string; target: number; found: number }

export async function getTeamGoal(): Promise<TeamGoal> {
  const response = await fetch('/api/team-goal', { cache: 'no-store' })
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to load team goal'))
  return response.json() as Promise<TeamGoal>
}


async function sendJson<T>(url: string, method: string, fallback: string, data?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    cache: 'no-store',
    headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  })
  if (!response.ok) throw new Error(await errorMessage(response, fallback))
  return response.json() as Promise<T>
}

export const getUser = (userId: number) =>
    sendJson<UserProfile>(`/api/users/${userId}`, 'GET', 'Failed to load profile')

export const passLessonApi = (userId: number, lesson: number) =>
    sendJson<UserProfile>(`/api/users/${userId}/lessons/${lesson}/pass`, 'POST', 'Failed to save quiz')

export const updateSettings = (userId: number, settings: { anonymous?: boolean; shareWithResearchers?: boolean }) =>
    sendJson<UserProfile>(`/api/users/${userId}/settings`, 'PATCH', 'Failed to save settings', settings)
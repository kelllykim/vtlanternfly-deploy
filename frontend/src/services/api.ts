import type { UserProfile } from '../types';

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers)
  if (options.method && options.method !== 'GET') headers.set('X-Requested-With', 'VT-Lanternfly')
  const response = await fetch(url, { ...options, headers, credentials: 'same-origin' })
  if (response.status === 401 && !['/api/auth/login', '/api/auth/register'].includes(url)) {
    window.dispatchEvent(new Event('vtlanternfly:session-expired'))
  }
  return response
}

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
  const response = await apiFetch(url, {
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
  duplicate: boolean
  report_id: number | null
  photo_id: string
  metadata: SightingMetadata
  detection: DetectionResult
  verification_status: 'approved' | 'rejected' | 'unavailable'
  life_stage: string | null
  points_awarded: number
  user: UserProfile | null
}

export async function uploadPhoto(photo: File): Promise<UploadResponse> {
  const data = new FormData()
  data.append('photo', photo)
  const response = await apiFetch('/api/sightings', { method: 'POST', body: data })
  if (!response.ok) throw new Error(await errorMessage(response, 'Upload failed'))
  return response.json() as Promise<UploadResponse>
}

export type TeamGoal = { title: string; target: number; found: number }

export async function getTeamGoal(): Promise<TeamGoal> {
  const response = await apiFetch('/api/team-goal', { cache: 'no-store' })
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to load team goal'))
  return response.json() as Promise<TeamGoal>
}


async function sendJson<T>(url: string, method: string, fallback: string, data?: unknown): Promise<T> {
  const response = await apiFetch(url, {
    method,
    cache: 'no-store',
    headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  })
  if (!response.ok) throw new Error(await errorMessage(response, fallback))
  return response.json() as Promise<T>
}

export const getUser = () =>
    sendJson<UserProfile>('/api/auth/me', 'GET', 'Failed to load profile')

export type PublicProfile = { displayName: string; major: string | null; points: number; streak: number; streakBadgeTier: number | null; badges: string[]; badgesPrivate: boolean }
export const getPublicProfile = (userId: number) =>
    sendJson<PublicProfile>(`/api/users/${userId}/public-profile`, 'GET', 'Could not load this profile')

export const passLessonApi = (lesson: number) =>
    sendJson<UserProfile>(`/api/me/lessons/${lesson}/pass`, 'POST', 'Failed to save quiz')

export const updateSettings = (settings: { anonymous?: boolean; shareWithResearchers?: boolean }) =>
    sendJson<UserProfile>('/api/me/settings', 'PATCH', 'Failed to save settings', settings)

export const getLeaderboard = (segment: import('../types').LeaderboardSegment) =>
    sendJson<import('../types').LeaderboardEntry[]>(
        `/api/leaderboard?segment=${encodeURIComponent(segment)}`,
        'GET', 'Failed to load leaderboard')


export const logoutUser = () =>
    sendJson<{ message: string }>('/api/auth/logout', 'POST', 'Could not log out. Please try again.')


export const claimGoalRewards = (goalKey: string, period: string) =>
    sendJson<UserProfile>('/api/me/goals/claim', 'POST', 'Failed to claim goal points', { goal_key: goalKey, period })


export type FriendRequest = { requesterId: number; name: string }

export const getFriendRequests = () =>
    sendJson<FriendRequest[]>('/api/me/friend-requests', 'GET', 'Failed to load friend requests')

export const sendFriendRequest = (email: string) =>
    sendJson<{ message: string }>('/api/me/friend-requests', 'POST', 'Failed to send friend request', { email })

export const respondToFriendRequest = (requesterId: number, action: 'accept' | 'decline') =>
    sendJson<{ message: string }>(`/api/me/friend-requests/${requesterId}`, 'PATCH', 'Failed to respond to friend request', { action })


export const getMajors = () =>
    sendJson<string[]>('/api/majors', 'GET', 'Could not load the major choices. Please try again.')

export type ReportHistoryItem = {
  id: number
  reportNumber: number
  photoUrl: string
  submittedAt: string
  capturedAt: string | null
  status: 'approved' | 'rejected' | 'pending'
  detectionStatus: string | null
  lifeStage: string | null
  confidence: number | null
  latitude: number | null
  longitude: number | null
  points: number
}

export const getReportHistory = (offset = 0) =>
    sendJson<{ reports: ReportHistoryItem[]; nextOffset: number | null }>(
      `/api/me/reports?offset=${offset}`, 'GET', 'Could not load your reports. Please try again.')

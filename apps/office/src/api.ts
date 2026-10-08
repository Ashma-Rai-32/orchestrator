/** Typed calls to the Staffroom API. Types mirror the FastAPI response models. */
import { accessToken } from './auth.ts'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Me = { user_id: string; tenant_id: string; tenant_name: string }
export type Employee = { id: string; name: string; skills: string[]; created_at: string }
export type InboxItem = {
  id: string
  run_id: string
  employee: string
  question: string
  secret_name: string | null // a credential: answered into the secret store, never shown again
}
export type Run = { id: string; goal: string; status: string; summary: string | null }

/** Mirrors staffroom_api.agents.events (a discriminated union on `type`). */
export type RunEvent =
  | { type: 'run_started'; goal: string }
  | { type: 'run_resumed'; from_step: string }
  | { type: 'task_assigned'; employee: string; task: string }
  | { type: 'task_finished'; employee: string; result: string }
  | { type: 'task_failed'; employee: string; error: string }
  | { type: 'input_needed'; question_id: string; employee: string; question: string }
  | { type: 'run_waiting'; open_questions: number }
  | { type: 'run_finished'; summary: string }
  | { type: 'run_failed'; error: string }

const WS_API = API.replace(/^http/, 'ws')

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${await accessToken()}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return (await response.json()) as T
}

/**
 * Replays the run's events, then streams them live; the server closes the socket
 * after the last one. The token travels as a WebSocket subprotocol, never in the URL.
 */
async function followRun(runId: string, onEvent: (event: RunEvent) => void): Promise<void> {
  const socket = new WebSocket(`${WS_API}/runs/${runId}/stream`, ['bearer', await accessToken()])
  return new Promise((resolve, reject) => {
    socket.onmessage = (message) => onEvent((JSON.parse(message.data) as { event: RunEvent }).event)
    socket.onclose = (close) => (close.code === 1000 ? resolve() : reject(new Error(close.reason || `closed ${close.code}`)))
  })
}

export const api = {
  me: () => call<Me>('GET', '/me'),
  employees: () => call<Employee[]>('GET', '/employees'),
  startRun: (goal: string) => call<Run>('POST', '/goals', { goal }),
  inbox: () => call<InboxItem[]>('GET', '/inbox'),
  answer: (itemId: string, answer: string) =>
    call<{ run_resumed: boolean }>('POST', `/inbox/${itemId}/answer`, { answer }),
  followRun,
}

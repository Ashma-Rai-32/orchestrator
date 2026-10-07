/** Typed calls to the Staffroom API. Types mirror the FastAPI response models. */
import { accessToken } from './auth.ts'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Me = { user_id: string; tenant_id: string; tenant_name: string }
export type Employee = { id: string; name: string; skills: string[]; created_at: string }

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${await accessToken()}` },
  })
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return (await response.json()) as T
}

export const api = {
  me: () => get<Me>('/me'),
  employees: () => get<Employee[]>('/employees'),
}

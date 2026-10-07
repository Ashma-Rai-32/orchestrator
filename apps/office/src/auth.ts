/**
 * Sign-in with Keycloak (ADR-0003) via oidc-client-ts: authorization code + PKCE,
 * token storage and silent renewal are the library's job. The organization scope
 * makes Keycloak put the tenant (`tenants` claim) into the access token.
 */
import { UserManager, type User } from 'oidc-client-ts'

const origin = window.location.origin

const users = new UserManager({
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? 'http://localhost:8080/realms/staffroom',
  client_id: 'staffroom-office',
  redirect_uri: `${origin}/`,
  post_logout_redirect_uri: `${origin}/`,
  scope: 'openid organization',
  automaticSilentRenew: true, // refresh-token grant before the 5-minute access token expires
})

/** Returns a signed-in user, or navigates to Keycloak's login page (and never resolves). */
export async function signIn(): Promise<User> {
  const params = new URLSearchParams(window.location.search)
  if (params.has('code') && params.has('state')) {
    const user = await users.signinRedirectCallback()
    window.history.replaceState({}, '', '/') // drop ?code=&state= from the address bar
    return user
  }
  const user = await users.getUser()
  if (user && !user.expired) return user
  await users.signinRedirect()
  return new Promise<never>(() => {}) // the browser is leaving this page
}

export async function accessToken(): Promise<string> {
  const user = await users.getUser()
  if (!user || user.expired) throw new Error('not signed in')
  return user.access_token
}

export function signOut(): Promise<void> {
  return users.signoutRedirect()
}

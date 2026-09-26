export interface Session {
  token: string;
}

export async function fetchSession(): Promise<Session> {
  const response = await fetch("/api/session");
  return response.json();
}

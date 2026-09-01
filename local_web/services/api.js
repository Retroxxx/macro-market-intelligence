export async function getContext() {
  const response = await fetch('/api/local/v1/context', { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

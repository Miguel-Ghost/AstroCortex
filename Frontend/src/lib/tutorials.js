export const TUTORIALS = [
  { id: "your-sky", title: "Your sky", description: "Understand the celestial sphere.", duration: 15.04 },
  { id: "cortex", title: "Cortex", description: "Meet your guide to the sky.", duration: 15.04 },
  { id: "explore", title: "Explore AstroCortex", description: "A tour of the tools and observations.", duration: 15.04 },
].map(t => ({ ...t, video: `/static/tutorials/${t.id}.mp4`, poster: `/static/tutorials/${t.id}.jpg` }));
export function formatVideoTime(seconds) {
  const n = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

/** Observable operations only, independent of the report text and model drafts. */
export type ResearchSite = {
  title: string;
  url: string;
  state: "found" | "selected" | "read" | "unavailable";
};

export type ResearchActivity = {
  kind: "stage" | "query" | "results" | "selection" | "page" | "thought";
  timestamp: string;
  message: string;
  query?: string;
  sources?: ResearchSite[];
};

export type ResearchRun = {
  events: ResearchActivity[];
  state: "running" | "completed" | "interrupted" | "failed";
};

export function collectResearchSites(events: ResearchActivity[], sources: { title: string; url: string }[]): ResearchSite[] {
  const sites = new Map<string, ResearchSite>();
  const priority = { found: 0, selected: 1, unavailable: 2, read: 3 };
  const add = (site: ResearchSite) => {
    try {
      const url = new URL(site.url);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return;
      const previous = sites.get(site.url);
      if (!previous || priority[site.state] >= priority[previous.state]) sites.set(site.url, site);
    } catch { /* Ignore malformed URLs from historical source records. */ }
  };
  sources.forEach(source => add({ ...source, state: "selected" }));
  events.forEach(event => event.sources?.forEach(add));
  return [...sites.values()];
}

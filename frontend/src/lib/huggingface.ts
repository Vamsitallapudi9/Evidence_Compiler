// Client-side normalization of Hugging Face dataset references.

const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const HF_HOSTS = new Set(["huggingface.co", "www.huggingface.co", "hf.co"]);
/** Path segments that follow the dataset name in hub URLs (…/datasets/<name>/tree/main). */
const HUB_SUBPAGES = new Set(["tree", "blob", "resolve", "viewer", "discussions", "commits", "commit", "edit", "raw"]);

function fromSegments(segments: string[], fromUrl: boolean): string | null {
  if (segments.length === 0 || !SEGMENT.test(segments[0])) return null;
  // Legacy canonical datasets have no owner: /datasets/imdb or /datasets/imdb/tree/main.
  if (segments.length === 1 || (fromUrl && HUB_SUBPAGES.has(segments[1]))) return segments[0];
  return SEGMENT.test(segments[1]) ? `${segments[0]}/${segments[1]}` : null;
}

/**
 * Accepts "owner/name", a legacy single-segment name, or a hub URL such as
 * `https://huggingface.co/datasets/owner/name/tree/main?x=1` and returns
 * "owner/name". Returns null if the input is not a dataset reference.
 */
export function normalizeHfDataset(input: string): string | null {
  const raw = input.trim();
  if (!raw || /\s/.test(raw)) return null;

  const looksLikeUrl = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) || /^(www\.)?(huggingface\.co|hf\.co)\//i.test(raw);
  if (looksLikeUrl) {
    let url: URL;
    try {
      url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`);
    } catch {
      return null;
    }
    if (!/^https?:$/.test(url.protocol) || !HF_HOSTS.has(url.hostname.toLowerCase())) return null;
    let segments: string[];
    try {
      segments = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    } catch {
      return null;
    }
    if (segments[0] !== "datasets") return null;
    return fromSegments(segments.slice(1), true);
  }

  // Plain reference; tolerate a leading "datasets/" copied from a path.
  const segments = raw.replace(/^datasets\//, "").split("/");
  if (segments.length > 2) return null;
  return fromSegments(segments, false);
}

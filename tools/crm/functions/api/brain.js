/**
 * /api/brain — GBrain knowledge search via Supabase REST API
 * No pg package needed — pure fetch against PostgREST.
 * Requires env vars: SUPABASE_URL, SUPABASE_ANON_KEY
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const SUPA_URL  = env.SUPABASE_URL;
  const SUPA_KEY  = env.SUPABASE_ANON_KEY;

  if (!SUPA_URL || !SUPA_KEY) return json({ error: 'Supabase not configured' }, 503);

  let body;
  try { body = await request.json(); } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }

  const { action, query, slug, limit = 5 } = body;

  const supaFetch = (path, opts = {}) => fetch(`${SUPA_URL}/rest/v1${path}`, {
    ...opts,
    headers: {
      'apikey': SUPA_KEY,
      'Authorization': `Bearer ${SUPA_KEY}`,
      'Content-Type': 'application/json',
      'Accept-Profile': 'public',
      'Content-Profile': 'public',
      ...(opts.headers || {}),
    },
  });

  if (action === 'search') {
    if (!query) return json({ error: 'query required' }, 400);

    // Full-text search via PostgREST fts operator + title ilike fallback
    const encoded = encodeURIComponent(query.replace(/\s+/g, ' & '));
    const r = await supaFetch(
      `/pages?select=slug,title,compiled_truth&or=(title.ilike.*${encodeURIComponent(query)}*,compiled_truth.ilike.*${encodeURIComponent(query)}*)&limit=${limit}`
    );

    if (!r.ok) {
      const err = await r.text();
      return json({ error: err }, 502);
    }

    const rows = await r.json();
    const results = rows.map(row => ({
      slug: row.slug,
      title: row.title,
      excerpt: (row.compiled_truth || '').slice(0, 400),
      score: 1,
    }));

    return json({ results });
  }

  if (action === 'get') {
    if (!slug) return json({ error: 'slug required' }, 400);
    const r = await supaFetch(`/pages?slug=eq.${encodeURIComponent(slug)}&select=slug,title,compiled_truth&limit=1`);
    if (!r.ok) return json({ error: 'fetch failed' }, 502);
    const rows = await r.json();
    if (!rows.length) return json({ error: 'not found' }, 404);
    return json(rows[0]);
  }

  return json({ error: `Unknown action: ${action}` }, 400);
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' },
  });
}

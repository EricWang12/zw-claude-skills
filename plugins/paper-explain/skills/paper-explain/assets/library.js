/* Stars, drop lists and new-tab links for the paper library. build_index.py copies this
   file to the library root; the home page loads it as library.js, every paper page as
   ../../library.js.

   A star marks a paper the user will work from, such as the papers for a related-work
   section. Stars live in the artifact's database, collection "stars", one doc per star:
     "<Project>"         a whole folder, including papers filed into it later
     "<Project>:<name>"  one paper, the page <Project>/artifact/<name>.html
   Claude reads that collection to gather the starred papers (SKILL.md, "Starred papers").
   The doc "config/home", {url: "https://claude.ai/artifact/<id>"}, is the artifact's own
   link (each account's copy has its own); links opened in a new tab need it (below).
   Where the page cannot reach the database (a saved copy, a signed-out viewer) the stars
   stay hidden, and everything else works as before. */
(async () => {
  const ICON = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.85 5.9 6.5.85-4.75 4.5 1.2 6.45L12 17.4l-5.8 3.1 1.2-6.45-4.75-4.5 6.5-.85z"/></svg>';
  const load = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked: forget it */ } };
  const home = document.getElementById("library");  // the home page's <main>; paper pages have none
  const folders = home ? [...home.querySelectorAll("details[data-proj]")] : [];
  let filter = "all";  // "starred" shows only starred papers; only the database can turn it on

  // The home page opened at <artifact link>#<name> (a link opened in a new tab, below) shows that paper.
  const want = home && location.hash.slice(1);
  const card = want && [...home.querySelectorAll("ol.papers a")].find(a => a.getAttribute("href").endsWith("/" + want + ".html"));
  if (card) return location.replace(card.getAttribute("href"));

  // Home page: each folder is a drop list, closed until opened. This browser remembers which are open.
  let opened = new Set();
  try { opened = new Set(JSON.parse(load("library.open") || "[]")); } catch (e) { /* bad value: all closed */ }
  for (const d of folders) d.open = opened.has(d.dataset.proj);
  home?.addEventListener("click", e => {
    const summary = e.target.closest("summary");
    if (!summary || e.target.closest("button") || filter !== "all") return;
    const p = summary.parentElement.dataset.proj;
    summary.parentElement.open ? opened.delete(p) : opened.add(p);  // the folder toggles right after this click
    save("library.open", JSON.stringify([...opened]));
  });

  let db = null;
  try { db = await window.claude?.use?.("db"); } catch (e) { db = null; }
  if (!db) return;
  newTabLinks();
  if (home) homeStars(); else paperStar();

  // A page's address inside the artifact opens only the home page in a tab of its own. So while a
  // new-tab gesture (middle click, Ctrl/Cmd/Shift click, right click, long press) is under way, a
  // link to a library page carries <artifact link>#<name>, which the home page opens (above).
  // A plain click keeps the page's own address and stays in this frame.
  async function newTabLinks() {
    let url = "";
    try { url = (await db.doc("config/home").get()).data()?.url || ""; } catch (e) { /* no link: such tabs show the home page */ }
    if (!/^https:\/\/claude\.ai\/[\w/-]+$/.test(url)) return;
    const aim = (e, tab) => {
      const a = e.target.closest?.("a[href]");
      if (!(a instanceof HTMLAnchorElement)) return;
      const own = a.dataset.href || a.getAttribute("href");
      const u = new URL(own, location.href);
      if (u.origin !== location.origin) return;  // other websites open in a new tab anyway
      a.dataset.href = own;
      const m = u.pathname.match(/\/artifact\/([^/]+)\.html$/);
      a.setAttribute("href", tab ? url + (m ? "#" + m[1] : "") : own);
    };
    const tab = e => !!(e.button || e.ctrlKey || e.metaKey || e.shiftKey);
    addEventListener("mousedown", e => aim(e, tab(e)), true);
    addEventListener("keydown", e => e.key === "Enter" && aim(e, tab(e)), true);
    addEventListener("contextmenu", e => aim(e, true), true);
    addEventListener("touchstart", e => aim(e, true), { capture: true, passive: true });
  }

  // The database shows a write to this page at once, through the snapshot, which redraws the stars.
  async function write(key, on, btn) {
    btn.disabled = true;  // one write at a time per star
    try {
      const doc = db.doc("stars/" + key);
      if (on) await doc.set({ path: key.includes(":") ? key.replace(":", "/artifact/") + ".html" : key + "/" });
      else await doc.delete();
    } catch (e) {
      console.warn("star not saved:", e && (e.code || e.message));
    } finally {
      btn.disabled = false;
    }
  }

  function homeStars() {
    const seg = document.getElementById("star-filter");
    const hint = document.getElementById("star-hint");
    const empty = document.getElementById("star-empty");
    let stars = new Set(), first = true;

    function render() {
      let n = 0;
      for (const d of folders) {
        const whole = stars.has(d.dataset.proj);
        let shown = 0;
        d.querySelector(".fstar").setAttribute("aria-pressed", whole);
        for (const b of d.querySelectorAll(".star")) {
          const own = stars.has(b.dataset.star);
          b.setAttribute("aria-pressed", own);
          if (whole || own) { n++; shown++; }
          b.parentElement.hidden = filter === "starred" && !(whole || own);
        }
        d.hidden = filter === "starred" && !shown;
      }
      document.getElementById("star-count").textContent = n;
      for (const b of seg.querySelectorAll("[data-filter]")) b.setAttribute("aria-pressed", b.dataset.filter === filter);
      hint.hidden = filter !== "starred" || !n;
      empty.hidden = filter !== "starred" || n > 0;
    }

    function setFilter(f) {
      filter = f;
      save("library.filter", f);
      render();
      // Starred: open every folder that shows a paper. All: back to the folders this browser opened.
      for (const d of folders) d.open = f === "starred" ? !d.hidden : opened.has(d.dataset.proj);
    }

    db.collection("stars").onSnapshot(snap => {
      stars = new Set(snap.docs.map(d => d.id));
      if (!first) return render();
      first = false;
      document.documentElement.classList.add("stars-on");
      setFilter(load("library.filter") === "starred" ? "starred" : "all");
    }, e => console.warn("stars unavailable:", e && e.code));

    seg.addEventListener("click", e => {
      const b = e.target.closest("[data-filter]");
      if (b && b.dataset.filter !== filter) setFilter(b.dataset.filter);
    });
    home.addEventListener("click", e => {
      const b = e.target.closest("button[data-star]");
      if (!b) return;
      e.preventDefault();  // a star in a folder's header must not open or close the folder
      write(b.dataset.star, b.getAttribute("aria-pressed") !== "true", b);
    });
  }

  function paperStar() {
    // The page's own path, <Project>/artifact/<name>.html, names its star.
    const m = location.pathname.match(/([^/]+)\/artifact\/([^/]+)\.html$/);
    const bar = document.querySelector("nav.bar .frame");
    if (!m || !bar) return;
    const key = m[1] + ":" + m[2];
    const css = document.createElement("style");
    css.textContent = `
.star-btn { margin-left: auto; flex: none; display: inline-flex; align-items: center; gap: .35rem; font: 500 .8rem var(--f-mono);
  color: var(--muted); background: var(--surface); border: 1px solid var(--rule); border-radius: 4px; padding: .25rem .6rem; cursor: pointer; }
.star-btn:hover { color: var(--accent); }
.star-btn[aria-pressed="true"] { color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
.star-btn svg { width: 15px; height: 15px; display: block; }
.star-btn path { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linejoin: round; }
.star-btn[aria-pressed="true"] path { fill: currentColor; }`;
    document.head.append(css);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "star-btn";
    btn.setAttribute("aria-label", "星标这篇 paper");
    btn.innerHTML = ICON + "星标";
    btn.addEventListener("click", () => write(key, btn.getAttribute("aria-pressed") !== "true", btn));
    db.doc("stars/" + key).onSnapshot(s => {
      btn.setAttribute("aria-pressed", s.exists);
      if (!btn.isConnected) bar.append(btn);  // shown once the star's state is known
    }, e => console.warn("star unavailable:", e && e.code));
  }
})();

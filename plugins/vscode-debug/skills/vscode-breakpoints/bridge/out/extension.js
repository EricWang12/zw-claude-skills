"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const path = __importStar(require("node:path"));
const vscode = __importStar(require("vscode"));
/**
 * Turns a JSON manifest into real editor source breakpoints -- the red dots in
 * the gutter and the rows in the Breakpoints panel.
 *
 * The manifest is the whole interface. A terminal agent (or a human, or CI)
 * writes the file; this extension is the only thing that touches the debug API.
 * Nothing here modifies the program under debug.
 */
const OWNED_KEY = "agentBreakpoints.owned";
/**
 * Diagnostics go to three places: an output channel, and a file under /tmp.
 *
 * The file matters because this extension runs in a remote extension host while
 * the UI runs on a laptop -- without it, the only way to see why a sync did
 * nothing is to be sitting in front of the editor. Quiet mode silences toasts,
 * never logging; a sync that silently does nothing is the failure mode that is
 * hardest to diagnose.
 */
const DIAG_FILE = "/tmp/agent-breakpoints-diag.log";
let channel;
function log(message) {
    const line = `${new Date().toISOString()} ${message}`;
    channel?.appendLine(line);
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        require("node:fs").appendFileSync(DIAG_FILE, line + "\n");
    }
    catch {
        // Diagnostics must never break a sync.
    }
}
/** Stable identity for a breakpoint, so we only ever remove our own. */
function keyOf(fsPath, line) {
    return `${fsPath}:${line}`;
}
function manifestUri() {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
        return undefined;
    }
    const rel = vscode.workspace
        .getConfiguration("agentBreakpoints")
        .get("manifestPath", ".vscode/breakpoints.json");
    return vscode.Uri.joinPath(folder.uri, rel);
}
/**
 * Resolve a manifest path. Absolute wins; otherwise try each workspace folder
 * so a multi-root setup still lands on the right file.
 */
function resolveTarget(file) {
    if (path.isAbsolute(file)) {
        return vscode.Uri.file(file);
    }
    const folders = vscode.workspace.workspaceFolders ?? [];
    for (const folder of folders) {
        const candidate = vscode.Uri.joinPath(folder.uri, file);
        if (candidate.fsPath.length > 0) {
            return candidate;
        }
    }
    return undefined;
}
async function readManifest(uri) {
    const problems = [];
    let raw;
    try {
        raw = await vscode.workspace.fs.readFile(uri);
    }
    catch {
        return { entries: [], problems: [`Manifest not found: ${uri.fsPath}`] };
    }
    let parsed;
    try {
        parsed = JSON.parse(Buffer.from(raw).toString("utf8"));
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return { entries: [], problems: [`Manifest is not valid JSON: ${message}`] };
    }
    const list = Array.isArray(parsed) ? parsed : parsed.breakpoints ?? [];
    const entries = [];
    for (const [index, entry] of list.entries()) {
        if (typeof entry?.file !== "string" || entry.file.length === 0) {
            problems.push(`Entry ${index}: missing "file".`);
            continue;
        }
        if (!Number.isInteger(entry.line) || entry.line < 1) {
            problems.push(`Entry ${index} (${entry.file}): "line" must be a positive integer, got ${entry.line}.`);
            continue;
        }
        entries.push(entry);
    }
    return { entries, problems };
}
/**
 * Replace the previously-synced set with the manifest's set.
 *
 * Only breakpoints this extension created are removed, tracked by file:line in
 * workspace state -- breakpoints placed by hand survive a sync untouched.
 */
async function sync(context, { quiet = false } = {}) {
    const uri = manifestUri();
    if (!uri) {
        log("sync aborted: no workspace folder is open, so there is no manifest to read");
        if (!quiet) {
            vscode.window.showWarningMessage("Agent Breakpoints: no folder is open, so there is no manifest to read.");
        }
        return;
    }
    log(`sync start: manifest=${uri.fsPath} quiet=${quiet}`);
    const { entries, problems } = await readManifest(uri);
    log(`manifest parsed: ${entries.length} usable entries, ${problems.length} problem(s)`);
    const desired = new Map();
    for (const entry of entries) {
        const target = resolveTarget(entry.file);
        if (!target) {
            problems.push(`${entry.file}: could not resolve against any workspace folder.`);
            continue;
        }
        // Existence only. Deliberately NOT openTextDocument to check line count:
        // that loads every referenced file into the editor's model, which on a
        // network or FUSE-backed workspace turns one sync into N slow round-trips
        // and makes it look hung. The writer validates line numbers against source
        // before the manifest is ever written, which is the cheaper place to do it.
        try {
            await vscode.workspace.fs.stat(target);
        }
        catch {
            problems.push(`${entry.file}: file does not exist.`);
            continue;
        }
        desired.set(keyOf(target.fsPath, entry.line), { entry, target });
    }
    const owned = new Set(context.workspaceState.get(OWNED_KEY, []));
    const existing = vscode.debug.breakpoints.filter((bp) => bp instanceof vscode.SourceBreakpoint);
    // Drop everything we own, then re-add from the manifest. Re-adding rather
    // than mutating is what lets a changed condition or logMessage take effect.
    const stale = existing.filter((bp) => owned.has(keyOf(bp.location.uri.fsPath, bp.location.range.start.line + 1)));
    if (stale.length > 0) {
        vscode.debug.removeBreakpoints(stale);
    }
    const stillThere = new Set(vscode.debug.breakpoints
        .filter((bp) => bp instanceof vscode.SourceBreakpoint)
        .map((bp) => keyOf(bp.location.uri.fsPath, bp.location.range.start.line + 1)));
    const toAdd = [];
    for (const [key, { entry, target }] of desired) {
        if (stillThere.has(key)) {
            continue; // A hand-placed breakpoint already marks this line; leave it alone.
        }
        // Manifest lines are 1-based, the way editors and stack traces report them.
        const position = new vscode.Position(entry.line - 1, 0);
        toAdd.push(new vscode.SourceBreakpoint(new vscode.Location(target, position), entry.enabled ?? true, entry.condition, entry.hitCondition, entry.logMessage));
    }
    if (toAdd.length > 0) {
        vscode.debug.addBreakpoints(toAdd);
    }
    await context.workspaceState.update(OWNED_KEY, [...desired.keys()]);
    log(`sync done: desired=${desired.size} removed=${stale.length} added=${toAdd.length} ` +
        `debug.breakpoints now=${vscode.debug.breakpoints.length}`);
    for (const problem of problems) {
        log(`  problem: ${problem}`);
    }
    if (quiet) {
        return;
    }
    const summary = `Agent Breakpoints: ${desired.size} breakpoint${desired.size === 1 ? "" : "s"} synced from ${vscode.workspace.asRelativePath(uri)}.`;
    if (problems.length > 0) {
        vscode.window.showWarningMessage(`${summary} ${problems.length} skipped.`, "Show details").then((choice) => {
            if (choice === "Show details") {
                vscode.window.showWarningMessage(problems.join("\n"), { modal: true });
            }
        });
    }
    else {
        vscode.window.setStatusBarMessage(summary, 5000);
    }
}
/**
 * Serialize syncs.
 *
 * One manifest write can arrive as several watcher events, and the editor also
 * coalesces them, so without this the callbacks overlap. Overlapping syncs each
 * read and rewrite the same owned-breakpoint set and race each other -- the
 * observable symptom is duplicate work and a set that does not match the file.
 *
 * A run in flight sets a dirty flag instead of starting a second pass, so the
 * last write always wins and exactly one extra sync follows it.
 */
let syncing = false;
let syncDirty = false;
async function requestSync(context, reason, opts = {}) {
    if (syncing) {
        syncDirty = true;
        log(`sync coalesced (${reason}): one already in flight`);
        return;
    }
    syncing = true;
    try {
        do {
            syncDirty = false;
            await sync(context, opts);
        } while (syncDirty);
    }
    catch (err) {
        log(`sync threw (${reason}): ${err instanceof Error ? err.stack ?? err.message : String(err)}`);
    }
    finally {
        syncing = false;
    }
}
async function clear(context) {
    const owned = new Set(context.workspaceState.get(OWNED_KEY, []));
    const mine = vscode.debug.breakpoints.filter((bp) => bp instanceof vscode.SourceBreakpoint &&
        owned.has(keyOf(bp.location.uri.fsPath, bp.location.range.start.line + 1)));
    if (mine.length > 0) {
        vscode.debug.removeBreakpoints(mine);
    }
    await context.workspaceState.update(OWNED_KEY, []);
    vscode.window.setStatusBarMessage(`Agent Breakpoints: cleared ${mine.length} breakpoint${mine.length === 1 ? "" : "s"}.`, 5000);
}
function activate(context) {
    channel = vscode.window.createOutputChannel("Agent Breakpoints");
    context.subscriptions.push(channel);
    const folders = (vscode.workspace.workspaceFolders ?? []).map((f) => f.uri.fsPath);
    const config = vscode.workspace.getConfiguration("agentBreakpoints");
    log("--------------------------------------------------------------");
    log(`activate: editor=${vscode.version} extension=${context.extension?.id ?? "unknown"}`);
    log(`activate: workspaceFolders=${JSON.stringify(folders)}`);
    log(`activate: manifestPath=${config.get("manifestPath")} autoSync=${config.get("autoSync")} syncOnStartup=${config.get("syncOnStartup")}`);
    context.subscriptions.push(vscode.commands.registerCommand("agentBreakpoints.sync", () => requestSync(context, "command")), vscode.commands.registerCommand("agentBreakpoints.diagnose", () => {
        log(`diagnose: debug.breakpoints=${vscode.debug.breakpoints.length}`);
        log(`diagnose: owned=${JSON.stringify(context.workspaceState.get(OWNED_KEY, []))}`);
        channel?.show();
    }), vscode.commands.registerCommand("agentBreakpoints.clear", () => clear(context)), vscode.commands.registerCommand("agentBreakpoints.reveal", async () => {
        const uri = manifestUri();
        if (uri) {
            await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri));
        }
    }));
    if (config.get("autoSync", true)) {
        const rel = config.get("manifestPath", ".vscode/breakpoints.json");
        const folder = vscode.workspace.workspaceFolders?.[0];
        if (folder) {
            const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, rel));
            // Quiet on watch-driven syncs: a caller may rewrite the manifest
            // repeatedly, and a toast per write would be noise.
            watcher.onDidChange(() => void requestSync(context, "watch:change", { quiet: true }));
            watcher.onDidCreate(() => void requestSync(context, "watch:create", { quiet: true }));
            context.subscriptions.push(watcher);
            // Poll as well as watch. Watcher latency varies with the filesystem --
            // on a FUSE-backed workspace events have arrived ~19 s late, which is
            // long enough that a caller waiting for confirmation gives up first.
            // An mtime stat every couple of seconds is cheap and bounds the delay.
            let lastMtime = 0;
            const manifest = vscode.Uri.joinPath(folder.uri, rel);
            const poll = setInterval(async () => {
                if (syncing) {
                    return;
                }
                try {
                    const stat = await vscode.workspace.fs.stat(manifest);
                    if (lastMtime === 0) {
                        lastMtime = stat.mtime;
                        return;
                    }
                    if (stat.mtime !== lastMtime) {
                        lastMtime = stat.mtime;
                        await requestSync(context, "poll", { quiet: true });
                    }
                }
                catch {
                    // Manifest absent or unreadable; the create watcher covers its return.
                }
            }, 2000);
            context.subscriptions.push(new vscode.Disposable(() => clearInterval(poll)));
        }
    }
    if (config.get("syncOnStartup", true)) {
        void requestSync(context, "startup", { quiet: true });
    }
    log("activate: done");
}
function deactivate() { }
//# sourceMappingURL=extension.js.map
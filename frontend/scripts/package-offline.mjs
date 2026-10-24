import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const entry=readFileSync(resolve(root,'dist/client/index.html'),'utf8');
if(!entry.includes('assets/'))throw Error('Build the current application before packaging');
const out=resolve(root,'../deliverables');mkdirSync(out,{recursive:true});
writeFileSync(resolve(out,'UOL-Workspace.html'),`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>UOL · Run locally</title><style>body{font:17px/1.6 system-ui;background:#fafaf5;color:#153f3c;max-width:780px;margin:60px auto;padding:24px}pre{background:#eaf1ed;padding:20px;overflow:auto}a{color:#176b66}</style><h1>UOL workspace</h1><p>The original workspace now runs against the encrypted Python application service. Use the complete source archive; this guide does not substitute a browser-only mock.</p><pre>python -m venv .venv\n. .venv/bin/activate\npip install -r backend/requirements.txt\ncd frontend &amp;&amp; npm ci &amp;&amp; cd ..\npython backend/scripts/run-local.py --frontend frontend --demo --ephemeral</pre><p>Then open <a href="http://127.0.0.1:5173">UOL locally</a>. Remove --ephemeral to retain encrypted state using your OS keyring. Use --project-dir for your configured project instead of --demo.</p><p>Metadata only. No live native writes or source-record queries. See README and QA reports in the archive.</p></html>`);
console.log('Packaged local startup guide; current production bundle remains in dist/client.');

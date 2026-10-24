import test from 'node:test';
import assert from 'node:assert/strict';
import { seed } from '../src/fixtures.ts';
import { revise, saveMapping, workspaceExport } from '../src/services.ts';

test('knowledge revision rejects invalid calendar dates without mutation', () => {
  for (const patch of [{validFrom:'2026-02-30'}, {validFrom:''}, {validFrom:'tomorrow'}, {validTo:'2026-13-01'}, {validTo:'2026-09-30'}]) {
    const s=seed(), before=structuredClone(s);
    assert.throws(()=>revise(s,'active-customer',patch), /valid|date|begin/i);
    assert.deepEqual(s,before);
  }
});
test('knowledge membership changes retain one existing owner and unique additional domains', () => {
  for (const patch of [{domain:'missing'}, {memberships:['missing']}, {memberships:['service','service']}, {domain:'service',memberships:['service']}]) {
    const s=seed(), before=structuredClone(s);
    assert.throws(()=>revise(s,'active-customer',patch), /domain|membership/i);
    assert.deepEqual(s,before);
  }
  const s=seed(), before=structuredClone(s.knowledge.find(k=>k.id==='active-customer')!);
  const edited=revise(s,before.id,{domain:'customer',memberships:['service','finance']});
  assert.equal(edited.id,before.id); assert.equal(edited.originId,before.originId);
  assert.deepEqual(edited.memberships,['service','finance']);
  revise(s,before.id,{memberships:[]});
  assert.equal(edited.domain,'customer'); assert.deepEqual(edited.memberships,[]);
});
test('mapping rejects malformed calendar dates before creating a record', () => {
  for (const validFrom of ['', '2026-02-30','2026-2-01','not-a-date']) {
    const s=seed(), m=s.mappings[0], before=structuredClone(s);
    assert.throws(()=>saveMapping(s,{...m,validFrom},'steward'), /valid|date/i);
    assert.deepEqual(s,before);
  }
  const s=seed();
  assert.throws(()=>saveMapping(s,{...s.mappings[0],validTo:'2026-99-99'},'steward'),/valid|date/i);
  assert.doesNotThrow(()=>saveMapping(s,{...s.mappings[0],validFrom:'2024-02-29',validTo:'2024-02-29'},'steward'));
});
test('workspace exports prune inaccessible structured references without changing source records', () => {
  const s=seed(), k=s.knowledge.find(k=>k.id==='active-customer')!, a=s.assets.find(a=>a.id==='customers')!;
  k.related=['private-concept','mrr','contract'];
  a.knowledgeIds=['private-concept','mrr','active-customer']; a.parent='hidden-asset';
  const before=structuredClone(s), payload=workspaceExport(s,'restricted',true).payload as any;
  assert.deepEqual(payload.knowledge.find((k:any)=>k.id==='active-customer').related,['contract']);
  assert.deepEqual(payload.assets.find((a:any)=>a.id==='customers').knowledgeIds,['active-customer']);
  assert.equal(payload.assets.find((a:any)=>a.id==='customers').parent,null);
  assert.deepEqual(s,before);
});

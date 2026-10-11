// Genuine SDK smoke test: uses the same @modelcontextprotocol/client@2.2.0
// module imported by DeepSeek Harness' dsh-mcp-client. Not the DSH Web app.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';

const python = process.env.PYTHON || 'python3';
const scratch = mkdtempSync(join(process.env.RUNNER_TEMP || tmpdir(), 'trisynora-mcp-client-'));
const stage = join(scratch, 'exchange');
const pkg = join(stage, 'demo');
mkdirSync(join(pkg, 'assets'), { recursive: true });
mkdirSync(join(pkg, 'manifests'));
const saveJson = (path, value) => {
  const body = Buffer.from(JSON.stringify(value));
  writeFileSync(path, body);
  return createHash('sha256').update(body).digest('hex');
};
saveJson(join(stage, '.trisynora-exchange-root.json'), {
  format: 'trisynora.external-exchange-root/v1', kind: 'read-only-staging',
});
const video = Buffer.from('synthetic media bytes, not a real mp4');
writeFileSync(join(pkg, 'assets', 'Asset001.mp4'), video);
const origin = { product: 'minimax-h3', projectId: 'SampleProject', revision: 'fixture-r1' };
const asset = {
  contract: 'trisynora.asset/v1', artifactId: 'Asset001', origin,
  media: {
    kind: 'video', mimeType: 'video/mp4',
    path: 'assets/Asset001.mp4', sizeBytes: video.length,
    sha256: createHash('sha256').update(video).digest('hex'),
  },
  publication: { mode: 'reference-only', requiresReceiverApproval: true },
};
const shot = {
  contract: 'trisynora.shot/v1', shotId: 'Shot001', origin,
  native: { format: 'minimax-h3/mock-fixture', sha256: '0'.repeat(64) },
  timebase: { fpsNumerator: 30, fpsDenominator: 1, durationFrames: 30 },
  assetIds: ['Asset001'],
  handoff: { mode: 'reference-only', requiresExplicitBind: true },
};
const assetSha = saveJson(join(pkg, 'manifests', 'asset.json'), asset);
const shotSha = saveJson(join(pkg, 'manifests', 'shot.json'), shot);
saveJson(join(pkg, 'ready.json'), {
  format: 'trisynora.h3-video-package/v1',
  assetManifestSha256: assetSha,
  shotManifestSha256: shotSha,
});
const server = process.env.TRISYNORA_MCP_SCRIPT;
assert.ok(server && server.startsWith('/'), 'absolute MCP script required');
const client = new Client(
  { name: 'trisynora-genuine-mcp-sdk-smoke', version: '0.1.0' },
  { capabilities: {} },
);
const transport = new StdioClientTransport({
  command: python,
  args: ['-B', server],
  env: {
    PATH: process.env.PATH || '/usr/bin:/bin',
    PYTHONDONTWRITEBYTECODE: '1',
    TRISYNORA_EXCHANGE_ROOT: stage,
  },
});
try {
  await client.connect(transport);
  const listed = await client.listTools();
  const names = listed.tools.map(x => x.name).sort();
  assert.deepEqual(names, [
    'trisynora_check_capability',
    'trisynora_inspect_package',
    'trisynora_list_capabilities',
  ]);
  assert.ok(listed.tools.every(x => x.annotations?.readOnlyHint === true));
  const catalog = await client.callTool({
    name: 'trisynora_list_capabilities', arguments: {},
  });
  assert.equal(catalog.isError, false);
  const contents = JSON.parse(catalog.content[0].text);
  assert.equal(contents.status, 'catalog-only');
  assert.deepEqual(contents.products.map(x => x.connected), [false, false, false]);
  const missing = await client.callTool({
    name: 'trisynora_check_capability',
    arguments: { product: 'pointflux', capability: 'video-layer-import' },
  });
  assert.equal(missing.isError, false);
  assert.equal(JSON.parse(missing.content[0].text).status, 'not-connected');
  const inspected = await client.callTool({
    name: 'trisynora_inspect_package', arguments: { packageId: 'demo' },
  });
  assert.equal(inspected.isError, false);
  const verified = JSON.parse(inspected.content[0].text);
  assert.equal(verified.status, 'verified-reference-only');
  assert.equal(verified.artifactId, 'Asset001');
  assert.equal(verified.mediaSha256, asset.media.sha256);
  assert.equal(verified.mediaCodecVerified, false);
  assert.equal(verified.pointfluxImported, false);
  writeFileSync(join(pkg, 'assets', 'Asset001.mp4'), Buffer.from('tampered media'));
  const tampered = await client.callTool({
    name: 'trisynora_inspect_package', arguments: { packageId: 'demo' },
  });
  assert.equal(tampered.isError, true);
  const forbidden = await client.callTool({
    name: 'trisynora_inspect_package',
    arguments: { packageId: '../vera' },
  });
  assert.equal(forbidden.isError, true);
  const invalidName = await client.callTool({
    name: 'trisynora_write_to_pointflux',
    arguments: { path: '/root/PointFlux' },
  });
  assert.equal(invalidName.isError, true);
  console.log(JSON.stringify({
    status: 'genuine-mcp-sdk-stdio-pass',
    sdk: '@modelcontextprotocol/client@2.2.0',
    listedTools: names.length,
    nativeProductsConnected: false,
    nativeWriteToolExposed: false,
    inspectedActualPackageBytes: true,
    tamperedBytesRejected: true,
    harnessWebUiVerified: false,
  }));
} finally {
  await client.close();
  rmSync(scratch, { recursive: true, force: true });
}

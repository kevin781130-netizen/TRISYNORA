// Genuine SDK smoke test: uses the same @modelcontextprotocol/client@2.2.0
// module imported by DeepSeek Harness' dsh-mcp-client. Not the DSH Web app.
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';

const python = process.env.PYTHON || 'python3';
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
    TRISYNORA_EXCHANGE_ROOT: process.env.TRISYNORA_EXCHANGE_ROOT || '',
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
    harnessWebUiVerified: false,
  }));
} finally {
  await client.close();
}

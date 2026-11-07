import fs from 'node:fs';
import path from 'node:path';
import solc from 'solc';
export function compile(name = 'EvidenceRegistry', source = `${name}.sol`) {
  const input = { language: 'Solidity', sources: { [source]: {
    content: fs.readFileSync(new URL(`../contracts/${source}`, import.meta.url), 'utf8')
  } }, settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'paris',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object', 'evm.deployedBytecode.object'] } } } };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: name => {
    try { return { contents: fs.readFileSync(new URL(`../node_modules/${name}`, import.meta.url), 'utf8') }; }
    catch { return { error: `Import not found: ${name}` }; }
  } }));
  const errors = (output.errors || []).filter(e => e.severity === 'error');
  if (errors.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'));
  const result = output.contracts[source][name];
  return { abi: result.abi, bytecode: '0x' + result.evm.bytecode.object,
    deployedBytecode: '0x' + result.evm.deployedBytecode.object, compiler: solc.version() };
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  fs.mkdirSync('artifacts', { recursive: true });
  for (const name of ['EvidenceRegistry', 'TaskEscrow', 'BusinessRecords', 'TestToken']) {
    const artifact = compile(name, name === 'TestToken' ? 'test/TestToken.sol' : `${name}.sol`);
    fs.writeFileSync(path.join('artifacts', `${name}.json`), JSON.stringify(artifact, null, 2));
    console.log(`Compiled ${name} (${(artifact.deployedBytecode.length - 2) / 2} runtime bytes)`);
  }
}
